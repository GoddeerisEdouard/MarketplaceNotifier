import logging
import sys

from aiohttp_retry import RetryClient, ExponentialRetry
import redis.asyncio as redisaio
from tortoise import run_async, Tortoise

from config.config import config
from src.marketplace_notifier.scheduler import QueryScheduler
from src.marketplace_notifier.notifier import TweedehandsNotifier

FETCH_INTERVAL = 2 * 60  # 2 minutes
# Create a custom logger
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Create formatter
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# File handler
file_handler = logging.FileHandler('requests.log', encoding='utf-8')
file_handler.setFormatter(formatter)

# Console handler
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(formatter)

# Clear previous handlers (important when using in notebooks or reloading modules)
if logger.hasHandlers():
    logger.handlers.clear()

for handler in [file_handler, console_handler]:
    logger.addHandler(handler)

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

    # initialize redis pubsub IPC
    redis_client = redisaio.StrictRedis(host=config["redis_host"])
    tn = TweedehandsNotifier()
    retry_options = ExponentialRetry()  # default retry of 3, retry on all server errors (5xx)
    async with RetryClient(retry_options=retry_options, raise_for_status=False) as cs:
        scheduler = QueryScheduler(tn, cs, redis_client, FETCH_INTERVAL)
        await scheduler.start()


if __name__ == '__main__':
    run_async(run())
