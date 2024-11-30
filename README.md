# MarketplaceNotifier

Get notified for new *marketplace* listings  

supported *marketplaces*:

- [x] [2dehands](https://www.2dehands.be) / [2ememain](https://www.2ememain.be)

More info on how to receive notifications in [implementation](#implementation)

## Table of contents

* [Getting Started](#getting-started)
  * [Pre-requisites](#pre-requisites)
  * [Installing](#installing)
    * [Locally](#locally)
    * [Dockerized](#dockerized)
  * [Executing program](#executing-program)
* [Implementation](#implementation)
  * [commands](#commands)
  * [discord bot](#discord-bot)
* [FYI](#fyi)
* [Help](#help)


## Getting Started
### Pre-requisites
* tested on **Python 3.9**
  [requirements.txt](requirements.txt) contains all Python packages needed.

### Installing
#### Locally
A **redis server** should be running on port 6379
Make sure you can ping the server locally via the `redis-cli`

webserver to [handle CRUD operations](#implementation) on listing queries
```python
python api/webserver.py
```

fetch new listings & sends them with Redis
```python
python main.py
```

#### Dockerized
```shell
docker-compose up -d --build
```

This starts:
- the Redis server
- the webserver
- the notifier (which checks for new listings)

### Executing program
```shell
docker-compose up -d
```

the program will run and check for new listings every 5 minutes.
Based on the queries in the DB, it will check for new listings and process them through the process_listings method in
INotifier.

## Implementation
ways to communicate with the notifier  

! make sure the Redis [server is running](#executing-program) 
### commands
Check out the webserver [API spec](api/webserver_api_spec.yaml) to know which endpoints you can use to manage your queries.  
You can paste the spec in [Swagger](https://editor.swagger.io/) to have a UI.

### discord bot
example of how to handle new listings with [Redis pubsub](https://redis-py.readthedocs.io/en/stable/advanced_features.html#publish-subscribe)
in [discordpy](https://discordpy.readthedocs.io/en/stable/) to be exact

```python
import json
import redis.asyncio as redis
# this import might differ
from marketplace_notifier.notifier.tweedehands.return_models import TweedehandsListingInfo

from discord.ext import tasks, commands

REDIS_SUB_CHANNEL = 'listings'


# in a Cog
class MyCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.redis_client = redis.StrictRedis()
        self.bot.loop.create_task(self.new_listing_reader())


    async def cog_unload(self):
        await self.redis_client.aclose()
    
    
    async def new_listing_reader(self):
        """
        listens in Redis channel for messages and processes them
        """
        async with self.bot.redis_client.pubsub() as pubsub:
            await pubsub.subscribe(REDIS_SUB_CHANNEL)
            logging.info("started listening for new listings...")
            async for msg in pubsub.listen():
                if msg['type'] != 'message':
                    continue
    
                data = msg['data'].decode('utf-8')
                splitted_data = data.split(' ')
                if splitted_data[0] == 'NEW':
                    # NEW <request_url> {"listings": [<serialized TweedehandsListingInfo objects>]}
                    query_url = splitted_data[1]
                    listings_data = json.loads(" ".join(splitted_data[2:]))
                    
                    new_tweedehands_listings_infos = [TweedehandsListingInfo(**l) for l in listings_data['listings']]]
    
                    # do something with the new_tweedehands_listings_infos
                    # ...

# ... setup cog and load the extension
```

## FYI
Queries are a combination of the name of the listing you're using for + some filters (price / location)  

Queries to be monitored are stored in a DB.  
This is to cache already seen listings and update when new ones arrive.

New listings are sent with Redis to the `'listings'` channel.  
a webserver is running (on `http://localhost:5000`) to handle the commands

## Help

For any issues, please create an Issue

