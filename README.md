# MarketplaceNotifier

monitor and get notified for your queried marketplace listings  
A `Notifier` object with public methods.  
It's then up to the client to process the returned data through Redis pubsub.  
More info about how to subscribe in the [FYI](#fyi)

marketplaces:

- [ ] [2dehands](https://www.2dehands.be) / [2ememain](https://www.2ememain.be)
- [ ] [facebook marketplace](https://www.facebook.com/marketplace)

## Table of contents

* [Getting Started](#getting-started)
    + [Installing](#installing)
    + [Executing program](#executing-program)
* [Implementation](#implementation)
    * [commands](#commands)
    * [discord bot](#discord-bot)
* [FYI](#fyi)
* [Help](#help)


## Getting Started

### Installing

* tested on **Python 3.8**
  [requirements.txt](requirements.txt) contains all Python packages needed.

```shell
pip install -r requirements.txt
```

### Executing program

first, build the redis server and run it in Docker

```shell
docker build -t my-redis .
docker run -p 6379:6379 --name redis-server -d my-redis
```

next, run the monitor

```shell
python main.py
```

the program will run and check for new listings every 5 minutes.
Based on the queries in the DB, it will check for new listings and process them through the process_listings method in
INotifier.

## Implementation

ways to communicate with the notifier  
! make sure the Redis [server is running](#executing-program)

### commands

ADD or REMOVE queries to monitor

```python
import redis.asyncio as redis
from marketplace_notifier.notifier.tweedehands.models import TweedehandsQuerySpecs

# Connect to local Redis instance
redis_client = redis.StrictRedis()
channel = 'commands'


# ADD QUERY
async def add_query(query_specs: TweedehandsQuerySpecs):
    await redis_client.publish(channel, f"ADD_QUERY {query_specs}")


async def remove_query(request_url: str):
    await redis_client.publish(channel, f"REMOVE_QUERY {request_url}")

```

### discord bot
example of how to handle new listings  
in [discordpy](https://discordpy.readthedocs.io/en/stable/) to be exact

```python
import redis.asyncio as redis
from marketplace_notifier.notifier.tweedehands.return_models import TweedehandsListingInfo

from discord.ext import tasks, commands


# in a Cog
class MyCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.redis_client = redis.StrictRedis()
        self.redis_channel = 'discord_bot'
        self.bot.loop.create_task(self.new_listing_reader())


async def cog_unload(self):
    await self.redis_client.aclose()


async def new_listing_reader(self):
    async with self.redis_client.pubsub() as pubsub:
        await pubsub.subscribe(self.redis_channel)

        while True:
            message = await channel.get_message(ignore_subscribe_messages=True)
            if message is not None:
                data = msg['data'].decode('utf-8')
                if data.startswith('NEW_LISTING'):
                    serialized_new_tweedehands_listing_info = data[len('NEW_LISTING '):]
                    new_tweedehands_listing_info = TweedehandsListingInfo(**serialized_tweedehands_listing)

                    # do something with the new_tweedehands_listing_info
                    # ...
```

## FYI

queries to be monitored are stored in a DB.  
This is to cache already seen listings and update when new ones arrive.

new listings are sent with Redis to the `'discord_bot'` channel.

in the redis pubsub `commands` channel, you can send commands:
> **Adding** queries:
`"ADD_QUERY <serialized TweedehandsQuerySpecs object>"`

> **Removing** queries:
`"REMOVE_QUERY <request_url>"`

## Help

For any issues, please create an Issue

