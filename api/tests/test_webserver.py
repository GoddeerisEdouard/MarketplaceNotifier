import aiohttp


async def test_create_query():
    async with aiohttp.ClientSession() as cs:
        data = {
            "query": "test query",
            "location_filter": {
                "cityOrPostalCode": "test city",
                "radius": 10
            }
        }
        resp = await cs.post("http://localhost:5000/query/add", json=data)
        assert resp.status == 200
        assert await resp.json() == {"query": "test query",
                                     "locationFilter": {"city": "test city", "postalCode": "test city", "radius": 10}}


async def test_duplicate_query():
    async with aiohttp.ClientSession() as cs:
        data = {
            "query": "test query",
            "location_filter": {
                "cityOrPostalCode": "test city",
                "radius": 10
            }
        }
        resp = await cs.post("http://localhost:5000/query/add", json=data)
        assert resp.status == 200
        assert await resp.json() == {"query": "test query",
                                     "locationFilter": {"city": "test city", "postalCode": "test city", "radius": 10}}

        resp = await cs.post("http://localhost:5000/query/add", json=data)
        assert resp.status == 500
        assert await resp.json() == {"error": "Query already exists"}
