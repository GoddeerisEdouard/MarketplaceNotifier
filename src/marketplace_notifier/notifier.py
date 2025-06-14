import asyncio
import json
import logging
from typing import List, Optional, Dict, Any

import redis.asyncio as redis
from aiohttp_retry import RetryClient

from src.shared.api_utils import get_request_response
from src.shared.models import QueryInfo
from src.marketplace_notifier.db_models import LatestListingInfoDB


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
        for request_url, listings_of_request_url in request_url_all_listings_dict.items():
            logging.info(f'processing {request_url}...')
            # it might take a while for every query_url to be processed
            qi_exists = await QueryInfo.exists(request_url=request_url)
            if not qi_exists:
                logging.warning(f"request url {request_url} was removed from the DB while processing...")
                continue

            latest_listing_for_request_url = await LatestListingInfoDB.filter(
                request_url=request_url).get_or_none()  # should only be one
            # 0 if there is no latest listing for this request_url
            latest_listing_id = int(latest_listing_for_request_url.item_id[
                                    1:]) if latest_listing_for_request_url else 0  # remove 'm' prefix

            # filter out ad listings & older (than latest DB listing) listings
            new_non_ad_listings_of_request_url = [listing for listing in listings_of_request_url if
                                                  listing.get("priorityProduct") == "NONE" and int(
                                                      listing.get("itemId")[1:]) > latest_listing_id]
            if not new_non_ad_listings_of_request_url:
                logging.info(f'no new NON-AD listings for request_url: {request_url}')
                continue

            total_non_ad_new_listings = len(new_non_ad_listings_of_request_url)

            # sort listings from NEW to OLD (biggest number first)
            # we do this by checking the ID (format m<numbers> )
            # example: m123 is newer than m100 (because 123 comes after 100)
            new_non_ad_listings_of_request_url.sort(key=lambda li: int(li["itemId"][1:]), reverse=True)  # remove 'm' prefix

            logging.info(
                f'found {total_non_ad_new_listings} NEW NON-AD /{len(listings_of_request_url)} TOTAL listings for {request_url}')

            for i, listing in enumerate(new_non_ad_listings_of_request_url):
                logging.info(f'{i + 1}. listing for request url: <title:{listing["title"]}, id:{listing["itemId"]}>')
                if i == 0:
                    # save item_id of latest listing to DB
                    if latest_listing_for_request_url is None:
                        lidb_obj = LatestListingInfoDB(request_url=request_url,item_id=listing["itemId"], title=listing["title"])
                        await lidb_obj.save()
                        logging.info(f"set latest item_id to <{listing['itemId']}, title: {listing['title']}>")
                    else:
                        latest_listing_for_request_url.item_id = listing["itemId"]
                        latest_listing_for_request_url.title = listing["title"]
                        await latest_listing_for_request_url.save()

                        logging.info(f"updated latest item_id to <{listing['itemId']}, title: {listing['title']}>")

            logging.info(
                f'found {total_non_ad_new_listings} new NON-AD listings for {request_url}, publishing to redis...')
            msg = {"request_url": request_url, "new_listings": new_non_ad_listings_of_request_url}
            # this will throw a redis.exceptions.ConnectionError if redis is not running

            await async_redis_client.publish('listings', json.dumps(msg))
