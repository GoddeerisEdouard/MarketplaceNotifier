import logging
from http import HTTPStatus
from typing import Optional, Dict

from aiohttp_retry import RetryClient

logging.basicConfig(level=logging.INFO, filename="requests.log",
                    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", encoding="utf-8")

async def get_request_response(retry_client: RetryClient, URI: str,
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
    async with retry_client.get(URI, headers=headers, ssl=False) as response:
        if response.status == HTTPStatus.OK:
            return await response.text()
        elif response.status == HTTPStatus.NO_CONTENT:
            logging.warning(f"Requested URI: {URI} returns no content...")
            return ""
    logging.warning("Got status code %d when requesting %s\n-----", response.status, URI)

    logging.error("Failed after multiple retries, got error %d\n%s\n------", response.status, response)

    # TODO: handle when this error raises: when even after several retries, the server still doesn't respond
    # raises a aiohttp.ClientResponseError
    raise response.raise_for_status()
