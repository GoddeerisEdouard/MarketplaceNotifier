import logging
from http import HTTPStatus
from typing import Optional, Dict

import aiohttp

logging.basicConfig(level=logging.INFO, filename="requests.log",
                    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")


async def get_request_response(client_session: aiohttp.ClientSession, URI: str,
                               headers: Optional[Dict] = None) -> str:
    """
    uses client_session with given headers and a user-agent
    logs errors
    """
    if headers is None:
        headers = {
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36"}
    elif "user-agent" not in headers:
        headers = dict(headers, **{
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36"})

    logging.info("making request for %s", URI)
    async with client_session.get(URI, headers=headers, ssl=False) as response:
        if response.status == HTTPStatus.OK:
            return await response.text()
        elif response.status == HTTPStatus.NO_CONTENT:
            logging.warning(f"Requested URI: {URI} returns no content...")
            return ""
    logging.warning("Got status code %d on %s, trying again once more", response.status, URI)

    async with client_session.get(URI, headers=headers, ssl=False) as response:
        if response.status == HTTPStatus.OK:
            return await response.text()
    logging.error("Failed again, got error %d\n%s", response.status, response)
