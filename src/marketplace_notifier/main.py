import asyncio
import json
import logging
import sys
import traceback
from datetime import timedelta, datetime

from aiohttp_retry import RetryClient, ExponentialRetry
import redis.asyncio as redisaio
from tortoise import run_async, Tortoise

from config.config import config
from src.marketplace_notifier.utils.api_utils import get_request_response
from src.marketplace_notifier.notifier import TweedehandsNotifier
from src.shared.models import QueryInfo

FETCH_INTERVAL = 2 * 60  # 2 minutes
# Create a custom logger
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Create formatter
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# File handler
file_handler = logging.FileHandler('requests.log', encoding='utf-8')
file_handler.setFormatter(formatter)

# Console handler
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(formatter)

# Clear previous handlers (important when using in notebooks or reloading modules)
if logger.hasHandlers():
    logger.handlers.clear()

for handler in [file_handler, console_handler]:
    logger.addHandler(handler)


class QueryScheduler:
    def __init__(self, notifier, retry_client, redis_client, interval=FETCH_INTERVAL):
        self.notifier = notifier
        self.retry_client = retry_client
        self.redis_client = redis_client
        self.interval = interval
        self.tasks = {}  # Maps query URL to next scheduled time
        self.running = True

    async def start(self):
        """Start the scheduler and monitor for changes in queries"""
        queries = await QueryInfo.filter(is_healthy=True)
        for query in queries:
            if query.request_url not in self.tasks:
                # intialize the tasks for the first time (on boot)
                self.tasks[query.request_url] = datetime.now() + timedelta(seconds=self.interval)
                logging.info(f"Initialized query scheduling: {query.request_url}")


        while self.running:
            queries = await QueryInfo.filter(is_healthy=True)
            if not queries:
                logging.info("No (healthy) queries found, sleeping...")
                await asyncio.sleep(10)
                continue
            query_count = len(queries)

            # for every query above 4, increase the interval by 30 seconds, up to a maximum of 240 seconds
            self.interval = min(120 + max(query_count - 4, 0) * 30, 240)

            request_urls = {query.request_url for query in queries}

            # remove tasks for URLs that no longer exist
            removed_urls = set(self.tasks.keys()) - request_urls
            for url in removed_urls:
                logging.info(f"Query removed from monitoring: {url}")
                self.tasks.pop(url, None)

            # add new queries that aren't being tracked yet
            new_urls = request_urls - set(self.tasks.keys())
            self._schedule_new_queries(new_urls)

            # process queries that are ready to fetch
            await self._process_ready_queries()

            # log upcoming schedule
            self._log_schedule()

            # wait a bit before checking again
            await asyncio.sleep(10)

    def _schedule_new_queries(self, new_urls):
        """Schedule new queries with staggered times"""
        if not new_urls:
            return

        # calculate how to spread new queries
        now = datetime.now()
        spread_interval = self.interval / (len(new_urls) or 1)

        for i, url in enumerate(new_urls):
            # schedule queries with staggered times based on the interval
            schedule_time = now + timedelta(seconds=i * spread_interval)
            self.tasks[url] = schedule_time
            logging.info(f"New query scheduled for {schedule_time.strftime('%H:%M:%S')}: {url}")
            # update the next check time in the database
            QueryInfo.filter(request_url=url).update(next_check_time=schedule_time)



    async def _process_ready_queries(self):
        """Process all queries that are ready to be fetched"""
        now = datetime.now()
        ready_urls = [url for url, time in self.tasks.items() if time <= now]
        if len(ready_urls) > 1:
            # TODO: fix this, make sure it spreads evenly
            queries = await QueryInfo.filter(is_healthy=True)
            logging.warning(f"Too many URLs being fetched at once: {len(ready_urls)} queries to fetch of {len(queries)} healthy queries")
            await self.redis_client.publish("error_channel", json.dumps({
                "error": f"Too many urls being fetched at once: {len(ready_urls)}\nBe aware of ratelimiting!",
                "reason": f"urls 'next_time' aren't spread well enough, currently {len(queries)} healthy queries"
            }))

        # this should hopefully not be a big list
        for url in ready_urls:
            try:
                logging.info(f"Fetching: {url}")

                result = await get_request_response(self.retry_client, url)
                await self.notifier.process_listings({url: result["listings"]}, self.redis_client)

                # reschedule for next interval
                next_time = now + timedelta(seconds=self.interval)
                self.tasks[url] = next_time

                # Update the next check time in the database
                await QueryInfo.filter(request_url=url).update(next_check_time=next_time)

            except Exception as e:
                tb = traceback.format_exc()
                logging.error(f"Error fetching {url}: {type(e)}{str(e)}\ntraceback: {tb}")
                await self.redis_client.publish("error_channel", json.dumps({
                    "error": f"Error while fetching {url}",
                    "reason": str(e),
                    "trace": tb
                }))
                # mark task as unhealthy
                await QueryInfo.filter(request_url=url).update(is_healthy=False)
                logging.info(f"Task/url marked as unhealthy: {url}")

    def _log_schedule(self):
        """Log the upcoming schedule"""
        now = datetime.now()
        upcoming = [(url, time) for url, time in self.tasks.items() if time > now]
        upcoming.sort(key=lambda x: x[1])

        if upcoming:
            logging.info("Upcoming fetches:")
            for i, (url, time) in enumerate(upcoming[:5]):  # show at most 5
                wait_seconds = (time - now).total_seconds()
                logging.info(f"  {i + 1}. {time.strftime('%H:%M:%S')} (in {wait_seconds:.0f}s): {url}")

            if len(upcoming) > 5:
                logging.info(f"  ... and {len(upcoming) - 5} more")


async def run():
    """
    runs the Redis pubsub
    publishes new listings to the pubsub channel after every interval
    """
    CONFIG = {
        "connections": {
            "default": f"sqlite://{config['database_path']}/marketplace.sqlite3",
            "shared": config["default_db_url"]
        },
        "apps": {
            "default": {
                "models": ["src.marketplace_notifier.db_models"],
                "default_connection": "default"
            },
            "shared": {
                "models": ["src.shared.models"],
                "default_connection": "shared"
            }
        }
    }
    await Tortoise.init(config=CONFIG)
    await Tortoise.generate_schemas()

    # initialize redis pubsub IPC
    redis_client = redisaio.StrictRedis(host=config["redis_host"])
    tn = TweedehandsNotifier()
    retry_options = ExponentialRetry()  # default retry of 3, retry on all server errors (5xx)
    async with RetryClient(retry_options=retry_options, raise_for_status=False) as cs:
        scheduler = QueryScheduler(tn, cs, redis_client)
        await scheduler.start()


if __name__ == '__main__':
    run_async(run())
