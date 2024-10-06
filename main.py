import asyncio
import logging
from datetime import timedelta, datetime

import aiohttp
import redis.asyncio as redisaio
from tortoise import run_async, Tortoise

from api.webserver import DEFAULT_DB_URL
from config.config import config
from marketplace_notifier.notifier.tweedehands.notifier import TweedehandsNotifier

FETCH_INTERVAL = 5 * 60  # 5 minutes
logging.basicConfig(level=logging.INFO)

async def fetch_listings(tn: TweedehandsNotifier, cs: aiohttp.ClientSession, redis_client: redisaio):
    """
    fetches listings every interval (based on the request_urls in the DB)
    """
    # fetch listings based on request_urls
    while True:
        request_url_with_listings = await tn.fetch_all_query_urls(cs)
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
        db_url=DEFAULT_DB_URL,
        modules={'models': ['marketplace_notifier.db_models.models']}
    )
    await Tortoise.generate_schemas()

    # initialize redis pubsub IPC
    redis_client = redisaio.StrictRedis(host=config["redis_host"])

    tn = TweedehandsNotifier()
    async with aiohttp.ClientSession() as cs:
        await fetch_listings(tn, cs, redis_client)


if __name__ == '__main__':
    run_async(run())
