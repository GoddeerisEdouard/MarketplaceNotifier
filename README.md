# MarketplaceNotifier

monitor and get notified for your queried marketplace listings  
A `Notifier` object with public methods.  
It's then up to the client to process the returned data.

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

```shell
python main.py
```
the program will run and check for new listings every 5 minutes.
Based on the queries in the DB, it will check for new listings and return them.

## FYI
queries to be monitored are stored in a DB.  
This is to cache already seen listings and update when new ones arrive.



## Help

For any issues, please create an Issue

