import asyncio
import unittest

import aiohttp

from marketplace_notifier.notifier.tweedehands.models import TweedehandsLocationFilter

# https://www.reddit.com/r/learnpython/comments/11q8i08/comment/jc7fb6a/
asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


class TestPostalCodeAPI(unittest.IsolatedAsyncioTestCase):
    def test_invalid_postal_code_should_raise_value_error(self):
        postal_code = 1

        with self.assertRaises(ValueError):
            _ = TweedehandsLocationFilter.belgian_postal_code_validation(postal_code)

    async def test_valid_postal_code_should_return_correct_city(self):
        given_postal_code = 9000
        expected_city = "Gent"

        async with aiohttp.ClientSession() as client:
            result = await TweedehandsLocationFilter.get_valid_postal_code_and_city(client_session=client,
                                                                          postal_code_or_city=str(given_postal_code))
        self.assertEqual(result["city"], expected_city)
        self.assertEqual(result["postal_code"], given_postal_code)

    async def test_valid_city_should_have_expected_postal_code_in_result(self):
        given_city = "Brussel"
        expected_postal_code = 1000

        async with aiohttp.ClientSession() as client:
            result = await TweedehandsLocationFilter.get_valid_postal_code_and_city(client_session=client,
                                                                          postal_code_or_city=given_city)
        self.assertEqual(result["postal_code"], expected_postal_code)
        self.assertEqual(result["city"], given_city)

    async def test_invalid_city_should_return_none(self):
        given_city = "amsterdam"

        async with aiohttp.ClientSession() as client:
            result = await TweedehandsLocationFilter.get_valid_postal_code_and_city(client_session=client,
                                                                          postal_code_or_city=given_city)
        self.assertIsNone(result)
