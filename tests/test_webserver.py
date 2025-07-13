from aiohttp_retry import RetryClient

WEBSERVER_URL = "http://localhost:5000"
async def test_add_link():
    data = {
        "browser_url": "https://www.2dehands.be/q/iphone+15/#Language:all-languages|sortBy:SORT_INDEX|sortOrder:DECREASING"
    }
    async with RetryClient() as rc:
        resp = await rc.post(f"{WEBSERVER_URL}/query/add_link", json=data)
    assert resp.status == 200
    assert resp.headers["Content-Type"] == "application/json"
    response = await resp.json()
    del response["id"]
    assert resp.json() == {
        "marketplace": "TWEEDEHANDS",
        "query": "iphone 15",
        "request_url": "https://www.2dehands.be/lrp/api/search?attributesByKey%5B%5D=Language%3Aall-languages&attributesByKey%5B%5D=offeredSince%3AGisteren&limit=100&offset=0&sortBy=SORT_INDEX&sortOrder=DECREASING&viewOptions=list-view&query=iphone+15"
    }



async def test_duplicate_link():
    data = {
        "browser_url": "https://www.2dehands.be/q/iphone+15/#Language:all-languages|sortBy:SORT_INDEX|sortOrder:DECREASING"
    }
    async with RetryClient() as rc:
        resp = await rc.post(f"{WEBSERVER_URL}/query/add_link", json=data)
        assert resp.status == 200
#
        resp = await rc.post(f"{WEBSERVER_URL}/query/add_link", json=data)
        assert resp.status == 500
        assert await resp.json() == {"error": "Query already exists"}
