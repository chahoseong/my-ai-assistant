import os
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import load_database_settings
from app.database.core import Database, create_database


database: Database | None = None


def get_database() -> Database:
    global database
    if database is None:
        settings = load_database_settings(os.environ)
        database = create_database(settings.url)
    return database


async def dispose_database() -> None:
    global database
    current_database = database
    database = None
    if current_database is not None:
        await current_database.dispose()


async def get_session() -> AsyncIterator[AsyncSession]:
    current_database = get_database()
    async with current_database.session_factory() as session:
        yield session
