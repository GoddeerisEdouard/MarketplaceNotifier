import asyncio

import aiohttp
from tortoise import run_async

from db import init
from marketplace_notifier.notifier.tweedehands.notifier import TweedehandsNotifier

FETCH_INTERVAL = 5*60  # 5 minutes

async def run():
    # initialize db tables
    await init()

    tn = TweedehandsNotifier()
    async with aiohttp.ClientSession() as cs:
        while True:
            request_url_with_listings = await tn.fetch_all_query_urls(cs)
            await tn.process_listings(request_url_with_listings)

            await asyncio.sleep(FETCH_INTERVAL)


if __name__ == '__main__':
    run_async(run())
