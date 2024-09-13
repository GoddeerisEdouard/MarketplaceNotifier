from __future__ import annotations
from dataclasses import dataclass
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from marketplace_notifier.postalcode.models import ILocationFilter


# NOTE: these classes are used as input / output models when using functions


class IPriceType(BaseModel, ABC):
    """
    this enum interface represents all price types of a listing
    examples: exact price, bid, not_given
    """
    pass


class PriceInfo(BaseModel, ABC):
    price_type: IPriceType
    price_cents: int


class ListingLocation(BaseModel):
    """
    class representing all Location information of a Listing
    """
    city_name: Optional[str] = Field(None, alias="cityName")
    country_name: Optional[str] = Field(None, alias="countryName")


@dataclass
class IListingInfo(ABC):
    """
    interface represents all relevant listing info
    """
    id: str
    title: str
    price_info: PriceInfo
    description: str
    screenshot_path: Optional[str]
    posted_date: datetime
    seller_url: str
    specified_location: ListingLocation
    vip_url: str

    @property
    @abstractmethod
    def BASE_URL(self) -> str:
        raise NotImplementedError()

    def get_full_url(self) -> str:
        """
        :return: full URL hyperlink to listing for user
        """
        return self.BASE_URL + self.vip_url


@dataclass
class PriceRange:
    min_price_cents: int
    max_price_cents: int



class IQuerySpecs(BaseModel, ABC):
    """
    query specifications given by user
    these will be parsed into a URL to make a GET REQUEST
    """
    query: str
    location_filter: Optional[ILocationFilter] = None
    price_range: Optional[PriceRange] = None

    @property
    @abstractmethod
    def request_query_url(self) -> str:
        """
        generates request URL based on the given attributes
        does the opposite of parse_request_url
        :return: a listing query url to use for a GET request
        """
        raise NotImplementedError()

    @property
    @abstractmethod
    def browser_query_url(self) -> str:
        """
        generates the URL a user can use in his browser to find all listings based on his query
        :return: url a user can use in his browser
        """
        raise NotImplementedError()

    @classmethod
    @abstractmethod
    def parse_request_url(cls, get_request_query_url: str) -> IQuerySpecs:
        """
        parses webbrowser url and returns object of this dataclass
        ( does the opposite of browser_query_url )
        :param get_request_query_url: the url to parse
        :return: this dataclass
        """
        raise NotImplementedError()
