import json
import traceback
import re
import urllib.parse
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode, quote_plus, unquote_plus

import tortoise
from aiohttp import ClientResponseError
from pydantic import BaseModel, Field
from quart import Quart
from quart_schema import QuartSchema, RequestSchemaValidationError, validate_request, Info, document_response, \
    validate_querystring
from tortoise import Tortoise
from tortoise.contrib.quart import register_tortoise
from tortoise.contrib.pydantic import pydantic_model_creator, pydantic_queryset_creator

from shared.api_utils import get_retry_client
from shared.constants import TWEEDEHANDS_BROWSER_URL_REGEX
from src.shared.api_utils import get_request_response
from src.shared.models import QueryInfo, QueryStatus
from config.config import config

app = Quart(__name__)
app.rc = None
API_VERSION = "1.2.9"  # always edit this in the README too
QuartSchema(app, info=Info(title="Marketplace Monitor API", version=API_VERSION))
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
    app.rc = get_retry_client()


@app.after_serving
async def close_db():
    await Tortoise.close_connections()
    await app.rc.close()

class QueryArgs(BaseModel):
    request_url: Optional[str] = None

# Input model for validation
class QueryData(BaseModel):
    browser_url: str = Field(pattern=TWEEDEHANDS_BROWSER_URL_REGEX)


# response models (for OpenAPI documentation)
class QueryInfoListResponse(BaseModel):
    queries: Optional[QueryInfo_Pydantic_List] = Field(description="List of QueryInfos in the database")

# input model for updating QueryInfo status
class UpdateQueryStatus(BaseModel):
    status: QueryStatus = Field(..., description="Set the status of the query")
    id: int = Field(..., description="ID of the QueryInfo to update status for")

# INPUT: {"browser_url": "https://www.2dehands.be/q/iphone+15+pro/#sortBy:SORT_INDEX|sortOrder:DECREASING"}
# or
# {"browser_url": "https://www.2dehands.be/l/games-en-spelcomputers/#q:ps5|Language:all-languages|sortBy:SORT_INDEX|sortOrder:DECREASING"}
@app.post("/query/add_link")
@validate_request(QueryData)
async def create_query_by_link(data: QueryData):
    # add query by browser url
    # this is preferred, as we don't have to locally check/validate if the location filter & price filter etc are correct
    # store it in the DB with a unique ID
    # ! We don't send any requests! All we're doing is parsing the browser URL to a request URL & storing it in the DB
    parsed_browser_url = urllib.parse.urlparse(data.browser_url)
    params = dict(param.split(':', 1) for param in
                  parsed_browser_url.fragment.split('|')) if parsed_browser_url.fragment != "" else {}

    # we will alwqys add extra filters to the browser url if they're not present
    # #Language:all-languages|offeredSince:Gisteren|sortBy:SORT_INDEX|sortOrder:DECREASING(|postcode:...|distanceMeters:...|priceMin:...|priceMax:...)
    default_filters = {
        "Language": "all-languages",
        "offeredSince": "Gisteren",
        "sortBy": "SORT_INDEX",
        "sortOrder": "DECREASING"
    }

    # set filters if not present
    for filterKey, filterValue in default_filters.items():
        if params.get(filterKey) != filterValue:
            params[filterKey] = filterValue

    filtered_fragment = "|".join(f"{key}:{value}" for key, value in params.items())
    # correct filters = at least Language:all-languages, offeredSince:Gisteren, sortBy:SORT_INDEX, sortOrder:DECREASING

    if not parsed_browser_url.path.endswith("/"):
        # this makes sure when creating the browser url again, we don't get a url which looks like
        # https://www.2dehands.be/q/iphone+15+pro#sortBy:SORT_INDEX|...
        # but instead, looks like https://www.2dehands.be/q/iphone+15+pro/#sortBy:SORT_INDEX...
        parsed_browser_url = parsed_browser_url._replace(path=parsed_browser_url.path + "/")

    browser_url_with_correct_filters = parsed_browser_url._replace(fragment=filtered_fragment).geturl()

    path_parts = parsed_browser_url.path.strip('/').split('/')

    query_params = {
        "attributesByKey[]": ["Language:all-languages", "offeredSince:Gisteren"],
        "limit": 100,  # sometimes, even when we post a listing, it instantly gets on the second or even third page
        # even when the listings are sorted by date...: this makes sure we fetch all listings from the first 3 (and a half) pages
        "offset": 0,
        "sortBy": "SORT_INDEX",
        "sortOrder": "DECREASING",
        "viewOptions": "list-view"
    }
    if path_parts[0] == "l":
        # queried with a category as filter
        l1_category_name = path_parts[1]
        l1_category_value = l1_category_dict.get(l1_category_name)
        if l1_category_value is None:
            raise ValueError(f"Invalid browser url: l1 category ({l1_category_name}) not found")
        query_params["l1CategoryId"] = l1_category_value["id"]
        if len(path_parts) > 2:
            l2_category_name = path_parts[2]
            l2_category_value = l2_category_dict.get(l1_category_name).get(l2_category_name)
            if l2_category_value is None:
                raise ValueError(f"Invalid browser url: l2 category ({l2_category_name}) not found")
            query_params["l2CategoryId"] = l2_category_value["id"]  # only set if there's a subcategory

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

    min_price = params.get("PriceCentsFrom")
    max_price = params.get("PriceCentsTo")
    if min_price or max_price:
        query_params["attributeRanges[]"] = [f"PriceCents:{min_price or 'null'}:{max_price or 'null'}"]

    query_string = urlencode(query_params, doseq=True, quote_via=quote_plus)

    full_request_url = "https://www.2dehands.be/lrp/api/search?" + query_string
    # END of conversion from browser url to request url

    try:
        qi = await QueryInfo.create(browser_url=browser_url_with_correct_filters, request_url=full_request_url,
                                    query=query_params.get("query"))
    except tortoise.exceptions.IntegrityError:
        return {
            "error": "Query already exists",
        }, 500
    except Exception as e:
        raise e

    qi_py = await QueryInfo_Pydantic.from_tortoise_orm(qi)
    return qi_py.model_dump(), 200

@app.post("/query/status")
@validate_request(UpdateQueryStatus)
async def set_query_status(data: UpdateQueryStatus):
    # even if the filter doesn't match anything, no error will be thrown
    updated_count = await QueryInfo.filter(id=data.id).update(status=data.status)
    if updated_count == 0:
        return {"error": "QueryInfo not found"}, 404
    return {}, 204

@app.get("/query")
@validate_querystring(QueryArgs)
@document_response(model_class=QueryInfoListResponse)
async def get_all_queries(query_args: QueryArgs):
    if request_url := query_args.request_url:
        qi_py = await QueryInfo_Pydantic_List.from_queryset(QueryInfo.filter(request_url=request_url).all())
    else:
        qi_py = await QueryInfo_Pydantic_List.from_queryset(QueryInfo.all())
    return {"queries": qi_py.model_dump()}


@app.get("/query/<query_info_id>")
@document_response(model_class=QueryInfo_Pydantic)
async def get_query_by_id(query_info_id: int):
    try:
        qi = await QueryInfo.get(id=query_info_id)
    except tortoise.exceptions.DoesNotExist:
        return {
            "error": "Not Found",
        }, 404
    except ValueError:
        raise ValueError("Invalid query_info_id")
    except Exception as e:
        raise e
    qi_py = await QueryInfo_Pydantic.from_tortoise_orm(qi)
    return qi_py.model_dump()

# ! be aware that this can throw ClientResponseError 404 if item is "expired"
# bcs it requests from an external API
@app.get("/item/<item_id>")
async def get_additional_listing_info(item_id: str):
    # TODO: create reponse model
    # returns additional info of a listing
    # being the minimum bid, the current bids
    # as well as the seller's info (ID/bank verified, reviews, etc.)

    # response example:
    # {
    #     "bidsInfo": {
    #         "bids": [
    #             {
    #                 "date": "2025-06-05T17:22:22Z",
    #                 "id": 1498104034,
    #                 "user": {
    #                     "id": 11111111,
    #                     "nickname": "a bidder nickname"
    #                 },
    #                 "value": 36000
    #             }
    #         ],
    #         "currentMinimumBid": 30000, # THIS IS AN OPTIONAL FIELD
    #         # if this is not present, it means there's no minimum bid for the listing (just "BIEDEN")
    #         it's also possible that this is 0 or -1, which means the same (just "BIEDEN")
    #         "isBiddingEnabled": true, # be aware, if this is false, the listing is not for bidding
    #         "isRemovingBidEnabled": false
    #     },
    #     "sellerInfo": {
    #         "averageScore": 0,
    #         "bankAccount": false,
    #         "identification": false,
    #         "numberOfReviews": 0,
    #         "paymentMethod": {
    #             "name": "bancontact"
    #         },
    #         "phoneNumber": true,
    #         "profilePictures": {},
    #         "salesRepresentatives": [],
    #         "smbVerified": false
    #     }
    # }

    url = f"https://www.2dehands.be/{item_id}"

    response = await get_request_response(retry_client=app.rc, URI=url, json_response=False)

    match = re.search(r'window\.__CONFIG__\s*=\s*(\{.*?\});', response, re.DOTALL)
    if not match:
        raise Exception("Failed to find window.__CONFIG__ in the response")

    config_json_str = match.group(1)
    window_config = json.loads(config_json_str)

    listing = window_config["listing"]
    seller_id = listing["seller"]["id"]

    result = {"bidsInfo": listing["bidsInfo"]}
    url = f"https://www.2dehands.be/v/api/seller-profile/{seller_id}"
    seller_response = await get_request_response(retry_client=app.rc, URI=url)
    result["sellerInfo"] = seller_response

    return result


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


@app.errorhandler(ValueError)
async def handle_value_error(error):
    return {
        "error": f"ValueError: {str(error)}",
    }, 400


# Handle ClientResponseError specifically
@app.errorhandler(ClientResponseError)
async def handle_client_response_error(e: ClientResponseError):
    traceback_str = traceback.format_exc()

    response = {
        "error": type(e).__name__,
        "reason": str(e),
        "trace": traceback_str
    }

    return response, e.status

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
