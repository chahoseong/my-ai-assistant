import importlib

import pytest


@pytest.mark.asyncio
async def test_create_database_binds_new_session_to_async_engine() -> None:
    db = importlib.import_module("app.db")
    database = db.create_database(
        "postgresql+asyncpg://assistant:assistant@db/assistant_dev"
    )

    session = database.session_factory()
    try:
        assert session.bind is database.engine
    finally:
        await session.close()
        await database.dispose()
