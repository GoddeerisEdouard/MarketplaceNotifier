import unittest

import aiohttp

from marketplace_notifier.notifier.models import PriceRange
from marketplace_notifier.notifier.tweedehands.models import TweedehandsLocationFilter, TweedehandsQuerySpecs
from marketplace_notifier.notifier.tweedehands.notifier import TweedehandsNotifier
from marketplace_notifier.notifier.tweedehands.return_models import TweedehandsListingInfo


class TestTweedehandsNotifier(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tn = TweedehandsNotifier()

    async def test_car_query_returns_at_least_one_listing(self):
        # query expected to not be filled with only ads the first page
        # "car" for example does only have ads as response around 12am, hence not that query
        query = "iphone"

        tqs = TweedehandsQuerySpecs(query=query)

        # generate request url based on listingspecs
        request_url = tqs.request_query_url
        async with aiohttp.ClientSession() as cs:
            non_ad_listings = await self.tn.fetch_listings_of_request_url(cs, request_url)

        self.assertGreater(len(non_ad_listings), 1)
        self.assertTrue(isinstance(non_ad_listings[0], TweedehandsListingInfo))

    async def test_amount_of_listings_should_be_lower_with_location_filter(self):
        # query without location filter
        query = "mario wonder"

        # same query with location filter
        stad = "brussel"
        radius = 5


        async with aiohttp.ClientSession() as cs:
            query_specs_without_location_filter = TweedehandsQuerySpecs(query=query)

            non_ad_listings_without_location_filter = await self.tn.fetch_listings_of_request_url(cs,
                                                                                                  query_specs_without_location_filter.request_query_url)

            # with location filter
            city_and_postal_code = await TweedehandsLocationFilter.get_valid_postal_code_and_city(client_session=cs,
                                                                                                  postal_code_or_city=stad)
            tlf = TweedehandsLocationFilter(city=city_and_postal_code["city"],
                                            postal_code=city_and_postal_code["postal_code"], radius=radius)

            query_specs_with_location_filter = TweedehandsQuerySpecs(query=query, location_filter=tlf)

            non_ad_listings_with_location_filter = await self.tn.fetch_listings_of_request_url(cs,
                                                                                               query_specs_with_location_filter.request_query_url)

        self.assertGreater(len(non_ad_listings_without_location_filter), len(non_ad_listings_with_location_filter),
                           f"{query_specs_with_location_filter.request_query_url}")
