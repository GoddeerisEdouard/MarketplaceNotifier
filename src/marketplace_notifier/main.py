import logging
from logging.handlers import RotatingFileHandler
import sys

import redis.asyncio as redisaio
from tortoise import run_async, Tortoise

from config.config import config
from src.shared.api_utils import get_retry_client
from src.shared.models import QueryInfo
from src.marketplace_notifier.db_models import LatestListingInfoDB
from src.marketplace_notifier.notifier import Notifier

FETCH_INTERVAL = 2 * 60  # 2 minutes
# Create a custom logger
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Create formatter
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# File handler
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB
file_handler = RotatingFileHandler(
    'requests.log',
    maxBytes=MAX_FILE_SIZE,
    backupCount=3,
    encoding='utf-8'
)
file_handler.setFormatter(formatter)

# Console handler
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(formatter)

# Clear previous handlers (important when using in notebooks or reloading modules)
if logger.hasHandlers():
    logger.handlers.clear()

for handler in [file_handler, console_handler]:
    logger.addHandler(handler)


async def cleanup_orphaned_latest_listings():
    """
    Removes stale rows from LatestListingInfoDB that no longer have a corresponding entry in QueryInfo.
    This can happen when a query is deleted via the webserver API while the notifier is offline - QueryInfo loses the row,
    but LatestListingInfoDB still holds the last-seen listing ID for that URL.
    QueryInfo is the source of truth.
    LatestListingInfoDB is the notifier's own bookkeeping and should never outlive the query it belongs to.
    Called once at startup before the main notification loop begins.
    """
    logging.info("Syncing LatestListingInfoDB against QueryInfo (source of truth)...")
    shared_urls = set(await QueryInfo.all().values_list('request_url', flat=True))
    local_urls = set(await LatestListingInfoDB.all().values_list('request_url', flat=True))

    orphaned = local_urls - shared_urls
    if orphaned:
        deleted = await LatestListingInfoDB.filter(request_url__in=orphaned).delete()
        logging.info(
            f"Deleted {deleted} orphaned LatestListingInfoDB row(s) "
            f"for URLs no longer in QueryInfo."
        )
    else:
        logging.info("No orphaned rows found.")

    new_queries_count = len(shared_urls - local_urls)
    if new_queries_count:
        logging.info(
            f"{new_queries_count} monitored URL(s) have no latest-listing row yet "
            "- this is normal for fresh queries."
        )
    logging.info("Sync complete.")



async def run():
    """
    runs the Redis pubsub
    publishes new listings to the pubsub channel after every interval
    """
    CONFIG = {
        "connections": {
            "default": f"sqlite://{config['database_path']}/marketplace.sqlite3",
            "shared": config["default_db_url"]
        },
        "apps": {
            "default": {
                "models": ["src.marketplace_notifier.db_models"],
                "default_connection": "default"
            },
            "shared": {
                "models": ["src.shared.models"],
                "default_connection": "shared"
            }
        }
    }
    await Tortoise.init(config=CONFIG)
    await Tortoise.generate_schemas()

    await cleanup_orphaned_latest_listings()

    # initialize redis pubsub IPC
    redis_client = redisaio.StrictRedis(host=config["redis_host"])
    try:
        await redis_client.ping()
    except redisaio.ConnectionError as e:
        logging.error("Seems like there's not redis server running, please start it first.")
        raise e
    except Exception as e:
        logging.error(f"Unexpected error while connecting to Redis: {e}")
        raise e
    logging.info("Connected to Redis successfully.")

    # we sometimes get this error after a while of fetching:
    # aiohttp.client_exceptions.ClientResponseError: 400, message='Bad Request', url='.../api/...'
    # so we retry if the status code is 400
    # TODO: check if it actually retries for that status
    retry_client = get_retry_client(statuses=[400])
    async with retry_client as cs:
        notifier = Notifier(cs, redis_client, FETCH_INTERVAL)
        await notifier.start()


if __name__ == '__main__':
    run_async(run())
