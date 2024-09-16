from dataclasses import dataclass
from math import radians
from typing import Optional

import aiohttp
import tortoise
from quart import Quart
from quart_schema import validate_request, QuartSchema, RequestSchemaValidationError
from tortoise import Tortoise
from tortoise.contrib.quart import register_tortoise

from marketplace_notifier.db_models.models import QueryInfo
from marketplace_notifier.notifier.models import PriceRange
from marketplace_notifier.notifier.tweedehands.models import TweedehandsLocationFilter, TweedehandsQuerySpecs
import constants

app = Quart(__name__)
QuartSchema(app)


@app.before_serving
async def startup():
    await Tortoise.init(
        db_url=constants.DEFAULT_DB_URL,
        modules={"models": ["marketplace_notifier.db_models.models"]}
    )
    app.cs = aiohttp.ClientSession()


@app.after_serving
async def close_db():
    await Tortoise.close_connections()
    await app.cs.close()


@dataclass
class LocationFilter:
    city_or_postal_code: str
    radius: int


@dataclass
class QueryIn:
    query: str
    location_filter: Optional[LocationFilter] = None
    price_range: Optional[PriceRange] = None


# OUTPUT : {"browser_query_url": "", "location_filter": {"city": "", "postal_code": null, "radius": null}, "price_range": null, "query": "", "request_query_url": ""}
@app.post("/query/add")
@validate_request(QueryIn)
async def create_query(data: QueryIn):
    city_and_postal_code = await TweedehandsLocationFilter.get_valid_postal_code_and_city(client_session=app.cs,
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
        await QueryInfo.create(request_url=tqs.request_query_url, marketplace='TWEEDEHANDS', query=tqs.query)
    except tortoise.exceptions.IntegrityError:
        return {
            "error": "Query already exists",
        }, 500

    return tqs.model_dump()


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
    db_url=constants.DEFAULT_DB_URL,
    modules={"models": ["marketplace_notifier.db_models.models"]},
    generate_schemas=True,
)

if __name__ == '__main__':
    # run Quart webserver
    app.run('0.0.0.0', port=5000, debug=True)
