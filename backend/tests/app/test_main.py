from fastapi import FastAPI
import pytest


from fastapi.testclient import TestClient

import app.database.dependencies
import app.main

pytestmark = pytest.mark.unit


def test_load_llama_settings_uses_documented_defaults() -> None:
    settings = app.main.load_llama_settings({})

    assert settings.model == "google/gemma-4-E4B-it-qat-q4_0-gguf"
    assert settings.base_url == "http://127.0.0.1:8080/v1"
    assert settings.api_key == "llama.cpp"


def test_load_llama_settings_allows_environment_overrides() -> None:
    settings = app.main.load_llama_settings(
        {
            "LLM_MODEL_NAME": "test-model",
            "LLM_BASE_URL": "http://llama.example/v1",
            "LLM_API_KEY": "test-key",
        }
    )

    assert settings.model == "test-model"
    assert settings.base_url == "http://llama.example/v1"
    assert settings.api_key == "test-key"


def test_create_app_returns_independent_configured_instances() -> None:
    first_app = app.main.create_app()
    second_app = app.main.create_app()

    assert isinstance(first_app, FastAPI)
    assert first_app is not second_app
    assert {
        "/api/auth/signup",
        "/api/conversations",
    } <= first_app.openapi()["paths"].keys()
    assert any(getattr(route, "path", None) == "/metrics" for route in first_app.routes)


def test_application_startup_requires_database_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(app.database.dependencies, "database", None)

    with pytest.raises(ValueError, match="DATABASE_URL must be set"):
        with TestClient(app.main.app):
            pass


def test_application_startup_rejects_insecure_non_local_cookie(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")

    with pytest.raises(ValueError, match="SESSION_COOKIE_SECURE"):
        with TestClient(app.main.app):
            pass
