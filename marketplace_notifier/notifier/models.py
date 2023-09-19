from dataclasses import dataclass
from abc import ABC
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# NOTE: these classes are used as returnmodels when using functions


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
class IListingInfo(BaseModel, ABC):
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

    def get_link(self) -> str:
        return self._BASE_URL + self.vip_url
