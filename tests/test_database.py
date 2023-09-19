import unittest

from tortoise import Tortoise

TEST_DB_URL = "sqlite://testdb.sqlite3"


class TestDatabaseFunctionality(unittest.IsolatedAsyncioTestCase):
    async def test_database_creation_should_not_throw_errors(self):
        await Tortoise.init(db_url=TEST_DB_URL, modules={"models": ["marketplace_notifier.db_models.models"]})
