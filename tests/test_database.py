import urllib.parse

import pytest
import tortoise.exceptions
from tortoise.contrib import test

from src.shared.models import QueryInfo, Marketplace

TEST_DB_URL = "sqlite://test-db.sqlite"


class TestDatabaseFunctionality(test.TestCase):
    @classmethod
    def setUpClass(cls):
        test.initializer(["src.shared.models"], db_url=TEST_DB_URL)

    @classmethod
    def tearDownClass(cls):
        test.finalizer()

    def setUp(self):
        query = "auto"
        postcode = 9000
        radius = 10
        self.valid_req_url = f'https://www.2dehands.be/lrp/api/search?attributesByKey[]=Language%3Aall-languages&attributesByKey[]=offeredSince%3AGisteren&limit=100&offset=0&query={urllib.parse.quote_plus(query)}&searchInTitleAndDescription=true&sortBy=SORT_INDEX&sortOrder=DECREASING&viewOptions=list-view&distanceMeters={str(radius*1000)}&postcode={str(postcode)}'
        self.valid_browser_url = f'https://www.2dehands.be/q/{urllib.parse.quote_plus(query)}/#Language:all-languages|offeredSince:Gisteren|sortBy:SORT_INDEX|sortOrder:DECREASING|viewOptions:list-view|distanceMeters:{str(radius*1000)}|postcode:{str(postcode)}'

    async def test_db_add_query_should_be_readable_in_db(self):
        query = QueryInfo(browser_url=self.valid_browser_url, marketplace=Marketplace.TWEEDEHANDS, query="test", request_url=self.valid_req_url)
        await query.save()
        self.assertEqual(await QueryInfo.all().count(), 1)

        fetched_query = await QueryInfo.first()

        # all attributes are equal
        self.assertEqual(fetched_query.request_url, query.request_url)
        self.assertEqual(fetched_query.query, query.query)
        self.assertEqual(fetched_query.marketplace, query.marketplace)

    async def test_db_invalid_domain_url_should_raise_validation_error(self):
        invalid_website = 'www.facebook.com'
        invalid_postcode = 'https://www.2dehands.be/lrp/api/search?attributesByKey[]=Language%3Aall-languages&attributesByKey[]=offeredSince%3AGisteren&limit=100&offset=0&query=auto&searchInTitleAndDescription=true&sortBy=SORT_INDEX&sortOrder=DECREASING&viewOptions=list-view&distanceMeters=10000&postcode=meow'
        empty_query = 'https://www.2dehands.be/lrp/api/search?attributesByKey[]=Language%3Aall-languages&attributesByKey[]=offeredSince%3AGisteren&limit=100&offset=0&query=&searchInTitleAndDescription=true&sortBy=SORT_INDEX&sortOrder=DECREASING&viewOptions=list-view'
        with pytest.raises(tortoise.exceptions.ValidationError):
            await QueryInfo.create(browser_url=self.valid_browser_url, request_url=invalid_website, marketplace=Marketplace.TWEEDEHANDS, query="irrelevant")

        with pytest.raises(tortoise.exceptions.ValidationError):
            await QueryInfo.create(browser_url=self.valid_browser_url, request_url=invalid_postcode, marketplace=Marketplace.TWEEDEHANDS, query="irrelevant")

        with pytest.raises(tortoise.exceptions.ValidationError):
            await QueryInfo.create(browser_url=self.valid_browser_url, request_url=empty_query, marketplace=Marketplace.TWEEDEHANDS, query="irrelevant")

        with pytest.raises(tortoise.exceptions.ValidationError):
            await QueryInfo.create(browser_url=invalid_website, request_url=self.valid_req_url, marketplace=Marketplace.TWEEDEHANDS, query="irrelevant")


    async def test_db_adding_and_removing_a_query_should_remove_it_from_db(self):
        q = await QueryInfo.create(browser_url=self.valid_browser_url, marketplace=Marketplace.TWEEDEHANDS, query="test", request_url=self.valid_req_url)

        await q.save()
        self.assertEqual(await QueryInfo.all().count(), 1)

        await q.delete()
        self.assertEqual(await QueryInfo.all().count(), 0)

