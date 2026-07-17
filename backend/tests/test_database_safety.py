import pytest

from app.test_db_safety import (
    UnsafeTestDatabaseError,
    validate_test_database_identity,
    validate_test_database_url,
)


def test_test_database_url_is_required() -> None:
    with pytest.raises(UnsafeTestDatabaseError, match="TEST_DATABASE_URL"):
        validate_test_database_url({"DATABASE_URL": "postgresql://dev"})


def test_application_database_url_is_required_for_safety_comparison() -> None:
    with pytest.raises(UnsafeTestDatabaseError, match="DATABASE_URL"):
        validate_test_database_url({"TEST_DATABASE_URL": "postgresql://test"})


def test_test_database_url_cannot_equal_application_database_url() -> None:
    with pytest.raises(UnsafeTestDatabaseError, match="must differ"):
        validate_test_database_url(
            {
                "DATABASE_URL": "postgresql://dev",
                "TEST_DATABASE_URL": "postgresql://dev",
            }
        )


@pytest.mark.asyncio
async def test_database_host_aliases_cannot_bypass_safety_comparison() -> None:
    with pytest.raises(UnsafeTestDatabaseError, match="same database"):
        await validate_test_database_identity(
            "postgresql+asyncpg://assistant:assistant@localhost:5432/assistant_dev",
            "postgresql+asyncpg://assistant:assistant@127.0.0.1:5432/assistant_dev",
        )


def test_distinct_test_database_url_is_returned() -> None:
    test_url = "postgresql://test"

    assert (
        validate_test_database_url(
            {"DATABASE_URL": "postgresql://dev", "TEST_DATABASE_URL": test_url}
        )
        == test_url
    )
