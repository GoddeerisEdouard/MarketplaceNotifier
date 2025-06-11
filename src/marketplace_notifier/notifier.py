import asyncio
import logging
import re
from typing import List, Optional, Dict, Any

import redis.asyncio as redis
from aiohttp_retry import RetryClient

from utils.api_utils import get_request_response
from src.shared.models import QueryInfo
from src.marketplace_notifier.db_models import ListingInfoDB


class TweedehandsNotifier:
    def __init__(self):
        self.listing_urls_for_requests = []

    async def fetch_all_request_urls(self, retry_client: RetryClient) -> Dict[
        str, List[Optional[Dict[Any, Any]]]]:
        """
        fetches the listings of all query urls
        :param retry_client: session to use the send GET requests
        :return: {<query_url>: [<Listings>]}
        """
        # update cached listing_urls
        self.listing_urls_for_requests = set(await QueryInfo.all().values_list("request_url", flat=True))
        logging.info(f'fetching listings for {len(self.listing_urls_for_requests)} request urls...')

        # Create async tasks for each request URL
        async def fetch_for_url(request_url):
            return request_url, await get_request_response(retry_client, request_url)

        # Run all requests concurrently
        tasks = [fetch_for_url(request_url) for request_url in self.listing_urls_for_requests]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        query_url_listings_dict = {}
        for result in results:
            if isinstance(result, Exception):
                logging.error(f"Error fetching listings: {result}")
                continue
            request_url, response = result
            query_url_listings_dict[request_url] = response["listings"]

        return query_url_listings_dict

    async def process_listings(self, request_url_all_listings_dict: Dict[
        str, List[Dict[Any, Any]]], async_redis_client: redis.client) -> None:
        """
        stores some attributes of listing in DB
        publishes new listings to redis pubsub channel
        """
        for request_url, listings_of_query_url in request_url_all_listings_dict.items():
            logging.info(f'processing {request_url}...')
            # it might take a while for every query_url to be processed
            qi_exists = await QueryInfo.exists(request_url=request_url)
            if not qi_exists:
                logging.warning(f"request url {request_url} was removed from the DB while processing...")
                continue

            # sort listings from OLD to NEW
            # we do this by checking the ID (format m<numbers> )
            # example: m123 is newer than m100 (because 123 comes after 100)
            # so the smallest number will be first in list (as it's the oldest)
            listings_of_query_url.sort(key=lambda li: int(re.search(r"\d+", li["itemId"]).group(0)))
            new_listings = []

            latest_listing_for_request_url = await ListingInfoDB.filter(request_url=request_url).order_by('-item_id').first()

            latest_listing_id = int(latest_listing_for_request_url.item_id[1:]) if latest_listing_for_request_url else 0 # remove 'm' prefix



            for listing in listings_of_query_url:
                listing_id = int(listing["itemId"][1:]) # remove 'm' prefix
                if listing_id <= latest_listing_id:
                    logging.info("no newer listings found for this request URL.")
                    break

                exists = await ListingInfoDB.exists(request_url=request_url, item_id=listing["itemId"])
                if exists:
                    logging.info(f'listing already seen for this request url: <title:{listing["title"]}, id:{listing["itemId"]}>')
                    continue

                logging.info(f'new listing found for request url: <request_url:{request_url}, title:{listing["title"]}, id:{listing["itemId"]}>')
                new_listings.append(listing)
                listing_info_db_obj = ListingInfoDB(item_id=listing["itemId"], title=listing["title"], request_url=request_url)
                # update latest listing ID in DB
                await listing_info_db_obj.save()

            if not new_listings:
                logging.info(f'no new listings for {request_url}')
                continue

            logging.info(f'found {len(new_listings)} new listings for {request_url}, publishing to redis...')
            msg = f"{request_url} {new_listings}"
            # this will throw a redis.exceptions.ConnectionError if redis is not running
            await async_redis_client.publish('listings', msg)