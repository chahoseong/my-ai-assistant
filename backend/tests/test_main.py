from collections.abc import AsyncIterator

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
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
        self.result = FakeStreamResult()

    def run_stream(self, message: str) -> FakeStreamResult:
        self.message = message
        return self.result


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
async def test_chat_rejects_empty_message(client: AsyncClient) -> None:
    response = await client.post("/api/chat", json={"message": ""})

    assert response.status_code == 422
