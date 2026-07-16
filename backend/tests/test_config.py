import importlib

import pytest


def test_load_database_settings_reads_database_url() -> None:
    config = importlib.import_module("app.config")

    settings = config.load_database_settings(
        {"DATABASE_URL": "postgresql+asyncpg://assistant:assistant@db/assistant_dev"}
    )

    assert settings.url == "postgresql+asyncpg://assistant:assistant@db/assistant_dev"


def test_load_database_settings_rejects_missing_database_url() -> None:
    config = importlib.import_module("app.config")

    with pytest.raises(ValueError, match="DATABASE_URL must be set"):
        config.load_database_settings({})
