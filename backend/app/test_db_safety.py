import asyncio
from collections.abc import Mapping
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool


class UnsafeTestDatabaseError(RuntimeError):
    """Raised when test execution could target an unsafe database."""


@dataclass(frozen=True)
class DatabaseIdentity:
    database_name: str
    system_identifier: int


def validate_test_database_url(env: Mapping[str, str]) -> str:
    test_url = env.get("TEST_DATABASE_URL")
    if not test_url:
        raise UnsafeTestDatabaseError(
            "TEST_DATABASE_URL must be set; refusing to run database tests"
        )

    database_url = env.get("DATABASE_URL")
    if not database_url:
        raise UnsafeTestDatabaseError(
            "DATABASE_URL must be set for test database safety comparison"
        )

    if test_url == database_url:
        raise UnsafeTestDatabaseError(
            "TEST_DATABASE_URL must differ from DATABASE_URL; refusing to run tests"
        )

    return test_url


async def fetch_database_identity(url: str) -> DatabaseIdentity:
    engine = create_async_engine(url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            result = await connection.execute(
                text(
                    """
                    SELECT current_database() AS database_name,
                           system_identifier
                    FROM pg_control_system()
                    """
                )
            )
            row = result.one()._mapping
            return DatabaseIdentity(
                database_name=str(row["database_name"]),
                system_identifier=int(row["system_identifier"]),
            )
    finally:
        await engine.dispose()


async def validate_test_database_identity(
    database_url: str,
    test_url: str,
) -> None:
    application_identity, test_identity = await asyncio.gather(
        fetch_database_identity(database_url),
        fetch_database_identity(test_url),
    )
    if application_identity == test_identity:
        raise UnsafeTestDatabaseError(
            "TEST_DATABASE_URL points to the same database as DATABASE_URL; "
            "refusing to run tests"
        )


async def truncate_test_database(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.execute(text("TRUNCATE TABLE messages, conversations CASCADE"))
