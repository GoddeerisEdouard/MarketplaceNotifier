from tortoise import Tortoise

DEFAULT_DB_URL = "sqlite://db.sqlite3"


async def init():
    await Tortoise.init(
        db_url=DEFAULT_DB_URL,
        modules={"models": ["db_models.models"]}
    )

    await Tortoise.generate_schemas()
