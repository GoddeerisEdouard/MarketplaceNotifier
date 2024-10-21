import json
import logging
import re
from abc import ABC, abstractmethod
from dataclasses import asdict
from typing import List, Optional, Type, Set, Dict

import aiohttp
import redis.asyncio as redis

from marketplace_notifier.db_models.models import QueryInfo, ListingInfo as ListingInfoDB
from marketplace_notifier.notifier.models import IListingInfo, IQuerySpecs
from marketplace_notifier.utils.api_utils import get_request_response


class INotifier(ABC):
    """
    interface of marketplace notifier
    """
    # looks like {"req_url1", "req_url2", ...}
    listing_urls_for_requests: Set[str] = {}

    @property
    @abstractmethod
    def marketplace(self) -> str:
        """
        :return: name of marketplace
        """
        raise NotImplementedError

    @abstractmethod
    def _parse_non_ad_listings(self, raw_listings_response) -> List[Optional[IListingInfo]]:
        """
        helper method
        :param raw_listings_response: expected raw data format
        :return: parsed List of non-ad IListingInfo objects
        """

        raise NotImplementedError()

    async def _parse_listings_from_response(self, client_session: aiohttp.ClientSession, get_req_url: str) -> List[
        Optional[IListingInfo]]:
        """
        helper method
        gets a raw json response with all listings of query & returns IListingInfo objects
        :param client_session: session to use the send GET requests
        :param get_req_url: GET request url to fetch all raw listings in json
        :return: a (empty) list of IListingInfo objects
        """
        response_data = await get_request_response(client_session, get_req_url)
        if response_data == "":
            logging.warning(f"No response data, here's the request URL you tried:\n{get_req_url}")
            return []
        data = None
        try:
            data = json.loads(response_data)
        except TypeError:
            logging.warning(f"Couldn't decode data of url {get_req_url}\n---\ndata:\n{response_data}")
        except json.JSONDecodeError as e:
            logging.warning(f"Couldn't decode json for given uri {get_req_url}\n---\ndata:\n{response_data}\n{e}")
        except Exception as e:
            logging.warning(f"Unhandled exception: {e}")

        # only return listings which aren't ads
        parsed_non_ad_listings = self._parse_non_ad_listings(data)

        # if there are no non-ad listings found
        if not parsed_non_ad_listings:
            logging.debug("no non-ad listings found")

        return parsed_non_ad_listings

    async def add_new_query(self, listing_specs: Type[IQuerySpecs]) -> None:
        """
        helper method
        inserts new request url in DB
        when fetching new queries, the new_request_url will be updated
        :return: None
        """

        request_url = listing_specs.request_query_url
        await QueryInfo.create(request_url=request_url, marketplace=self.marketplace, query=listing_specs.query)

    async def _fetch_listings_of_request_url(self, client_session: aiohttp.ClientSession, query_request_url: str) -> \
            List[
                Optional[Type[IListingInfo]]]:
        """
        fetches all listings and returns all parsed relevant listing info in a list
        :param client_session: session to use the send GET requests
        :param query_request_url: exact GET request url used to get all listings
        :return: list of parsed non-ad listing info objects
        """

        new_non_ad_listings_infos = await self._parse_listings_from_response(client_session, query_request_url)
        return new_non_ad_listings_infos

    async def fetch_all_query_urls(self, client_session: aiohttp.ClientSession) -> Dict[
        str, List[Optional[Type[IListingInfo]]]]:
        """
        fetches the listings of all query urls
        :param client_session: session to use the send GET requests
        :return: {<query_url>: [<IListingInfo> non-ad listings]}
        """
        # update cached listing_urls
        self.listing_urls_for_requests = set(await QueryInfo.all().values_list("request_url", flat=True))
        logging.info(f'fetching listings for {len(self.listing_urls_for_requests)} query urls...')

        query_url_listing_infos: Dict[str, List[Optional[Type[IListingInfo]]]] = {}
        for request_url in self.listing_urls_for_requests:
            parsed_non_ad_listings = await self._fetch_listings_of_request_url(client_session, request_url)
            query_url_listing_infos[request_url] = parsed_non_ad_listings

        return query_url_listing_infos

    async def process_listings(self, query_url_listing_infos: Dict[
        str, List[Optional[Type[IListingInfo]]]], async_redis_client: redis.client) -> None:
        """
        stores some attributes of listing in DB
        sends new listings with restricted attributes to subscribers
        """
        for query_url, non_ad_listings_infos in query_url_listing_infos.items():
            logging.info(f'processing {query_url}...')
            # it might take a while for every query_url to be processed
            qi_exists = await QueryInfo.exists(request_url=query_url)
            if not qi_exists:
                logging.warning(f"query url {query_url} was removed from the DB while processing...")
                continue
            new_parsed_listings_infos = []
            for parsed_listing_info in non_ad_listings_infos:
                exists = await ListingInfoDB.exists(id=parsed_listing_info.id)
                if exists:
                    logging.info(f'listing already exists: {parsed_listing_info}')
                    continue

                logging.info(f'new listing found: {asdict(parsed_listing_info)}')

                # convert parsed_listings to db listinginfo
                listing_info_db_obj = ListingInfoDB(id=parsed_listing_info.id, title=parsed_listing_info.title,
                                                    marketplace=self.marketplace,
                                                    date=parsed_listing_info.posted_date)
                # save listing in db
                await listing_info_db_obj.save()
                new_parsed_listings_infos.append(parsed_listing_info)

            if len(new_parsed_listings_infos) == 0:
                continue

            # order listings from OLD to NEW
            # we do this by checking the ID (format m<numbers> )
            # example: m123 is newer than m100 (because 123 comes after 100)
            # so the smallest number will be first in list (as it's the oldest)
            new_parsed_listings_infos.sort(key=lambda li: int(re.search(r"\d+", li.id).group(0)))
            serialized_tweedehands_listing_infos = [li.to_json() for li in new_parsed_listings_infos]
            command = "NEW"
            data = json.dumps({"listings": serialized_tweedehands_listing_infos})
            msg = " ".join([command, query_url, data])
            await async_redis_client.publish('listings', msg)
