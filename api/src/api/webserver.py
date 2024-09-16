from dataclasses import dataclass
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
    cityOrPostalCode: str
    radius: int


@dataclass
class QueryIn:
    query: str
    location_filter: Optional[LocationFilter] = None
    price_range: Optional[PriceRange] = None


# OUTPUT : {query: ..., request_url_ID:..., locationFilter: {city:..., postalCode:..., radius:...}}
# or OUTPUT : {query: ..., request_url_ID:..., locationFilter: null}
@app.post("/query/add")
@validate_request(QueryIn)
async def create_query(data: QueryIn):
    city_and_postal_code = await TweedehandsLocationFilter.get_valid_postal_code_and_city(client_session=app.cs,
                                                                                          postal_code_or_city=data.location_filter.cityOrPostalCode) if data.location_filter else None

    tqs = TweedehandsQuerySpecs(query=data.query,
                                location_filter=TweedehandsLocationFilter(city=city_and_postal_code['city'],
                                                                          postal_code=city_and_postal_code[
                                                                              'postal_code'],
                                                                          radius=data.location_filter.radius) if city_and_postal_code else None,
                                price_range=data.price_range)

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
