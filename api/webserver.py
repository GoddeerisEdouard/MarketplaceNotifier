from dataclasses import dataclass
from typing import Optional

import tortoise
from aiohttp_retry import RetryClient
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
app.rc = RetryClient()
QuartSchema(app)
QueryInfo_Pydantic = pydantic_model_creator(QueryInfo)
QueryInfo_Pydantic_List = pydantic_queryset_creator(QueryInfo)


@app.before_serving
async def startup():
    await Tortoise.init(
        db_url=DEFAULT_DB_URL,
        modules={"models": ["marketplace_notifier.db_models.models"]}
    )


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
