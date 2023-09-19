from pydantic import field_validator, Field

from marketplace_notifier.notifier.models import IListingInfo


class TweedehandsListing(IListingInfo):
    _BASE_URL = "https://www.2dehands.be"
    id: str = Field(max_length=11)
    title: str = Field(max_length=60)
