# MarketplaceNotifier
**Version:** 1.2.0
## What is this?
A service to get notified the second a great deal is listed.  

supported *marketplace* (so far):
- [x] [2dehands](https://www.2dehands.be)

## How does this work?
You simply copy the marketplace link of your web browser and send it in a POST request to the webserver.  
Afterwards, the Redis server will send - if there is any - new listings data (every 2 minutes).  

Simple example:  
> get notified whenever a new iPhone 15 Pro gets listed
> ```sh
> curl -X POST http://localhost:5000/query/add_link \
>      -H "Content-Type: application/json" \
>      -d '{"browser_url": "https://www.2dehands.be/q/iphone+15+pro/"}'
> ```

Now you're automatically monitoring new listings for that browser_url.  

Next step is to handle the incoming new listings data (with Redis).  
New listings data is being sent in the `listings` channel in this format:     
`'{"request_url": <request_url>, "new_listings": [<Listing objects>]}'`  
check [api_models.py](src/misc/api_models.py) for the Listing object structure.

Load the data as josn to access the request_url and new_listings:
```python
json.loads(data["data"])
{"request_url": "https://www.2dehands.be/q/iphone+15+pro/", "new_listings": [<Listing objects>]}
```

Here's an [example](#discord-bot) of handling these messages in discord.py.

## Table of contents

* [Getting Started](#getting-started)
  * [Pre-requisites](#pre-requisites)
  * [Installing](#installing)
    * [Locally](#locally)
    * [Dockerized](#dockerized)
* [Implementation](#implementation)
  * [Add / Delete / Get links to monitor](#add--delete--get-links-to-monitor)
  * [discord bot](#discord-bot)
* [FYI](#fyi)
* [Help](#help)


## Getting Started
### Pre-requisites
* tested on **Python 3.9**
  [requirements.txt](src/marketplace_notifier/requirements.txt) contains all Python packages needed.

### Installing
#### Locally
A **redis server** should be running on port 6379  
Test if the server is running by pinging with `redis-cli`.

webserver to [handle CRUD operations](#implementation) on listing queries  
If on windows, you have to add to PYTHONPATH first to fix some relative imports  
`set PYTHONPATH=%PYTHONPATH%;C:\Users\Admin\Documents\Some Other Folder\MarketplaceNotifier`
```sh
python3 -m venv webserver-venv
source webserver-venv/bin/activate
# or on Windows: webserver-venv\Scripts\activate 
pip3 install -r src/api/requirements.txt
python src/api/webserver.py
```

fetch new listings & sends them with Redis

`set PYTHONPATH=%PYTHONPATH%;C:\Users\Admin\Documents\Some Other Folder\MarketplaceNotifier`
```sh
python3 -m venv notifier-venv
source notifier-venv/bin/activate
# or on Windows: notifier-venv\Scripts\activate 
pip3 install -r src/marketplace_notifier/requirements.txt
python src/marketplace_notifier/main.py
```

#### Dockerized
```shell
docker-compose up -d
```

This starts 3 services:
- the Redis server (handling new listings)
- webserver (Adding/Deleting/Getting queries)
- the notifier (which checks for new listings & sends them to a channel in the Redis server)

## Implementation
ways to communicate with the notifier  

! make sure the Redis server [is running](#executing-program) 
### Add / Delete / Get links to monitor
Once the webserver is running, you can browse to `http://localhost:5000/docs` to check out the endpoints & their responses.

### discord bot
example of how to handle new listings with [Redis pub/sub](https://redis-py.readthedocs.io/en/stable/advanced_features.html#publish-subscribe) in [discordpy](https://discordpy.readthedocs.io/en/stable/) to be exact.

```python
import json
import redis.asyncio as redis

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
        # '<request_url> [<Listing objects>]'}
        splitted_data = json.loads(data)
        request_url = data["request_url"]
        new_listings = data["new_listings"]
        # do something with the new listings
        # ...

    # ... setup cog and load the extension
```

## FYI
Marketplace links to be monitored for new listings are stored in a DB.  
We also store minimal listings data in a DB.
This is to cache already seen listings and update (the latest listing) when new ones arrive.

New listings are sent with Redis to the `'listings'` channel.  
A webserver is running (on `http://localhost:5000`) to handle adding/removing/getting the marketplace links you're monitoring.

Errors during fetching are sent tot the `error_channel` channel.  
So you should definitely also subscribe to that channel.  
These have a format of:
```json
{"error":  "...", "reason":  "...", "traceback":  "..."}
```
! the traceback is optional!

---
There are 3 services:
- a **Redis server** (handles messaging, to send new listings to & read new listings from)
- a **webserver** to add / delete / get links to monitor.
- a **monitor / notifier** which sends new listings (info) to a Redis channel every interval. 

We're using the Redis pub/sub implementation to handle received new listing(s) as soon as possible.  
This is basically a while loop which handles every incoming message/payload.

The monitor service will run and check for new listings every 2 minutes.
Based on the request urls in the DB, it will check for new listings and process them through the process_listings method in
INotifier.
## Help

For any issues, please create an Issue

