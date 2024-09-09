from pydantic import Field

from marketplace_notifier.notifier.models import IListingInfo


class TweedehandsListingInfo(IListingInfo):
    id: str = Field(max_length=11)
    title: str = Field(max_length=60)

    BASE_URL = "https://www.2dehands.be"
