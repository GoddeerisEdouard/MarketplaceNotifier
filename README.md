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

