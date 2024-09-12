import aiohttp
import redis.asyncio as redis
from tortoise.contrib import test

from marketplace_notifier.db_models.models import QueryInfo, ListingInfo
from marketplace_notifier.notifier.tweedehands.models import TweedehandsQuerySpecs
from marketplace_notifier.notifier.tweedehands.notifier import TweedehandsNotifier

TEST_DB_URL = "sqlite://test-db.sqlite"


class TestListingInfo(test.TestCase):

    @classmethod
    def setUpClass(cls):
        test.initializer(["marketplace_notifier.db_models.models"], db_url=TEST_DB_URL)

    @classmethod
    def tearDownClass(cls):
        test.finalizer()

    async def test_redis_connection(self):
        redis_client = redis.StrictRedis()
        r = await redis_client.ping()
        self.assertTrue(r)

    async def test_query_should_add_listing_in_db(self):
        tn = TweedehandsNotifier()
        # add query to monitor
        query = "iphone"
        request_url = TweedehandsQuerySpecs(query=query).request_query_url
        await QueryInfo.create(request_url=request_url, marketplace=tn.marketplace, query=query)

        async with aiohttp.ClientSession() as cs:
            request_url_with_listings = await tn.fetch_all_query_urls(cs)

        self.assertEqual(await ListingInfo.all().count(), 0)

        redis_client = redis.StrictRedis()
        await tn.process_listings(request_url_with_listings, redis_client)
        await redis_client.close()

        self.assertGreater(await ListingInfo.all().count(), 0, "no listings added to an empty db")
