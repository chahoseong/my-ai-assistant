from collections.abc import Mapping

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine


class UnsafeTestDatabaseError(RuntimeError):
    """Raised when test execution could target an unsafe database."""


def validate_test_database_url(env: Mapping[str, str]) -> str:
    test_url = env.get("TEST_DATABASE_URL")
    if not test_url:
        raise UnsafeTestDatabaseError(
            "TEST_DATABASE_URL must be set; refusing to run database tests"
        )

    database_url = env.get("DATABASE_URL")
    if database_url is not None and test_url == database_url:
        raise UnsafeTestDatabaseError(
            "TEST_DATABASE_URL must differ from DATABASE_URL; refusing to run tests"
        )

    return test_url


async def truncate_test_database(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.execute(text("TRUNCATE TABLE messages, conversations CASCADE"))
