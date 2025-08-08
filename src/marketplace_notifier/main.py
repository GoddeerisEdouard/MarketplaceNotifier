import logging
from logging.handlers import RotatingFileHandler
import sys

import redis.asyncio as redisaio
from tortoise import run_async, Tortoise

from config.config import config
from src.shared.api_utils import get_retry_client
from src.shared.models import QueryInfo
from src.marketplace_notifier.db_models import LatestListingInfoDB
from src.marketplace_notifier.scheduler import QueryScheduler
from src.marketplace_notifier.notifier import TweedehandsNotifier

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


async def sync_request_urls_between_shared_db_and_marketplace_db():
    # this is useful when the pubsub is down while the webserver is still online
    request_urls_shared_db = await QueryInfo.all().values_list('request_url', flat=True)
    logging.info("Syncing request URLs between webserver and marketplace DB...")
    request_urls_marketplace_db = await LatestListingInfoDB.all().values_list('request_url', flat=True)

    # the shared DB request_urls are the source of truth
    request_urls_to_remove = set(request_urls_shared_db) - set(request_urls_marketplace_db)
    logging.info(f"There are {len(request_urls_to_remove)} too much request_urls being fetched")
    for request_url in request_urls_to_remove:
        await QueryInfo.filter(request_url=request_url).delete()
    logging.info("Syncing complete!")


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

    await sync_request_urls_between_shared_db_and_marketplace_db()

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

    tn = TweedehandsNotifier()
    retry_client = get_retry_client()
    async with retry_client as cs:
        scheduler = QueryScheduler(tn, cs, redis_client, FETCH_INTERVAL)
        await scheduler.start()


if __name__ == '__main__':
    run_async(run())
