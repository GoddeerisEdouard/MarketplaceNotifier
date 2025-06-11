import asyncio
import json
import logging
import traceback
from datetime import timedelta, datetime

from marketplace_notifier.utils.api_utils import get_request_response
from src.shared.models import QueryInfo


class QueryScheduler:
    """
    Scheduler that manages fetching queries at scheduled intervals.
    this is to prevent spamming the 2dehands API at the same time
    """

    def __init__(self, notifier, retry_client, redis_client, interval):
        self.notifier = notifier
        self.retry_client = retry_client
        self.redis_client = redis_client
        self.interval = interval
        self.tasks = {}  # Maps query URL to next scheduled time
        self.running = True

    async def _schedule_new_query(self, url):
        # we schedule it immediatly the first time
        next_time = datetime.now()
        self.tasks[url] = next_time
        logging.info(f"Initial query scheduled for {next_time.strftime('%H:%M:%S')}: {url}")

        # Update the next check time in the database
        await QueryInfo.filter(request_url=url).update(next_check_time=next_time)

    async def start(self):
        """Start the scheduler and monitor for changes in queries"""

        await self._initialize_query_schedule()

        while self.running:
            healthy_request_urls = await QueryInfo.filter(is_healthy=True).values_list("request_url", flat=True)
            if not healthy_request_urls:
                logging.info("No (healthy) queries found, sleeping...")
                await asyncio.sleep(10)
                continue

            removed_urls = set(self.tasks.keys()) - set(healthy_request_urls)

            # remove tasks for URLs that no longer exist
            for url in removed_urls:
                logging.info(f"Query removed from monitoring: {url}")
                self.tasks.pop(url, None)

            # add new queries that aren't being tracked yet
            new_urls = set(healthy_request_urls) - set(self.tasks.keys())
            for new_url in new_urls:
                await self._schedule_new_query(new_url)

            # process queries that are ready to fetch
            await self._process_ready_queries()

            # log upcoming schedule
            self._log_schedule()

            # wait a bit before checking again
            await asyncio.sleep(10)

    async def _initialize_query_schedule(self):
        """
        Initialize the schedule by spreading queries evenly across the interval.
        """
        now = datetime.now()
        healthy_request_urls = await QueryInfo.filter(is_healthy=True).values_list("request_url", flat=True)

        if not healthy_request_urls:
            logging.info("No healthy queries found to initialize.")
            return

        # Calculate the spread interval
        spread_interval = self.interval / max(len(healthy_request_urls), 1)

        for i, url in enumerate(healthy_request_urls):
            # Schedule each query at evenly spaced intervals
            next_time = now + timedelta(seconds=i * spread_interval)
            self.tasks[url] = next_time
            logging.info(f"Initial query scheduled for {next_time.strftime('%H:%M:%S')}: {url}")

            # Update the next check time in the database
            await QueryInfo.filter(request_url=url).update(next_check_time=next_time)

    async def _process_ready_queries(self):
        """Process all queries that are ready to be fetched"""
        now = datetime.now()
        ready_urls = [url for url, time in self.tasks.items() if time <= now]
        if len(ready_urls) > 1:
            queries = await QueryInfo.filter(is_healthy=True)
            logging.warning(
                f"Too many URLs being fetched at once: {len(ready_urls)} queries to fetch of {len(queries)} healthy queries")
            await self.redis_client.publish("error_channel", json.dumps({
                "error": f"Too many urls being fetched at once: {len(ready_urls)}\nBe aware of ratelimiting!",
                "reason": f"urls 'next_time' aren't spread well enough, currently {len(queries)} healthy queries"
            }))

        # Find the last scheduled time
        last_scheduled_time = max(self.tasks.values(), default=now)

        spread_interval = self.interval / max(len(self.tasks), 1)
        # this should hopefully not be a big list
        for i, url in enumerate(ready_urls):
            try:
                logging.info(f"Fetching: {url}")

                result = await get_request_response(self.retry_client, url)
                await self.notifier.process_listings({url: result["listings"]}, self.redis_client)

                # reschedule for next interval
                # we just add the interval to the current time
                next_time = last_scheduled_time + timedelta(seconds=(i + 1) * spread_interval)
                self.tasks[url] = next_time
                self.tasks[url] = next_time
                logging.info(f"Next fetch scheduled for {next_time.strftime('%H:%M:%S')}: {url}")

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
