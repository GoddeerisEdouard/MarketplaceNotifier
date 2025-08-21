# MarketplaceNotifier
**Version:** 1.3.3
## What is this?
A service to get notified the second a great deal is listed.  

supported *marketplace* (so far):
- [x] [2dehands](https://www.2dehands.be)

## How does this work?
You simply copy the marketplace link of your web browser and send it in a POST request to the webserver.  
Afterwards, the Redis server will send - if there is any - new non-ad listings data (every 2 minutes).  
This is done by "long polling".  

example REQUEST:  
> get notified whenever a new iPhone 15 Pro gets listed
> ```sh
> curl -X POST http://localhost:5000/query/add_link \
>      -H "Content-Type: application/json" \
>      -d '{"browser_url": "https://www.2dehands.be/q/iphone+15+pro/"}'
> ```

Now you're automatically monitoring new listings for that browser_url.  
RESPONSE:
```json
{
  "browser_url": "https://www.2dehands.be/q/iphone+15+pro/#Language:all-languages|offeredSince:Gisteren|sortBy:SORT_INDEX|sortOrder:DECREASING",
  "id": 1,
  "status": "ACTIVE",
  "next_check_time": null,
  "query": "iphone 15 pro",
  "request_url": "https://www.2dehands.be/lrp/api/search?attributesByKey%5B%5D=Language%3Aall-languages&attributesByKey%5B%5D=offeredSince%3AGisteren&limit=100&offset=0&sortBy=SORT_INDEX&sortOrder=DECREASING&viewOptions=list-view&query=iphone+15+pro"
}
```
\- yes, your browser_url automatically gets additional filters.


Next step is to handle the incoming new listings data (with Redis).  
New listings data is being sent in the `listings` channel in this format:     
`'{"request_url": <request_url>, "new_listings": [<Listing objects>]}'`  
check [api_models.py](src/misc/api_models.py) for the `<Listing>` object structure.

Load the data as JSON:
`json.loads(data["data"])`
```json
{"request_url": "https://www.2dehands.be/lrp/api/search?attributesByKey%5B%5D=Language%3Aall-languages&attributesByKey%5B%5D=offeredSince%3AGisteren&limit=100&offset=0&sortBy=SORT_INDEX&sortOrder=DECREASING&viewOptions=list-view&query=iphone+15+pro", 
 "new_listings": [<Listing objects>]}
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

running WEBSERVER to [handle CRUD operations](#implementation):  
```sh
python3 -m venv webserver-venv
source webserver-venv/bin/activate # Linux
# webserver-venv\Scripts\activate  # Windows
pip3 install -r src/api/requirements.txt
python src/api/webserver.py
```

NOTIFIER service (which checks for new listings & sends them to a channel in the Redis server):  
```sh
python3 -m venv notifier-venv
source notifier-venv/bin/activate # Linux
# notifier-venv\Scripts\activate # Windows 
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

! make sure a Redis server is running on port 6379. 
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
        # '{"request_url": <request_url>, "new_listings": [<Listing objects>]}'
        splitted_data = json.loads(data)
        request_url = data["request_url"]
        new_listings = data["new_listings"]
        # do something with the new listings
        # be aware, new_listings are sorted from newest to oldest
        # ...

    # ... setup cog and load the extension
```

## FYI
2dehands browser_urls to be monitored for new listings are stored in a DB.  
We also store the latest item_id of a browser_url in the DB.  

New listings are sent with Redis to the `'listings'` channel.  
A webserver is running (on `http://localhost:5000`) to handle adding/removing/getting the 2dehands browser_urls you're monitoring.

---

URL specific errors are sent to `request_url_error`  
The messages are in this format:  
```json
{"request_url": <request_url>, "error": "...", "reason": "...", "traceback": "..."}
```
! the traceback key is optional!  

When this error is raised, the monitor service will stop monitoring that specific URL.  
It'll also set the status to `FAILED` in the DB.  
You can set the status back to `ACTIVE` by sending a POST request to `/query/status`.  
(check the API endpoints for the exact payload format)

---

Generic warning messages are sent to `warning` channel  
```json
{"message": "...",
"reason":  "..."}
```
Example of a warning can be -> too many URLs are being fetched together.  
This may cause the risk of being ratelimited.

---
There are 3 services:
- a **Redis server** (handles messaging, to send new listings to & read new listings from)
- a **webserver** to add / delete / get links to monitor.
- a **monitor / notifier** which sends new non-ad listings to a Redis channel every interval. 

We're using the Redis pub/sub implementation to handle received new listing(s) as soon as possible.  
This is basically a while loop which handles every incoming message/payload.

The monitor service will run and check for new listings every 2 minutes.
## Help

For any issues, please create an Issue

