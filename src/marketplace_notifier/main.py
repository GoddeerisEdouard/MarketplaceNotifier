import asyncio
import logging
import sys
from datetime import timedelta, datetime

from aiohttp_retry import RetryClient, ExponentialRetry
import redis.asyncio as redisaio
from tortoise import run_async, Tortoise

from config.config import config
from notifier.tweedehands.notifier import TweedehandsNotifier

FETCH_INTERVAL = 5 * 60  # 5 minutes
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

async def fetch_listings(tn: TweedehandsNotifier, rc: RetryClient, redis_client: redisaio):
    """
    fetches listings every interval (based on the request_urls in the DB)
    """
    # fetch listings based on request_urls
    while True:
        request_url_with_listings = await tn.fetch_all_query_urls(rc)
        await tn.process_listings(request_url_with_listings, redis_client)
        in_x_seconds = datetime.now() + timedelta(seconds=FETCH_INTERVAL)
        logging.info(f"Will now sleep until {in_x_seconds.strftime('%H:%M:%S')}")
        await asyncio.sleep(FETCH_INTERVAL)


async def run():
    """
    runs the Redis pubsub
    sends new listings to the pubsub channel after every interval
    """
    await Tortoise.init(
        db_url=config["default_db_url"],
        modules={'models': ['src.shared.models']}
    )
    await Tortoise.generate_schemas()

    # initialize redis pubsub IPC
    redis_client = redisaio.StrictRedis(host=config["redis_host"])

    tn = TweedehandsNotifier()
    retry_options = ExponentialRetry() # default retry of 3, retry on all server errors (5xx)
    async with RetryClient(retry_options=retry_options, raise_for_status=False) as cs:
        await fetch_listings(tn, cs, redis_client)


if __name__ == '__main__':
    run_async(run())
