import logging
from collections.abc import AsyncIterator, Sequence

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic_ai import ModelMessage, ModelRequest
import pytest

import app.main


class FakeStreamResult:
    def __init__(self) -> None:
        self.delta_requested: bool | None = None

    async def __aenter__(self) -> "FakeStreamResult":
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def stream_text(self, *, delta: bool) -> AsyncIterator[str]:
        self.delta_requested = delta
        yield "Hello"
        yield " world"


class FakeAgent:
    def __init__(self) -> None:
        self.message: str | None = None
        self.message_history: Sequence[ModelMessage] | None = None
        self.result = FakeStreamResult()

    def run_stream(
        self,
        message: str,
        *,
        message_history: Sequence[ModelMessage] | None = None,
    ) -> FakeStreamResult:
        self.message = message
        self.message_history = message_history
        return self.result


class FailingStream:
    async def __aenter__(self) -> None:
        raise RuntimeError("connection refused")

    async def __aexit__(self, *args: object) -> None:
        return None


class FailingAgent:
    def run_stream(
        self,
        message: str,
        *,
        message_history: Sequence[ModelMessage] | None = None,
    ) -> FailingStream:
        return FailingStream()


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


def test_configure_logger_adds_one_console_handler_without_propagation() -> None:
    app.main.configure_logger()
    app.main.configure_logger()

    console_handlers = [
        handler
        for handler in app.main.logger.handlers
        if type(handler) is logging.StreamHandler
    ]

    assert len(console_handlers) == 1
    assert app.main.logger.propagate is False


@pytest.mark.asyncio
async def test_chat_streams_agent_text_deltas(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_agent = FakeAgent()
    monkeypatch.setattr(app.main, "agent", fake_agent)

    async with client.stream(
        "POST", "/api/chat", json={"message": "hello"}
    ) as response:
        body = "".join([chunk async for chunk in response.aiter_text()])

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "data: Hello" in body
    assert "data:  world" in body
    assert fake_agent.message == "hello"
    assert fake_agent.result.delta_requested is True


@pytest.mark.asyncio
async def test_chat_streams_safe_error_event_when_agent_fails(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(app.main, "agent", FailingAgent())

    with caplog.at_level(logging.ERROR, logger="app.main"):
        async with client.stream(
            "POST", "/api/chat", json={"message": "hello"}
        ) as response:
            body = "".join([chunk async for chunk in response.aiter_text()])

    assert response.status_code == 200
    assert "event: error" in body
    assert "data: Unable to generate a response." in body
    assert "connection refused" not in body
    assert any(record.message == "chat_stream_failed" for record in caplog.records)
    assert any(
        getattr(record, "event", None) == "chat_stream_failed"
        for record in caplog.records
    )
    assert "connection refused" in caplog.text


@pytest.mark.asyncio
async def test_chat_rejects_empty_message(client: AsyncClient) -> None:
    response = await client.post("/api/chat", json={"message": ""})

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_stream_response_passes_message_history_to_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_agent = FakeAgent()
    monkeypatch.setattr(app.main, "agent", fake_agent)
    history = [ModelRequest.user_text_prompt("previous")]

    events = [event async for event in app.main.stream_response("current", history)]

    assert events == [{"data": "Hello"}, {"data": " world"}]
    assert fake_agent.message == "current"
    assert fake_agent.message_history == history
