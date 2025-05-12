import json
import urllib.parse
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlencode, quote_plus

import tortoise
from aiohttp_retry import RetryClient, ExponentialRetry
from quart import Quart
from quart_schema import validate_request, QuartSchema, RequestSchemaValidationError
from tortoise import Tortoise
from tortoise.contrib.quart import register_tortoise
from tortoise.contrib.pydantic import pydantic_model_creator, pydantic_queryset_creator

from marketplace_notifier.db_models.models import QueryInfo
from marketplace_notifier.notifier.models import PriceRange
from marketplace_notifier.notifier.tweedehands.models import TweedehandsLocationFilter, TweedehandsQuerySpecs
from config.config import config

DEFAULT_DB_URL = f"sqlite://{config['database_path']}/db.sqlite3"

app = Quart(__name__)
app.rc = None
QuartSchema(app)
QueryInfo_Pydantic = pydantic_model_creator(QueryInfo)
QueryInfo_Pydantic_List = pydantic_queryset_creator(QueryInfo)
with open("l1_categories.json", "r") as f:
    l1_category_dict = json.load(f)
with open("l2_categories.json", "r") as f:
    l2_category_dict = json.load(f)


@app.before_serving
async def startup():
    await Tortoise.init(
        db_url=DEFAULT_DB_URL,
        modules={"models": ["marketplace_notifier.db_models.models"]}
    )
    retry_options = ExponentialRetry()  # default retry of 3, retry on all server errors (5xx)
    app.rc = RetryClient(retry_options=retry_options, raise_for_status=False)


@app.after_serving
async def close_db():
    await Tortoise.close_connections()
    await app.rc.close()


@dataclass
class LocationFilter:
    city_or_postal_code: str
    radius: int


@dataclass
class QueryIn:
    query: str
    location_filter: Optional[LocationFilter] = None
    price_range: Optional[PriceRange] = None


# OUTPUT : {"id": 123, "browser_query_url": "", "location_filter": {"city": "", "postal_code": null, "radius": null}, "price_range": null, "query": "", "request_query_url": ""}
@app.post("/query/add")
@validate_request(QueryIn)
async def create_query(data: QueryIn):
    city_and_postal_code = await TweedehandsLocationFilter.get_valid_postal_code_and_city(retry_client=app.rc,
                                                                                          postal_code_or_city=data.location_filter.city_or_postal_code) if data.location_filter else None
    # validate filters
    lf = TweedehandsLocationFilter(city=city_and_postal_code['city'],
                                   postal_code=city_and_postal_code[
                                       'postal_code'],
                                   radius=data.location_filter.radius) if city_and_postal_code and int(
        data.location_filter.radius) > 0 else None

    price_range = PriceRange(min_price_cents=data.price_range.min_price_cents,
                             max_price_cents=data.price_range.max_price_cents) if data.price_range and data.price_range.min_price_cents >= 0 and data.price_range.max_price_cents > data.price_range.min_price_cents else None

    # fill model with validated data
    tqs = TweedehandsQuerySpecs(query=data.query,
                                location_filter=lf,
                                price_range=price_range)

    try:
        qi = await QueryInfo.create(request_url=tqs.request_query_url, marketplace='TWEEDEHANDS', query=tqs.query)
    except tortoise.exceptions.IntegrityError:
        return {
            "error": "Query already exists",
        }, 500

    return_model = tqs.model_dump()
    return_model['id'] = qi.id
    return return_model, 200


# INPUT: {"browser_url": "https://www.2dehands.be/q/iphone+15+pro/#sortBy:SORT_INDEX|sortOrder:DECREASING"}
@app.post("/query/add_link")
async def create_query_by_link(data):
    # add query by browser url
    # this is preferred, as we don't have to locally check/validate if the location filter & price filter etc are correct
    # store it in the DB with a unique ID
    # return a nice json object with all relevant info after parsing
    # ! don't send a request yet! all we're doing is adding our parsed link in our DB!
    parsed_browser_url = urllib.parse.urlparse(data.browser_url)
    fragment = parsed_browser_url.fragment or []
    params = dict(param.split(':', 1) for param in fragment.split('|'))

    # example browser_url to better understand the parsing:
    # https://www.2dehands.be/q/iphone+15+pro/#sortBy:SORT_INDEX|sortOrder:DECREASING
    # or
    # https://www.2dehands.be/l/games-en-spelcomputers/#q:ps5|Language:all-languages|sortBy:SORT_INDEX|sortOrder:DECREASING
    path_parts = parsed_browser_url.path.strip('/').split('/')

    l1_category_name = None
    l2_category_name = None
    query_params = {
        "attributesByKey[]": ["Language:all-languages", "offeredSince:Gisteren"],
        "limit": 30,  # sometimes, even when we post a listing, it instantly gets on the second or even third page
        # even when the listings are sorted by date...: this makes sure we fetch all listings from the first 3 (and a half) pages
        # so we might have to increase the limit in the future
        "offset": 0,
        "sortBy": "SORT_INDEX",
        "sortOrder": "DECREASING",
        "viewOptions": "list-view"
    }
    if path_parts[0] == "l":
        # queried with a category as filter
        l1_category_name = path_parts[1]
        query_params["l1CategoryId"] = l1_category_dict.get(l1_category_name)["id"]
        if len(path_parts) > 2:
            l2_category_name = path_parts[2]
            query_params["l2CategoryId"]: l2_category_dict.get(l1_category_name).get(l2_category_name)["id"]  # only set if there's a subcategory

        if query := params.get("q"):
            query_params["query"] = query
    elif path_parts[0] == "q":
        # query without a category
        query_params["query"] = path_parts[1]

    if postcode := params.get("postcode"):
        query_params["postcode"] = postcode
        # because we only want to add a distance if there's a postcode
        if distance := params.get("distanceMeters"):
            query_params["distanceMeters"] = distance

    if postcode := params.get("postcode"):
        query_params["postcode"] = postcode
        # because we only want to add a distance if there's a postcode
        if distance := params.get("distanceMeters"):
            query_params["distanceMeters"] = distance

    query_string = urlencode(query_params, doseq=True, quote_via=quote_plus)

    full_request_url = "https://www.2dehands.be/lrp/api/search?" + query_string
    try:
        qi = await QueryInfo.create(request_url=full_request_url, marketplace='TWEEDEHANDS',
                                    query=query_params["query"])
    except tortoise.exceptions.IntegrityError:
        return {
            "error": "Query already exists",
        }, 500

    return qi, 200


@app.get("/query")
async def get_all_queries():
    qi_py = await QueryInfo_Pydantic_List.from_queryset(QueryInfo.all())
    return qi_py.model_dump_json()


@app.get("/query/<query_info_id>")
async def get_query_by_id(query_info_id: int):
    try:
        qi = await QueryInfo.get(id=query_info_id)
    except tortoise.exceptions.DoesNotExist:
        return {
            "error": "Not Found",
        }, 404
    qi_py = await QueryInfo_Pydantic.from_tortoise_orm(qi)
    return qi_py.model_dump_json()


@app.delete("/query/<query_info_id>")
async def delete_query(query_info_id: int):
    query = await QueryInfo.get(id=query_info_id)
    await query.delete()
    return {"message": "Query deleted"}, 200


@app.errorhandler(RequestSchemaValidationError)
async def handle_request_validation_error(error):
    return {
        "error": str(error.validation_error),
    }, 400


@app.get("/ping")
async def ping() -> str:
    return "pong"


register_tortoise(
    app,
    db_url=DEFAULT_DB_URL,
    modules={"models": ["marketplace_notifier.db_models.models"]},
    generate_schemas=True,
)

if __name__ == '__main__':
    # run Quart webserver
    app.run(config["webserver_host"], port=5000, debug=True)
