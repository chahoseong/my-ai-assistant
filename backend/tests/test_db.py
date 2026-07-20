import importlib
from typing import cast

import pytest
from sqlalchemy.pool import QueuePool

from app.observability import DB_POOL_IN_USE, bind_db_pool_in_use


def db_pool_in_use() -> float:
    for family in DB_POOL_IN_USE.collect():
        for sample in family.samples:
            if sample.name == "db_pool_in_use":
                return sample.value

    raise AssertionError("Missing db_pool_in_use sample")


def test_db_pool_gauge_reads_current_value_from_registered_callback() -> None:
    checked_out = 2
    bind_db_pool_in_use(lambda: checked_out)

    assert db_pool_in_use() == 2

    checked_out = 5
    assert db_pool_in_use() == 5


@pytest.mark.asyncio
async def test_create_database_registers_its_pool_callback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = importlib.import_module("app.db")
    registered_callbacks = []
    monkeypatch.setattr(db, "bind_db_pool_in_use", registered_callbacks.append)

    database = db.create_database(
        "postgresql+asyncpg://assistant:assistant@db/assistant_dev"
    )
    try:
        assert len(registered_callbacks) == 1
        pool = cast(QueuePool, database.engine.sync_engine.pool)
        assert registered_callbacks[0]() == pool.checkedout()
    finally:
        await database.dispose()


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
