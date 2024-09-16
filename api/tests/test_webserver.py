import aiohttp


async def test_create_query():
    async with aiohttp.ClientSession() as cs:
        data = {
            "query": "test query",
            "location_filter": {
                "cityOrPostalCode": "Brussel",
                "radius": 10
            },
            "price_range": None
        }
        resp = await cs.post("http://localhost:5000/query/add", json=data)
        assert resp.status == 200
        assert await resp.json() == {
            "browser_query_url": "",
            "location_filter": {
                "city": "",
                "postal_code": None,
                "radius": None
            },
            "price_range": None,
            "query": "",
            "request_query_url": ""
        }


async def test_duplicate_query():
    async with aiohttp.ClientSession() as cs:
        data = {
            "query": "test query",
            "location_filter": {
                "cityOrPostalCode": "Gent",
                "radius": 10
            },
            "price_range": {
                "min_price_cents": 0,
                "max_price_cents": 5000
            }
        }
        resp = await cs.post("http://localhost:5000/query/add", json=data)
        assert resp.status == 200

        resp = await cs.post("http://localhost:5000/query/add", json=data)
        assert resp.status == 500
        assert await resp.json() == {"error": "Query already exists"}
