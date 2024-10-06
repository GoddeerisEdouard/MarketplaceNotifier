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

webserver to handle CRUD operations on listing queries
```python
python api/src/api/webserver.py
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

**ADD** queries to monitor
- `POST localhost:5000/query/add`
```yaml
{
  "query": "...",
  "location_filter": {
    "cityOrPostalCode": "...",
    "radius": 10
  },
  "price_range": {
    "min_price_cents": 0,
    "max_price_cents": 100000
  }
}
```
> ! `location_filter` and `price_range` can be null

python example:
```python
import requests

WEBSERVER_URL = 'localhost:5000'
payload = 
        {"query": query, 
        "location_filter": {"cityOrPostalCode": cityOrPostalCode, "radius": radius},
        "price_range": {"min_price_cents": 0, "max_price_cents": 100000}
        }
response = requests.post(f'http://{WEBSERVER_URL}/add_query', json=payload)
response_data = response.json()
```
---

**GET** queries to monitor  
get all queryinfo objects
- `GET localhost:5000/query/`

get queryinfo object by ID
- `GET localhost:5000/query/<query_info_id>`
---

**DELETE** query
- `DELETE localhost:5000/query/<query_info_id>`

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

queries to be monitored are stored in a DB.  
This is to cache already seen listings and update when new ones arrive.

new listings are sent with Redis to the `'listings'` channel.  
a webserver is running (on `http://localhost:5000`) to handle the commands

## Help

For any issues, please create an Issue

