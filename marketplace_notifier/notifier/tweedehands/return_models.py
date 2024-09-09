from pydantic import Field

from marketplace_notifier.notifier.models import IListingInfo


class TweedehandsListingInfo(IListingInfo):
    id: str = Field(max_length=11)
    title: str = Field(max_length=60)

    BASE_URL = "https://www.2dehands.be"

    def to_json(self):
        return { "id": self.id,
                 "title": self.title,
                 "price_info": self.price_info.model_dump(),
                 "description": self.description,
                 "screenshot_path": self.screenshot_path,
                 "posted_date": self.posted_date.strftime("%d %B '%y, %H:%M"),
                 "seller_url": self.seller_url,
                 "specified_location": self.specified_location.model_dump(),
                 "vip_url": self.vip_url
                 }