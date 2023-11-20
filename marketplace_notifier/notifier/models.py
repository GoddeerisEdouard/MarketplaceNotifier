from __future__ import annotations
from dataclasses import dataclass
from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# NOTE: these classes are used as input / output models when using functions


class IPriceType(BaseModel, ABC, Enum):
    """
    this enum interface represents all price types of a listing
    examples: exact price, bid, not_given
    """
    pass


class PriceInfo(BaseModel, ABC):
    price_type: IPriceType
    price_cents: int


class Location(BaseModel):
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
    _BASE_URL: str
    title: str
    price_info: PriceInfo
    description: str
    screenshot_path: str
    posted_date: datetime
    seller_url: str
    specified_location: Location
    vip_url: str

    def get_full_url(self) -> str:
        """
        :return: full URL hyperlink to listing
        """
        return self._BASE_URL + self.vip_url


@dataclass
class PriceRange:
    min_price_cents: int
    max_price_cents: int


@dataclass
class IListingSpecs(ABC):
    """
    listing specifications given by user
    these will be parsed into a URL to make a GET REQUEST
    """
    query: str
    location: Location
    price_range: PriceRange = PriceRange(0, 0)

    @abstractmethod
    def generate_listing_query_url(self) -> str:
        """
        generates request URL based on the given attributes
        ( does the opposite of parse_url(...) )
        :return: a listing query url to use for a GET request
        """
        raise NotImplementedError()

    @classmethod
    @abstractmethod
    def parse_url(cls, get_request_query_url: str) -> IListingSpecs:
        """
        parses url and returns object of this dataclass
        ( does the opposite of get_request_url(...) )
        :param get_request_query_url: the url to parse
        looks like .../q/iphone/#Language:all-languages|sortBy:SORT_INDEX|sortOrder:DECREASING|postcode:9000|searchInTitleAndDescription:true
        or
        .../q/iphone/#Language:all-languages|PriceCentsTo:5000|sortBy:SORT_INDEX|sortOrder:DECREASING|postcode:9000|searchInTitleAndDescription:true
        :return: this dataclass, parsed by current url
        """
        raise NotImplementedError()
