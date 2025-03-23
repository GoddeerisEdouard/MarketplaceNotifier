from datetime import datetime
from enum import Enum
from typing import Optional, List, Union, Literal

from aiohttp_retry import RetryClient
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field, HttpUrl, AliasChoices

from marketplace_notifier.utils.api_utils import get_request_response


# Tweedehands API related
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
    AUTOMOTIVE_EXTENDED_ASQ = "AUTOMOTIVE_EXTENDED_ASQ"


class Listing(BaseModel):
    """
    class representing a parsed listing from the API
    """
    item_id: str = Field(..., alias="itemId")
    title: str
    description: str
    price_info: PriceInfo = Field(..., alias="priceInfo")
    location: Location
    date: Optional[Union[datetime, Literal["Vandaag", "Gisteren", "Eergisteren"]]] = None
    image_urls: Optional[List[str]] = Field(None, alias="imageUrls")
    seller_information: SellerInformation = Field(..., alias="sellerInformation")
    category_id: int = Field(..., alias="categoryId")
    priority_product: PriorityProductEnum = Field(..., alias="priorityProduct")
    video_on_vip: bool = Field(..., alias="videoOnVip")
    urgency_feature_active: bool = Field(..., alias="urgencyFeatureActive")
    nap_available: bool = Field(..., alias="napAvailable")
    attributes: Optional[List[Attribute]] = Field(..., validation_alias=AliasChoices("attributes", "extendedAttributes"))
    traits: List[TraitEnum]
    verticals: List[str]
    pictures: Optional[List[Picture]] = None
    vip_url: str = Field(..., alias="vipUrl")

    @property
    def url(self):
        return f"https://2dehands.be{self.vip_url}"

    async def set_posted_date(self, rc: RetryClient) -> None:
        # aka: make it so the display_element always gets found
        data = await get_request_response(rc, self.url)
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
