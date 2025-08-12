import logging
from http import HTTPStatus
from types import SimpleNamespace
from typing import Optional, Dict, Any, Iterable

from aiohttp_retry import RetryClient, ExponentialRetry
from aiohttp import ClientSession, TraceConfig, TraceRequestStartParams, TraceRequestExceptionParams, \
    TraceRequestEndParams, ClientConnectorDNSError


def get_retry_client(exceptions: Iterable[type[Exception]] = None, statuses: Iterable[int] = None) -> RetryClient:
    """
    RetryClient which includes logging the retries
    exceptions: exceptions to retry on
    statuses: HTTP status codes to retry on
    """

    # Store last error/status for retry logging
    last_error_info = {}

    # Callback to capture response status
    async def on_request_end(
            session: ClientSession,
            trace_config_ctx: SimpleNamespace,
            params: TraceRequestEndParams,
    ) -> None:
        status = params.response.status
        url = str(params.url)

        # store status if it might trigger a retry (4xx/5xx) ! this depends on the retry_options!
        if status >= 400:
            last_error_info[url] = f"HTTP {status}"

    # Callback to capture exceptions
    async def on_request_exception(
            session: ClientSession,
            trace_config_ctx: SimpleNamespace,
            params: TraceRequestExceptionParams,
    ) -> None:
        exception = params.exception
        url = str(params.url)

        # store exception info
        last_error_info[url] = f"{type(exception).__name__}: {str(exception)}"

    # Callback to log retries (but skip first attempt)
    async def on_request_start(
            session: ClientSession,
            trace_config_ctx: SimpleNamespace,
            params: TraceRequestStartParams,
    ) -> None:
        current_attempt = trace_config_ctx.trace_request_ctx['current_attempt']
        if current_attempt > 1:  # the attempts are 1 based!
            url = str(params.url)

            # Get the error/status that caused this retry
            error_reason = last_error_info.get(url, "Unknown reason")

            logging.warning(
                f"Retrying attempt {current_attempt}/{retry_options.attempts} for URL: {params.url} "
                f"due to {error_reason}"
            )

            # clean up
            last_error_info.pop(url, None)

    trace_config = TraceConfig()
    trace_config.on_request_start.append(on_request_start)
    trace_config.on_request_end.append(on_request_end)
    trace_config.on_request_exception.append(on_request_exception)

    # default ClientDNSError, this is raised when the internet seems down
    exceptions = {ClientConnectorDNSError} if exceptions is None else {ClientConnectorDNSError, *exceptions}
    retry_options = ExponentialRetry(attempts=4, start_timeout=3.0, exceptions=exceptions, statuses=statuses)
    return RetryClient(
        retry_options=retry_options,
        trace_configs=[trace_config],
        raise_for_status=False
    )

async def get_request_response(retry_client: RetryClient, URI: str,
                               headers: Optional[Dict] = None, json_response: bool = True) -> Any:
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
    # TODO: handle exception when we lose connection (or when server refuses)
    """
    raise ClientConnectorError(req.connection_key, exc) from exc
aiohttp.client_exceptions.ClientConnectorError: Cannot connect to host www.2dehands.be:443 ssl:False [Temporary failure in name resolution]
    """
    async with retry_client.get(URI, headers=headers) as response:
        if response.status == HTTPStatus.OK:
            if not json_response:
                return await response.text()
            return await response.json()
        elif response.status == HTTPStatus.NO_CONTENT:
            logging.info(f"Requested URI: {URI} returns no content...")
            return ""
    logging.error("Failed %s after multiple retries, got error %d\n%s\n------", URI, response.status, response)

    raise response.raise_for_status()
