import asyncio
import json
import logging

import aiohttp
import redis.asyncio as redisaio
from tortoise import run_async
from tortoise.contrib.pydantic import pydantic_model_creator

from db import init
from marketplace_notifier.db_models.models import QueryInfo
from marketplace_notifier.notifier.tweedehands.models import TweedehandsQuerySpecs, TweedehandsLocationFilter
from marketplace_notifier.notifier.tweedehands.notifier import TweedehandsNotifier

FETCH_INTERVAL = 5*60  # 5 minutes

async def process_command(channel: redisaio.client.PubSub, cs: aiohttp.ClientSession):
    """
    redis method to handle received messages
    based on https://redis-py.readthedocs.io/en/stable/examples/asyncio_examples.html#Pub/Sub-Mode
    """
    async for msg in channel.listen():
        if msg['type'] != 'message':
            continue
        # message should be in form "<command> ..."
        command = msg['data'].decode('utf-8')
        logging.info(f'received command: {command}')
        if command.startswith('ADD_QUERY'):
            # "ADD_QUERY {"query": ..., "cityOrPostalCode": ..., "radius": ...}"
            data = json.loads(command[len('ADD_QUERY '):])
            city_and_postal_code = await TweedehandsLocationFilter.get_valid_postal_code_and_city(client_session=cs,
                                                                                                   postal_code_or_city=data['cityOrPostalCode'])
            tlf = TweedehandsLocationFilter(city=city_and_postal_code['city'],
                                            postal_code=city_and_postal_code['postal_code'], radius=data['radius']) if city_and_postal_code else None

            # TODO price range
            tqs = TweedehandsQuerySpecs(query=data['query'], location_filter=tlf)

            qi = await QueryInfo.create(request_url=tqs.request_query_url, marketplace='TWEEDEHANDS', query=tqs.query)
            QueryInfo_Pydantic = pydantic_model_creator(QueryInfo)
            qipy = await QueryInfo_Pydantic.from_tortoise_orm(qi)
            logging.info(f'added query: {qipy.model_dump()}')
        elif command.startswith('REMOVE_QUERY'):
            # "REMOVE_QUERY <request_url>"

            request_url = command[len('REMOVE_QUERY '):]
            await QueryInfo.filter(request_url=request_url).delete()

async def fetch_listings(tn: TweedehandsNotifier, cs: aiohttp.ClientSession, redis_client: redisaio):
    """
    fetches listings once in a while (based on what's in the DB)
    """
    # fetch listings based on request_urls
    while True:
        request_url_with_listings = await tn.fetch_all_query_urls(cs)
        await tn.process_listings(request_url_with_listings, redis_client)
        logging.info(f"Will now sleep for {FETCH_INTERVAL} seconds")
        await asyncio.sleep(FETCH_INTERVAL)

async def run():
    # initialize db tables
    await init()
    # initialize redis pubsub IPC
    redis_client = redisaio.StrictRedis()

    tn = TweedehandsNotifier()
    tasks = []
    async with redis_client.pubsub() as pubsub:
        # listen for incoming redis commands
        await pubsub.subscribe('commands')

        async with aiohttp.ClientSession() as cs:
            # listen for redis command to add/remove request_urls before fetching
            tasks.append(asyncio.create_task(process_command(pubsub, cs)))
            tasks.append(asyncio.create_task(fetch_listings(tn, cs, redis_client)))
            await asyncio.gather(*tasks)

if __name__ == '__main__':
    run_async(run())
