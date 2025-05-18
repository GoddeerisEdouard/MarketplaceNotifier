import redis.asyncio as redis
from aiohttp_retry import RetryClient
from tortoise.contrib import test

from src.shared.models import QueryInfo, ListingInfo
from src.marketplace_notifier.notifier.models import PriceRange
from src.marketplace_notifier.notifier.tweedehands.models import TweedehandsQuerySpecs, TweedehandsLocationFilter
from src.marketplace_notifier.notifier.tweedehands.notifier import TweedehandsNotifier

TEST_DB_URL = "sqlite://test-db.sqlite"


class TestListingInfo(test.TestCase):

    @classmethod
    def setUpClass(cls):
        test.initializer(["src.shared.models"], db_url=TEST_DB_URL)

    @classmethod
    def tearDownClass(cls):
        test.finalizer()

    async def test_redis_connection(self):
        redis_client = redis.StrictRedis()
        r = await redis_client.ping()
        self.assertTrue(r)

    async def test_valid_input_queries_should_be_serialized_without_errors(self):
        # TODO: remove all this, we want the browser_url to be the only input
        # there's no need to replicate 2dehands' frontend forms
        query = "iphone"
        city = "Gent"
        postal_code = 9000
        radius = 5
        min_price_cents = 0
        max_price_cents = 5000

        lf = TweedehandsLocationFilter(city=city, postal_code=postal_code, radius=radius)
        pr = PriceRange(min_price_cents=min_price_cents, max_price_cents=max_price_cents)
        tqs = TweedehandsQuerySpecs(query=query, location_filter=lf, price_range=pr)
        # no filters
        tqsnf = TweedehandsQuerySpecs(query=query, location_filter=None, price_range=None)

        expected_serialized_tqs = {"query": query,
                                   "location_filter": {"city": city, "postal_code": postal_code, "radius": radius},
                                   "price_range": {"min_price_cents": min_price_cents,
                                                   "max_price_cents": max_price_cents}}
        expected_serialized_tqs["browser_query_url"] = tqs.browser_query_url
        expected_serialized_tqs["request_query_url"] = tqs.request_query_url

        expected_serialized_tqs_nf = {"query": query, "location_filter": None, "price_range": None}
        expected_serialized_tqs_nf["browser_query_url"] = tqsnf.browser_query_url
        expected_serialized_tqs_nf["request_query_url"] = tqsnf.request_query_url

        self.assertEqual(tqs.model_dump(), expected_serialized_tqs)
        self.assertEqual(tqsnf.model_dump(), expected_serialized_tqs_nf)

    async def test_invalid_input_queries_should_be_parsed_correctly(self):
        query = "iphone"
        invalid_city = "invalid city"
        radius = 5
        async with RetryClient() as rc:
            postal_code_and_city = await TweedehandsLocationFilter.get_valid_postal_code_and_city(rc, invalid_city)

        tqs = TweedehandsQuerySpecs(query=query, location_filter=TweedehandsLocationFilter(city=postal_code_and_city["city"], postal_code=postal_code_and_city["postal_code"],
                                  radius=radius) if postal_code_and_city else None)

        self.assertEqual(tqs.location_filter, None)


    async def test_query_should_add_listing_in_db(self):
        tn = TweedehandsNotifier()
        # add query to monitor
        query = "iphone"
        tqs = TweedehandsQuerySpecs(query=query)
        await QueryInfo.create(browser_url=tqs.browser_query_url, request_url=tqs.request_query_url, marketplace=tn.marketplace, query=query)

        async with RetryClient() as rc:
            request_url_with_listings = await tn.fetch_all_query_urls(rc)

        self.assertEqual(await ListingInfo.all().count(), 0)

        redis_client = redis.StrictRedis()
        await tn.process_listings(request_url_with_listings, redis_client)
        await redis_client.close()

        self.assertGreater(await ListingInfo.all().count(), 0, "no listings added to an empty db")
