import logging
from collections.abc import AsyncIterator

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
import pytest
from fastapi.testclient import TestClient

import app.dependencies
import app.main


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app.main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


def test_load_llama_settings_uses_documented_defaults() -> None:
    settings = app.main.load_llama_settings({})

    assert settings.model == "google/gemma-4-E4B-it-qat-q4_0-gguf"
    assert settings.base_url == "http://127.0.0.1:8080/v1"
    assert settings.api_key == "llama.cpp"


def test_load_llama_settings_allows_environment_overrides() -> None:
    settings = app.main.load_llama_settings(
        {
            "LLAMA_MODEL": "test-model",
            "LLAMA_BASE_URL": "http://llama.example/v1",
            "LLAMA_API_KEY": "test-key",
        }
    )

    assert settings.model == "test-model"
    assert settings.base_url == "http://llama.example/v1"
    assert settings.api_key == "test-key"


def test_application_exposes_fastapi_app() -> None:
    assert isinstance(app.main.app, FastAPI)


def test_application_startup_requires_database_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(app.dependencies, "database", None)

    with pytest.raises(ValueError, match="DATABASE_URL must be set"):
        with TestClient(app.main.app):
            pass


def test_configure_logger_adds_one_console_handler_without_propagation() -> None:
    app.main.configure_logger()
    app.main.configure_logger()

    assert app.main.logger.name == "app"
    console_handlers = [
        handler
        for handler in app.main.logger.handlers
        if type(handler) is logging.StreamHandler
    ]

    assert len(console_handlers) == 1
    assert app.main.logger.propagate is False


def test_configure_logger_receives_child_router_logs() -> None:
    class RecordingHandler(logging.Handler):
        def __init__(self) -> None:
            super().__init__()
            self.records: list[logging.LogRecord] = []

        def emit(self, record: logging.LogRecord) -> None:
            self.records.append(record)

    app.main.configure_logger()
    recording_handler = RecordingHandler()
    app.main.logger.addHandler(recording_handler)
    try:
        logging.getLogger("app.routers.chat").error("router_log_probe")
    finally:
        app.main.logger.removeHandler(recording_handler)

    assert [record.getMessage() for record in recording_handler.records] == [
        "router_log_probe"
    ]


@pytest.mark.asyncio
async def test_legacy_chat_endpoint_is_removed(client: AsyncClient) -> None:
    response = await client.post("/api/chat", json={"message": "hello"})

    assert response.status_code == 404
