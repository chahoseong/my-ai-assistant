from pathlib import Path

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
import pytest

import app.main


def test_application_module_exists() -> None:
    assert (Path(__file__).parents[1] / "app" / "main.py").is_file()


def test_application_exposes_fastapi_app() -> None:
    assert isinstance(getattr(app.main, "app", None), FastAPI)


@pytest.mark.asyncio
async def test_chat_streams_llm_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_stream_response(message: str):
        assert message == "안녕"
        for token in ("반", "가워요"):
            yield {"data": token}

    monkeypatch.setattr(
        app.main, "stream_response", fake_stream_response, raising=False
    )
    transport = ASGITransport(app=app.main.app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        async with client.stream(
            "POST", "/api/chat", json={"message": "안녕"}
        ) as response:
            body = "".join([chunk async for chunk in response.aiter_text()])

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "data: 반" in body
    assert "data: 가워요" in body


@pytest.mark.asyncio
async def test_chat_rejects_empty_message() -> None:
    transport = ASGITransport(app=app.main.app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/chat", json={"message": ""})

    assert response.status_code == 422
