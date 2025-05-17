import urllib.parse

from pydantic import computed_field

from src.marketplace_notifier.notifier.models import IQuerySpecs
from src.marketplace_notifier.postalcode.models import ILocationFilter


class TweedehandsQuerySpecs(IQuerySpecs):
    @computed_field
    @property
    def request_query_url(self) -> str:
        """
        generates request URL based on the given attributes
        :return: a listing query url to use for a GET request
        """
        URI = "https://www.2dehands.be/lrp/api/search?attributesByKey[]=Language%3Aall-languages" \
              f"&attributesByKey[]=offeredSince%3AGisteren&limit=30&offset=0&query={urllib.parse.quote_plus(self.query)}" \
              "&searchInTitleAndDescription=true&sortBy=SORT_INDEX&sortOrder=DECREASING&viewOptions=list-view"
        if self.location_filter:
            URI += f"&distanceMeters={str(self.location_filter.radius * 1000)}&postcode={str(self.location_filter.postal_code)}"
        if self.price_range:
            URI += f"&attributeRanges[]:PriceCents:{str(self.price_range.min_price_cents)}:{str(self.price_range.max_price_cents)}"
        return URI

    @computed_field
    @property
    def browser_query_url(self) -> str:
        """
        generates the URL a user can use in his browser to find all listings based on his query
        :return: url a user can use in his browser
        looks like .../q/iphone/#Language:all-languages|sortBy:SORT_INDEX|sortOrder:DECREASING|searchInTitleAndDescription:true
        or
        .../q/iphone/#Language:all-languages|PriceCentsTo:5000|sortBy:SORT_INDEX|sortOrder:DECREASING|searchInTitleAndDescription:true
        """
        websearch_url = f"https://www.2dehands.be/q/{urllib.parse.quote_plus(self.query)}/#Language:all-languages|offeredSince:Gisteren|sortBy:SORT_INDEX|sortOrder:DECREASING"
        if self.location_filter is not None:
            websearch_url += f"|distanceMeters:{self.location_filter.radius * 1000}|postcode:{self.location_filter.postal_code}"
        if self.price_range is not None:
            websearch_url +=f"|PriceCentsFrom:{str(self.price_range.min_price_cents)}|PriceCentsTo:{str(self.price_range.max_price_cents)}"
        return websearch_url

    @classmethod
    def parse_request_url(cls, get_request_query_url: str) -> IQuerySpecs:
        """
        parses webbrowser url and returns object of this dataclass
        ( does the opposite of browser_query_url )
        :param get_request_query_url: the url to parse
        looks like .../.../q/iphone/#Language:all-languages|sortBy:SORT_INDEX|sortOrder:DECREASING|searchInTitleAndDescription:true
        or with price range (0 - 50 euros)
        .../q/iphone/#Language:all-languages|PriceCentsTo:5000|sortBy:SORT_INDEX|sortOrder:DECREASING|searchInTitleAndDescription:true
        :return: this dataclass
        """
        raise NotImplementedError()


class TweedehandsLocationFilter(ILocationFilter):
    RADIUS_LIST = [3, 5, 10, 15, 25, 50, 75]
