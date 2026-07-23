import importlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


PROJECT_ROOT = Path(__file__).resolve().parents[2]


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


def test_weather_settings_require_an_identifying_geocoder_user_agent() -> None:
    config = importlib.import_module("app.config")

    with pytest.raises(ValueError, match="NOMINATIM_USER_AGENT"):
        config.load_weather_settings({})


def test_weather_settings_allow_provider_endpoint_replacement() -> None:
    config = importlib.import_module("app.config")

    settings = config.load_weather_settings(
        {
            "NOMINATIM_USER_AGENT": "my-ai-assistant/0.1 (contact@example.com)",
            "NOMINATIM_BASE_URL": "https://geocoder.example.test",
            "OPEN_METEO_BASE_URL": "https://weather.example.test",
        }
    )

    assert settings.geocoder_user_agent == "my-ai-assistant/0.1 (contact@example.com)"
    assert settings.geocoder_base_url == "https://geocoder.example.test"
    assert settings.weather_base_url == "https://weather.example.test"


def test_opgg_tft_settings_are_disabled_without_a_remote_url() -> None:
    config = importlib.import_module("app.config")

    settings = config.load_opgg_tft_settings({})

    assert settings.mcp_url is None
    assert settings.cache_ttl_seconds == 300.0


def test_opgg_tft_settings_accept_a_url_and_cache_ttl() -> None:
    config = importlib.import_module("app.config")

    settings = config.load_opgg_tft_settings(
        {
            "OPGG_MCP_URL": "https://opgg.example/mcp",
            "OPGG_TFT_CACHE_TTL_SECONDS": "45",
        }
    )

    assert settings.mcp_url == "https://opgg.example/mcp"
    assert settings.cache_ttl_seconds == 45.0


def test_non_local_environment_requires_secure_cookie() -> None:
    config = importlib.import_module("app.config")

    with pytest.raises(ValueError, match="SESSION_COOKIE_SECURE"):
        config.load_auth_settings({"APP_ENV": "production"})


def test_auth_settings_default_to_vite_development_origins() -> None:
    config = importlib.import_module("app.config")

    settings = config.load_auth_settings({})

    assert settings.allowed_origins == frozenset(
        {"http://127.0.0.1:5173", "http://localhost:5173"}
    )


def test_auth_settings_parse_exact_allowed_origins() -> None:
    config = importlib.import_module("app.config")

    settings = config.load_auth_settings(
        {
            "APP_ENV": "production",
            "SESSION_COOKIE_SECURE": "true",
            "AUTH_ALLOWED_ORIGINS": "https://app.example.com, http://localhost:5173,",
        }
    )

    assert settings.app_env == "production"
    assert settings.cookie_secure is True
    assert settings.allowed_origins == frozenset(
        {"https://app.example.com", "http://localhost:5173"}
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
            "tests/app/test_config.py::test_load_database_settings_reads_database_url",
        ],
        cwd=PROJECT_ROOT,
        env=test_environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
