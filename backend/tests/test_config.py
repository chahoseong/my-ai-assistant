import importlib
import os
import subprocess
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


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


def test_non_local_environment_requires_secure_cookie() -> None:
    config = importlib.import_module("app.config")

    with pytest.raises(ValueError, match="SESSION_COOKIE_SECURE"):
        config.load_auth_settings({"APP_ENV": "production"})


def test_auth_settings_parse_exact_allowed_origins() -> None:
    config = importlib.import_module("app.config")

    settings = config.load_auth_settings(
        {
            "APP_ENV": "production",
            "SESSION_COOKIE_SECURE": "true",
            "AUTH_ALLOWED_ORIGINS": "https://app.example.com, http://localhost:8000,",
        }
    )

    assert settings.app_env == "production"
    assert settings.cookie_secure is True
    assert settings.allowed_origins == frozenset(
        {"https://app.example.com", "http://localhost:8000"}
    )


def test_auth_settings_reject_invalid_secure_boolean() -> None:
    config = importlib.import_module("app.config")

    with pytest.raises(ValueError, match="SESSION_COOKIE_SECURE"):
        config.load_auth_settings({"SESSION_COOKIE_SECURE": "yes"})


def test_unit_tests_can_run_without_database_urls() -> None:
    test_environment = dict(os.environ)
    test_environment.pop("DATABASE_URL", None)
    test_environment.pop("TEST_DATABASE_URL", None)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "tests/test_config.py::test_load_database_settings_reads_database_url",
        ],
        cwd=PROJECT_ROOT,
        env=test_environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
