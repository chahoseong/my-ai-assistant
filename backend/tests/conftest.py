import os
import subprocess
import sys
from collections.abc import AsyncIterator
from pathlib import Path

import pytest_asyncio

from app.db import Database, create_database
from app.test_db_safety import (
    truncate_test_database,
    validate_test_database_identity,
    validate_test_database_url,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def upgrade_test_schema(test_url: str) -> None:
    migration_env = dict(os.environ)
    migration_env["DATABASE_URL"] = test_url
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=PROJECT_ROOT,
        env=migration_env,
        check=True,
    )


@pytest_asyncio.fixture
async def test_database() -> AsyncIterator[Database]:
    test_url = validate_test_database_url(os.environ)
    database_url = os.environ["DATABASE_URL"]
    await validate_test_database_identity(database_url, test_url)
    upgrade_test_schema(test_url)
    database = create_database(test_url)

    try:
        await truncate_test_database(database.engine)
        yield database
    finally:
        await truncate_test_database(database.engine)
        await database.dispose()
