from abc import ABC, abstractmethod
from typing import List, Optional

import aiohttp

from marketplace_notifier.notifier.models import IListingInfo, IListingSpecs


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
    async def _parse_listings_from_response(self, client_session: aiohttp.ClientSession, get_req_url: str) -> List[
        Optional[IListingInfo]]:
        """
        helper method
        gets a raw json response with all listings of query & returns IListingInfo objects
        :param client_session: session to use the send GET requests
        :param get_req_url: exact GET url to request all raw listings json
        :return: a (empty) list of IListingInfo objects
        """
        raise NotImplementedError()

    @abstractmethod
    async def add_new_query(self, listing_specs: IListingSpecs) -> None:
        """
        adds parsed "listing query"/~listing_specs to notifier lising query list
        :return: None
        """

        request_url = listing_specs.generate_listing_query_url()

        # append to query request list to refresh every now & then
        self.listing_urls_for_requests.append(request_url)

    @abstractmethod
    async def get_listings_of_request_url(self, client_session: aiohttp.ClientSession, query_request_url: str) -> List[
        IListingInfo]:
        """
        gets all listings and returns all parsed relevant listing info in a list
        :param client_session: session to use the send GET requests
        :param query_request_url: exact GET request url used to get all listings
        :return: parsed listing info as dataclass object
        """

        new_listings = await self._parse_listings_from_response(client_session, query_request_url)
        return new_listings
