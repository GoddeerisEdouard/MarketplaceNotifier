import json
import traceback
import urllib.parse
from pathlib import Path
from urllib.parse import urlencode, quote_plus, unquote_plus

import tortoise
from aiohttp_retry import RetryClient, ExponentialRetry
from pydantic import BaseModel, Field
from quart import Quart
from quart_schema import QuartSchema, RequestSchemaValidationError, validate_request
from tortoise import Tortoise
from tortoise.contrib.quart import register_tortoise
from tortoise.contrib.pydantic import pydantic_model_creator, pydantic_queryset_creator

from src.shared.models import QueryInfo, Marketplace
from config.config import config

app = Quart(__name__)
app.rc = None
QuartSchema(app)
QueryInfo_Pydantic = pydantic_model_creator(QueryInfo)
QueryInfo_Pydantic_List = pydantic_queryset_creator(QueryInfo)
with open(Path(__file__).parent / "l1_categories.json", "r") as f:
    l1_category_dict = json.load(f)
with open(Path(__file__).parent / "l2_categories.json", "r") as f:
    l2_category_dict = json.load(f)


@app.before_serving
async def startup():
    await Tortoise.init(
        db_url=config["default_db_url"],
        modules={"models": ["src.shared.models"]}
    )
    retry_options = ExponentialRetry()  # default retry of 3, retry on all server errors (5xx)
    app.rc = RetryClient(retry_options=retry_options, raise_for_status=False)


@app.after_serving
async def close_db():
    await Tortoise.close_connections()
    await app.rc.close()


# Input model for validation
class QueryData(BaseModel):
    browser_url: str = Field(pattern=r'^https://www\.2dehands\.be/(q|l)/.*$')


# INPUT: {"browser_url": "https://www.2dehands.be/q/iphone+15+pro/#sortBy:SORT_INDEX|sortOrder:DECREASING"}
@app.post("/query/add_link")
@validate_request(QueryData)
async def create_query_by_link(data: QueryData):
    # add query by browser url
    # this is preferred, as we don't have to locally check/validate if the location filter & price filter etc are correct
    # store it in the DB with a unique ID
    # return a nice json object with all relevant info after parsing
    # ! We don't send any requests! All we're doing is parsing the browser URL to a request URL & storing it in the DB
    parsed_browser_url = urllib.parse.urlparse(data.browser_url)
    params = dict(param.split(':', 1) for param in
                  parsed_browser_url.fragment.split('|')) if parsed_browser_url.fragment != "" else {}
    # example browser_url to better understand the parsing:
    # https://www.2dehands.be/q/iphone+15+pro/#sortBy:SORT_INDEX|sortOrder:DECREASING
    # or
    # https://www.2dehands.be/l/games-en-spelcomputers/#q:ps5|Language:all-languages|sortBy:SORT_INDEX|sortOrder:DECREASING
    path_parts = parsed_browser_url.path.strip('/').split('/')

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
            query_params["l2CategoryId"]: l2_category_dict.get(l1_category_name).get(l2_category_name)[
                "id"]  # only set if there's a subcategory

        if query := params.get("q"):
            query_params["query"] = unquote_plus(query)
    elif path_parts[0] == "q":
        # query without a category
        query_params["query"] = unquote_plus(path_parts[1])

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
    # END of conversion from browser url to request url

    try:
        qi = await QueryInfo.create(request_url=full_request_url, marketplace=Marketplace.TWEEDEHANDS,
                                    query=query_params["query"])
    except tortoise.exceptions.IntegrityError:
        return {
            "error": "Query already exists",
        }, 500
    except Exception as e:
        raise e

    qi_py = await QueryInfo_Pydantic.from_tortoise_orm(qi)
    return qi_py.model_dump(), 200


@app.get("/query")
async def get_all_queries():
    qi_py = await QueryInfo_Pydantic_List.from_queryset(QueryInfo.all())
    return {"queries": qi_py.model_dump()}


@app.get("/query/<query_info_id>")
async def get_query_by_id(query_info_id: int):
    try:
        qi = await QueryInfo.get(id=query_info_id)
    except tortoise.exceptions.DoesNotExist:
        return {
            "error": "Not Found",
        }, 404
    except ValueError:
        return {
            "error": "Invalid query_info_id",
        }, 400
    except Exception as e:
        raise e
    qi_py = await QueryInfo_Pydantic.from_tortoise_orm(qi)
    return qi_py.model_dump()


@app.delete("/query/<query_info_id>")
async def delete_query(query_info_id: int):
    try:
        query = await QueryInfo.get(id=query_info_id)
    except tortoise.exceptions.DoesNotExist:
        return {
            "error": "Not Found",
        }, 404
    except Exception as e:
        raise e

    await query.delete()
    return {"message": "Query deleted"}, 200


@app.errorhandler(RequestSchemaValidationError)
async def handle_request_validation_error(error):
    return {
        "error": str(error.validation_error),
    }, 400


# global error handler for unexpected exceptions
@app.errorhandler(Exception)
async def handle_exception(e: Exception):
    # Optional: log the traceback
    traceback_str = traceback.format_exc()

    # you could log this somewhere instead of returning it in production
    response = {
        "error": "Unexpected error occurred",
        "reason": str(e),
        "trace": traceback_str  # remove in production if not needed
    }
    return response, 500


@app.get("/ping")
async def ping() -> str:
    return "pong"


register_tortoise(
    app,
    db_url=config["default_db_url"],
    modules={"models": ["src.shared.models"]},
    generate_schemas=True,
)

if __name__ == '__main__':
    # run Quart webserver
    app.run(config["webserver_host"], port=5000, debug=True)
