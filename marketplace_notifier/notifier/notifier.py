import json
import logging
from abc import ABC, abstractmethod
from typing import List, Optional, Type

import aiohttp

from marketplace_notifier.notifier.models import IListingInfo, IQuerySpecs
from marketplace_notifier.utils.api_utils import get_request_response


class INotifier(ABC):
    """
    interface of marketplace notifier
    """
    # TODO: add unique ID to every element in this list to be able to easily remove them
    # (maybe based on name or something, just a generated name, can be the vip url too)
    # the request url is not enough, as it looks different for the developer than for the user
    # these urls are to fetch ALL listings of a specific spec
    # example:
    # browser URL req: .../q/nintendo+switch
    # GET req URL: .../lrp/api/search?attributesByKey[]=Language%3Aall-languages&limit=30&offset=0&query=nintendo%20switch&searchInTitleAndDescription=true&viewOptions=list-view
    listing_urls_for_requests: List[str] = []

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

    async def _add_new_query(self, listing_specs: Type[IQuerySpecs]) -> None:
        """
        helper method
        adds parsed "listing query"/~listing_specs to notifier lising query list
        :return: None
        """

        request_url = listing_specs.request_query_url

        # append to query request list to refresh every now & then
        # TODO: add unique ID for this URL, so we can easily remove it later on
        # as spoken about in INotifier
        self.listing_urls_for_requests.append(request_url)

    async def fetch_listings_of_request_url(self, client_session: aiohttp.ClientSession, query_request_url: str) -> \
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
