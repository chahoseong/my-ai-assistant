import pytest

from app.test_db_safety import (
    UnsafeTestDatabaseError,
    validate_test_database_url,
)


def test_test_database_url_is_required() -> None:
    with pytest.raises(UnsafeTestDatabaseError, match="TEST_DATABASE_URL"):
        validate_test_database_url({"DATABASE_URL": "postgresql://dev"})


def test_test_database_url_cannot_equal_application_database_url() -> None:
    with pytest.raises(UnsafeTestDatabaseError, match="must differ"):
        validate_test_database_url(
            {
                "DATABASE_URL": "postgresql://dev",
                "TEST_DATABASE_URL": "postgresql://dev",
            }
        )


def test_distinct_test_database_url_is_returned() -> None:
    test_url = "postgresql://test"

    assert (
        validate_test_database_url(
            {"DATABASE_URL": "postgresql://dev", "TEST_DATABASE_URL": test_url}
        )
        == test_url
    )
