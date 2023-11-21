import json
import re
import urllib.parse
from datetime import datetime
from enum import Enum
from typing import Optional, List

import pydantic
import aiohttp
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field, field_validator, HttpUrl

from marketplace_notifier.utils.api_utils import get_request_response

# Postalcode API related
BELGIAN_POSTAL_CODE_REGEX = "^[1-9]{1}[0-9]{3}$"
BELGIAN_CITY_REGEX = "^[A-Za-zÀ-ÿ\\.'*`´’,\\- \"]{1,34}$"


class PostalCodeAPIResponseModel(BaseModel):
    postcode_hoofdgemeente: str
    naam_hoofdgemeente: str
    postcode_deelgemeente: str
    naam_deelgemeente: str
    taal: str
    region: str
    longitude: str
    latitude: str

    class Config:
        str_to_lower = True


BelgianCityType = pydantic.constr(pattern=BELGIAN_CITY_REGEX)


class LocationFilter(BaseModel):
    """
    class representing parsed location filters
    """
    city: BelgianCityType = Field(..., description="Valid belgian city name")
    postal_code: int = Field(..., description="Valid belgian postal code")
    radius: int

    @classmethod
    async def get_valid_postal_code_and_city(cls, client_session: aiohttp.ClientSession,
                                             postal_code_or_city: str) -> Optional[dict]:
        """
        helper method to get the postal code of a given city or the city of a given postal code
        city can be either in French or Dutch
        :param client_session: used to make the GET request for the postal code data
        :param postal_code_or_city: a postal code or a city (Dutch or French)
        :return: None if invalid postal_code_or_city, else a dict of  the postal code with its matching city in Dutch
        """

        postal_code_or_city_normalized = str(postal_code_or_city).lower()
        # prevent GET requests for invalid postal code / city
        if not re.match(f"{BELGIAN_CITY_REGEX}|{BELGIAN_POSTAL_CODE_REGEX}", postal_code_or_city_normalized):
            return

        api_url = f"https://opzoeken-postcode.be/{urllib.parse.quote_plus(postal_code_or_city_normalized)}.json"
        response = await get_request_response(client_session, api_url)
        response_json = json.loads(response)
        if response_json:
            for postal_code_and_city_model in response_json:
                postal_code_and_city_model_obj = PostalCodeAPIResponseModel.model_validate(
                    postal_code_and_city_model["Postcode"])

                # check if any postal code or city matches the given postal code, if it does, return that element
                if postal_code_and_city_model_obj.postcode_hoofdgemeente == postal_code_or_city_normalized \
                        or postal_code_and_city_model_obj.postcode_deelgemeente == postal_code_or_city_normalized:
                    return {"postal_code": int(postal_code_and_city_model_obj.postcode_hoofdgemeente),
                            "city": postal_code_and_city_model_obj.naam_hoofdgemeente.capitalize()}

                elif postal_code_and_city_model_obj.naam_hoofdgemeente == postal_code_or_city_normalized \
                        or postal_code_and_city_model_obj.naam_deelgemeente == postal_code_or_city_normalized:
                    return {"postal_code": int(postal_code_and_city_model_obj.postcode_hoofdgemeente),
                            "city": postal_code_and_city_model_obj.naam_hoofdgemeente.capitalize()}

    @field_validator("radius")
    def distance_converter(cls, v: int) -> int:
        """
        only allow tweedehands / 2ememain 's GUI distance input values and convert to closest match
        """
        RADIUS_LIST = [3, 5, 10, 15, 25, 50, 75]
        return RADIUS_LIST[min(range(len(RADIUS_LIST)), key=lambda i: abs(RADIUS_LIST[i] - v))]

    @field_validator("postal_code")
    def belgian_postal_code_validation(cls, v: int) -> int:
        if not re.match(BELGIAN_POSTAL_CODE_REGEX, str(v)):
            raise ValueError(f"{v} is not a valid belgian postal code")
        return v


# Tweedehands API related
class ListingInfo(BaseModel):
    """
    class representing parsed (relevant) info to use for API calls
    """
    query: str
    location_filter: Optional[LocationFilter] = None

    @property
    def query_url(self) -> str:
        URI = "https://www.2dehands.be/lrp/api/search?attributesByKey[]=Language%3Aall-languages" \
              f"&attributesByKey[]=offeredSince%3AGisteren&limit=30&offset=0&query={urllib.parse.quote_plus(self.query)}" \
              "&searchInTitleAndDescription=true&sortBy=SORT_INDEX&sortOrder=DECREASING&viewOptions=list-view"
        if self.location_filter:
            URI += f"&distanceMeters={str(self.location_filter.radius * 1000)}&postcode={str(self.location_filter.postal_code)}"
        return URI

    @classmethod
    def get_field_names_dict(cls):
        return dict.fromkeys(cls.__fields__.keys())


class PriceTypeEnum(str, Enum):
    """
    represents all possible price types of Listings
    """
    FIXED = "FIXED"
    SEE_DESCRIPTION = "SEE_DESCRIPTION"
    MIN_BID = "MIN_BID"
    NOTK = "NOTK"
    ON_REQUEST = "ON_REQUEST"
    FAST_BID = "FAST_BID"
    FREE = "FREE"
    RESERVED = "RESERVED"
    EXCHANGE = "EXCHANGE"

    def should_be_displayed(self) -> bool:
        """
        whether the type should be displayed on the 2dehands website
        else, it's just the price
        """
        return self in [self.SEE_DESCRIPTION, self.NOTK, self.FAST_BID, self.ON_REQUEST, self.FREE, self.RESERVED,
                        self.EXCHANGE]

    def human_readable(self) -> str:
        """
        converts selected Enum to human readable format
        :return: string with human readable format
        """
        converter = {self.SEE_DESCRIPTION: "Zie omschrijving",
                     self.NOTK: "o.t.k.",
                     self.FAST_BID: "Bieden",
                     self.ON_REQUEST: "Op aanvraag",
                     self.FREE: "Gratis",
                     self.RESERVED: "Gereserveerd",
                     self.EXCHANGE: "Ruilen"}
        if self.name not in converter:
            raise ValueError("No need to convert to human readable format when price is displayed!")

        return converter[self]


# generated from query url response

class PriceInfo(BaseModel):
    """
    class representing all price info of a Listing
    """
    price_cents: int = Field(..., alias="priceCents")
    price_type: PriceTypeEnum = Field(..., alias="priceType")

    @property
    def human_readable_price(self) -> str:
        if self.price_type.should_be_displayed():
            return self.price_type.human_readable()

        formatted_price = f"€{self.price_cents / 100:,.2f}"
        fractional_separator = ","
        main_currency, fractional_currency = formatted_price.split(".")[0], formatted_price.split(".")[1]
        new_main_currency = main_currency.replace(",", ".")
        currency = new_main_currency + fractional_separator + fractional_currency
        return currency


class Location(BaseModel):
    """
    class representing all Location information of a Listing
    """
    city_name: Optional[str] = Field(None, alias="cityName")
    country_name: Optional[str] = Field(None, alias="countryName")
    country_abbreviation: Optional[str] = Field(None, alias="countryAbbreviation")
    distance_meters: int = Field(..., alias="distanceMeters")
    is_buyer_location: bool = Field(..., alias="isBuyerLocation")
    on_country_level: bool = Field(..., alias="onCountryLevel")
    abroad: bool
    latitude: float
    longitude: float


class SellerInformation(BaseModel):
    """
    class representing all seller information of a Listing
    """
    seller_id: int = Field(..., alias="sellerId")
    seller_name: str = Field(..., alias="sellerName")
    show_soi_url: bool = Field(..., alias="showSoiUrl")
    show_website_url: bool = Field(..., alias="showWebsiteUrl")
    is_verified: bool = Field(..., alias="isVerified")


class Attribute(BaseModel):
    key: str
    value: str


class AspectRatio(BaseModel):
    width: int
    height: int


class Picture(BaseModel):
    """
    class representing all picture formats of a Listing
    """
    id: int
    extra_small_url: HttpUrl = Field(..., alias="extraSmallUrl")
    medium_url: HttpUrl = Field(..., alias="mediumUrl")
    large_url: HttpUrl = Field(..., alias="largeUrl")
    extra_extra_large_url: HttpUrl = Field(..., alias="extraExtraLargeUrl")
    aspect_ratio: AspectRatio = Field(..., alias="aspectRatio")


class PriorityProductEnum(str, Enum):
    NONE = "NONE"
    DAGTOPPER = "DAGTOPPER"
    TOPADVERTENTIE = "TOPADVERTENTIE"


class TraitEnum(str, Enum):
    """
    class representing all traits a Listing can have
    """
    DAG_TOPPER_28DAYS = "DAG_TOPPER_28DAYS"
    PROFILE = "PROFILE"
    NO_COMMERCIAL_CONTENT = "NO_COMMERCIAL_CONTENT"
    PACKAGE_PREMIUM = "PACKAGE_PREMIUM"
    DAG_TOPPER_7DAYS = "DAG_TOPPER_7DAYS"
    URL = "URL"
    PACKAGE_PLUS = "PACKAGE_PLUS"
    EXTRA_IMAGES_SNIPPET = "EXTRA_IMAGES_SNIPPET"
    DAG_TOPPER_3DAYS = "DAG_TOPPER_3DAYS"
    PACKAGE_FREE = "PACKAGE_FREE"
    CUSTOMER_SUPPORT_BUSINESS_LINE = "CUSTOMER_SUPPORT_BUSINESS_LINE"
    SHOPPING_CART = "SHOPPING_CART"
    ADMARKT_CONSOLE = "ADMARKT_CONSOLE"
    DAG_TOPPER = "DAG_TOPPER"
    VERIFIED_SELLER = "VERIFIED_SELLER"
    MICROTIP = "MICROTIP"
    NO_MARKETING = "NO_MARKETING"
    UNIQUE_SELLING_POINTS = "UNIQUE_SELLING_POINTS"
    IMAGES_GALLERY = "IMAGES_GALLERY"
    SELLER_PROFILE_URL = "SELLER_PROFILE_URL"
    EXTRA_BRANDING = "EXTRA_BRANDING"
    TRADE_IN_REQUEST_AVAILABLE = "TRADE_IN_REQUEST_AVAILABLE"
    WARRANTY_LABEL = "WARRANTY_LABEL"
    FEED_BOOSTER_HIGH = "FEED_BOOSTER_HIGH"
    TEST_DRIVE_REQUEST_AVAILABLE = "TEST_DRIVE_REQUEST_AVAILABLE"
    CALL_BACK_REQUEST_AVAILABLE = "CALL_BACK_REQUEST_AVAILABLE"
    FINANCE_AVAILABLE = "FINANCE_AVAILABLE"
    VIDEO = "VIDEO"
    REQUEST_BUYER_LOCATION_IN_ASQ = "REQUEST_BUYER_LOCATION_IN_ASQ"
    EXTRA_LARGE_PHOTOS = "EXTRA_LARGE_PHOTOS"
    HIGHLIGHTS = "HIGHLIGHTS"
    CONTACT_SALES_REPRESENTATIVES = "CONTACT_SALES_REPRESENTATIVES"
    DEALER_PACKAGE_PREMIUM = "DEALER_PACKAGE_PREMIUM"
    EXTERNAL_REVIEWS = "EXTERNAL_REVIEWS"
    NO_RESPONSE_TIME_IN_VIP = "NO_RESPONSE_TIME_IN_VIP"
    COMPANY_PHOTO_AND_LOGO = "COMPANY_PHOTO_AND_LOGO"
    PACKAGE_BASIC = "PACKAGE_BASIC"
    ETALAGE = "ETALAGE"
    URGENCY = "URGENCY"
    DEALER_PACKAGE_BASIC = "DEALER_PACKAGE_BASIC"
    FEED_BOOSTER_REMOVER = "FEED_BOOSTER_REMOVER"
    HIGHLIGHT_SERVICE_HISTORY = "HIGHLIGHT_SERVICE_HISTORY"


class Listing(BaseModel):
    """
    class representing a parsed listing from the API
    """
    item_id: str = Field(..., alias="itemId")
    title: str
    description: str
    price_info: PriceInfo = Field(..., alias="priceInfo")
    location: Location
    # date can be None and has to be set later via set_posted_date
    date: Optional[datetime] = None
    image_urls: Optional[List[str]] = Field(None, alias="imageUrls")
    seller_information: SellerInformation = Field(..., alias="sellerInformation")
    category_id: int = Field(..., alias="categoryId")
    priority_product: PriorityProductEnum = Field(..., alias="priorityProduct")
    video_on_vip: bool = Field(..., alias="videoOnVip")
    urgency_feature_active: bool = Field(..., alias="urgencyFeatureActive")
    nap_available: bool = Field(..., alias="napAvailable")
    attributes: Optional[List[Attribute]]
    traits: List[TraitEnum]
    verticals: List[str]
    pictures: Optional[List[Picture]]
    vip_url: str = Field(..., alias="vipUrl")

    @property
    def url(self):
        return f"https://2dehands.be{self.vip_url}"

    async def set_posted_date(self, client_session: aiohttp.ClientSession) -> None:
        # aka: make it so the display_element always gets found
        data = await get_request_response(client_session, self.url)
        soup = BeautifulSoup(data, "html.parser")
        display_element = soup.find(id="displayed-since")
        if display_element is None:
            display_element = soup.select_one("#listing-root > div > div.Stats-root > span:nth-child(3) > span")

        raw_date_text = display_element.text.split("sinds")[1].strip().replace(".", "")
        dutch_to_english_month_dict = {
            "jan": "January",
            "feb": "February",
            "mar": "March",
            "apr": "April",
            "mei": "May",
            "jun": "June",
            "jul": "July",
            "aug": "August",
            "sep": "September",
            "okt": "October",
            "nov": "November",
            "dec": "December"
        }
        correct_date_text = None
        for short_dutch_name_month, month in dutch_to_english_month_dict.items():
            if short_dutch_name_month in raw_date_text:
                correct_date_text = raw_date_text.replace(short_dutch_name_month, month)
                break
        if correct_date_text is None:
            raise ValueError("Something went wrong when trying to convert the datetime", raw_date_text)
        self.date = datetime.strptime(correct_date_text, "%d %B '%y, %H:%M")

    def is_ad(self) -> bool:
        return self.priority_product != PriorityProductEnum.NONE

    def __eq__(self, other) -> bool:
        if other is None:
            return False
        return self.item_id == other.item_id

    def __ne__(self, other) -> bool:
        return not self.__eq__(other)
