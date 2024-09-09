import asyncio
import json
import logging

import aiohttp
import redis.asyncio as redis
from tortoise import run_async

from db import init
from marketplace_notifier.db_models.models import QueryInfo
from marketplace_notifier.notifier.tweedehands.models import TweedehandsQuerySpecs
from marketplace_notifier.notifier.tweedehands.notifier import TweedehandsNotifier

FETCH_INTERVAL = 5*60  # 5 minutes

async def process_command(channel: redis.client.PubSub):
    """
    redis method to handle received messages
    based on https://redis-py.readthedocs.io/en/stable/examples/asyncio_examples.html#Pub/Sub-Mode
    """
    msg = await channel.get_message(ignore_subscribe_messages=True)
    if msg['type'] != 'message':
        return

    # message should be in form "<command> ..."
    command = msg['data'].decode('utf-8')
    logging.info(f'received command: {command}')
    if command.startswith('ADD_QUERY'):
        # "ADD_QUERY <serialized TweedehandsQuerySpecs object>"
        serialized_tqs = json.loads(command[len('ADD_QUERY '):])
        tqs = TweedehandsQuerySpecs(**serialized_tqs)

        await QueryInfo.create(request_url=tqs.request_query_url, marketplace='TWEEDEHANDS', query=tqs.query)
    elif command.startswith('REMOVE_QUERY'):
        # "REMOVE_QUERY <request_url>"

        request_url = command[len('REMOVE_QUERY '):]
        await QueryInfo.filter(request_url=request_url).delete()


async def run():
    # initialize db tables
    await init()
    # initialize redis pubsub IPC
    redis_client = redis.StrictRedis()

    tn = TweedehandsNotifier()
    async with redis_client.pubsub() as pubsub:
        # listen for incoming redis commands
        await pubsub.subscribe('commands')

        async with aiohttp.ClientSession() as cs:
            while True:
                # listen for redis command to add/remove request_urls before fetching
                await process_command(pubsub)
                request_url_with_listings = await tn.fetch_all_query_urls(cs)
                await tn.process_listings(request_url_with_listings, redis_client)

                await asyncio.sleep(FETCH_INTERVAL)


if __name__ == '__main__':
    run_async(run())
