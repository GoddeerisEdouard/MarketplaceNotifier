import redis.asyncio as redis
from typing import List, Dict, Any
import os

from src.shared.api_utils import get_request_response
from src.shared.models import QueryInfo, QueryStatus
from src.marketplace_notifier.db_models import LatestListingInfoDB

REQUEST_URL_ERROR_CHANNEL = "request_url_error"
GENERIC_WARNING_CHANNEL = "warning"
SLEEP_INTERVAL = 10  # seconds between checking for new queries or changes
WEBSERVER_URL = f"http://{'webserver' if os.getenv('USE_DOCKER_CONFIG', 'false').lower() == 'true' else 'localhost'}:5000"

import asyncio
import logging
import json
import traceback
from datetime import datetime, timedelta

class Notifier:
    """
    Manages the scheduling and execution of queries at regular intervals.
    Prevents spamming the 2dehands API by spreading requests over time.
    """

    def __init__(self, retry_client, redis_client, interval):
        self.retry_client = retry_client
        self.redis_client = redis_client
        self.interval = interval
        self.query_schedule = {}  # Maps request URLs to their next scheduled execution time

    async def start(self):
        """
        Start the scheduler and monitor for changes in active queries.
        """
        await self._initialize_schedule()

        while True:
            active_queries = await QueryInfo.filter(status=QueryStatus.ACTIVE).values_list("request_url", flat=True)

            if not active_queries:
                logging.info("No active queries found. Sleeping...")
                await asyncio.sleep(SLEEP_INTERVAL)
                continue

            await self._update_schedule(active_queries)
            await self._process_ready_queries()
            self._log_upcoming_schedule()

            await asyncio.sleep(SLEEP_INTERVAL)

    async def _initialize_schedule(self):
        """
        Initialize the schedule by spreading active queries evenly across the interval.
        """
        now = datetime.now()
        active_queries = await QueryInfo.filter(status=QueryStatus.ACTIVE).values_list("request_url", flat=True)

        if not active_queries:
            logging.info("No active queries found to initialize.")
            return

        spread_interval = self.interval / max(len(active_queries), 1)

        for i, request_url in enumerate(active_queries):
            next_execution_time = now + timedelta(seconds=i * spread_interval)
            self.query_schedule[request_url] = next_execution_time
            logging.info(f"Scheduled initial query at {next_execution_time.strftime('%H:%M:%S')}: {request_url}")

            await QueryInfo.filter(request_url=request_url).update(next_check_time=next_execution_time)

    async def _update_schedule(self, active_queries):
        """
        Update the schedule by adding new queries and removing inactive ones.
        """
        # Remove queries that are no longer active
        inactive_queries = set(self.query_schedule.keys()) - set(active_queries)
        for request_url in inactive_queries:
            self.query_schedule.pop(request_url, None)
            logging.info(f"Removed inactive query: {request_url}")

        # Add new queries that are not yet scheduled
        new_queries = set(active_queries) - set(self.query_schedule.keys())
        for request_url in new_queries:
            await self._schedule_new_query(request_url)

    async def _schedule_new_query(self, request_url):
        """
        Schedule a new query for the first time.
        """
        next_execution_time = datetime.now()
        self.query_schedule[request_url] = next_execution_time
        logging.info(f"Scheduled new query at {next_execution_time.strftime('%H:%M:%S')}: {request_url}")

        await QueryInfo.filter(request_url=request_url).update(next_check_time=next_execution_time)

    async def _process_ready_queries(self):
        """
        Process all queries that are ready to be executed.
        """
        now = datetime.now()
        ready_queries = [url for url, time in self.query_schedule.items() if time <= now]

        if len(ready_queries) > 1:
            total_active_queries = await QueryInfo.filter(status=QueryStatus.ACTIVE).count()
            warning_message = (f"Too many queries being processed at once: {len(ready_queries)} of {total_active_queries} active queries. "
                               "This may lead to rate limiting.")
            logging.warning(warning_message)
            await self.redis_client.publish(GENERIC_WARNING_CHANNEL, json.dumps({
                "message": warning_message,
                "reason": "Queries are not evenly distributed across the interval."
            }))

        spread_interval = self.interval / max(len(self.query_schedule), 1)
        last_scheduled_time = max(self.query_schedule.values(), default=now)

        for i, request_url in enumerate(ready_queries):
            try:
                logging.info(f"Processing query: {request_url}")

                result = await get_request_response(self.retry_client, request_url, json_response=True)
                await process_listings({request_url: result["listings"]}, self.redis_client)

                next_execution_time = last_scheduled_time + timedelta(seconds=(i + 1) * spread_interval)
                self.query_schedule[request_url] = next_execution_time
                logging.info(f"Next execution scheduled at {next_execution_time.strftime('%H:%M:%S')}: {request_url}")

                await QueryInfo.filter(request_url=request_url).update(next_check_time=next_execution_time)

            except Exception as e:
                error_traceback = traceback.format_exc()
                logging.error(f"Error processing query {request_url}: {type(e).__name__} - {str(e)}\n{error_traceback}")
                await QueryInfo.filter(request_url=request_url).update(status=QueryStatus.FAILED)
                logging.info(f"Marked query as FAILED: {request_url}")

                await self.redis_client.publish(REQUEST_URL_ERROR_CHANNEL, json.dumps({
                    "request_url": request_url,
                    "error": type(e).__name__,
                    "reason": str(e),
                    "traceback": error_traceback
                }))

    def _log_upcoming_schedule(self):
        """
        Log the upcoming schedule for the next queries.
        """
        now = datetime.now()
        upcoming_queries = [(url, time) for url, time in self.query_schedule.items() if time > now]
        upcoming_queries.sort(key=lambda x: x[1])

        if upcoming_queries:
            logging.info("Upcoming query executions:")
            for i, (url, time) in enumerate(upcoming_queries[:5]):  # Log at most 5 upcoming queries
                wait_time = (time - now).total_seconds()
                logging.info(f"  {i + 1}. {time.strftime('%H:%M:%S')} (in {wait_time:.0f}s): {url}")

            if len(upcoming_queries) > 5:
                logging.info(f"  ... and {len(upcoming_queries) - 5} more")

async def process_listings(
    request_url_all_listings_dict: Dict[str, List[Dict[Any, Any]]],
    async_redis_client: redis.client
) -> None:
    """
    Processes listings for each request URL:
    - Filters out ads and outdated listings.
    - Updates the latest listing in the database.
    - Publishes new listings to a Redis channel.
    """
    for request_url, listings in request_url_all_listings_dict.items():
        logging.info(f"Processing request URL: {request_url}")

        # Check if the request URL exists in the database
        if not await QueryInfo.exists(request_url=request_url):
            logging.warning(f"Request URL {request_url} was removed from the database while processing.")
            continue

        # Get the latest listing for the request URL from the database
        latest_listing = await LatestListingInfoDB.filter(request_url=request_url).get_or_none()
        latest_listing_id = int(latest_listing.item_id[1:]) if latest_listing else 0  # Remove 'm' prefix

        # Filter and sort new non-ad listings
        new_listings = [
            listing for listing in listings
            if listing["priorityProduct"] == "NONE" and int(listing["itemId"][1:]) > latest_listing_id
        ]

        if not new_listings:
            logging.info(f"No new non-ad listings for request URL: {request_url}")
            continue

        new_listings.sort(key=lambda li: int(li["itemId"][1:]), reverse=True)  # Sort by ID (newest first)

        logging.info(f"Found {len(new_listings)} new non-ad listings for {request_url}.")

        # Update the latest listing in the database
        await _update_latest_listing(request_url, new_listings[0], latest_listing)

        # Publish new listings to Redis
        await _publish_new_listings_to_redis(request_url, new_listings, async_redis_client)


async def _update_latest_listing(request_url: str, latest_listing: Dict[str, Any], db_latest_listing: LatestListingInfoDB) -> None:
    """
    Updates the latest listing for a request URL in the database.
    """
    if db_latest_listing is None:
        new_listing = LatestListingInfoDB(
            request_url=request_url,
            item_id=latest_listing["itemId"],
            title=latest_listing["title"]
        )
        await new_listing.save()
        logging.info(f"Set latest listing for {request_url} to <item_id: {latest_listing['itemId']}, title: {latest_listing['title']}>.")
    else:
        db_latest_listing.item_id = latest_listing["itemId"]
        db_latest_listing.title = latest_listing["title"]
        await db_latest_listing.save()
        logging.info(f"Updated latest listing for {request_url} to <item_id: {latest_listing['itemId']}, title: {latest_listing['title']}>.")


async def _publish_new_listings_to_redis(request_url: str, new_listings: List[Dict[str, Any]], async_redis_client: redis.client) -> None:
    """
    Publishes new listings to the Redis channel.
    """
    message = {"request_url": request_url, "new_listings": new_listings}
    await async_redis_client.publish("listings", json.dumps(message))
    logging.info(f"Published {len(new_listings)} new listings for {request_url} to Redis.")