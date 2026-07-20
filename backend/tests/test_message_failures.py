from collections.abc import AsyncIterator, Sequence
import json
from uuid import UUID

from httpx import ASGITransport, AsyncClient
from pydantic_ai import ModelMessage
import pytest
from sqlalchemy import select

import app.dependencies
import app.main
from app.models import Conversation, Message
from app.observability import LLM_STREAM_FAILURES_TOTAL


class FailingStreamResult:
    async def __aenter__(self) -> "FailingStreamResult":
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def stream_text(self, *, delta: bool) -> AsyncIterator[str]:
        assert delta is True
        raise RuntimeError("model unavailable")
        yield "unreachable"


class FailingAgent:
    def run_stream(
        self,
        message: str,
        *,
        message_history: Sequence[ModelMessage] | None = None,
    ) -> FailingStreamResult:
        return FailingStreamResult()


class SuccessfulStreamResult:
    async def __aenter__(self) -> "SuccessfulStreamResult":
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def stream_text(self, *, delta: bool) -> AsyncIterator[str]:
        assert delta is True
        yield "retry answer"


class SuccessfulAgent:
    def run_stream(
        self,
        message: str,
        *,
        message_history: Sequence[ModelMessage] | None = None,
    ) -> SuccessfulStreamResult:
        return SuccessfulStreamResult()


async def collect_messages(test_database, conversation_id: UUID) -> list[Message]:
    async with test_database.session_factory() as session:
        return list(
            await session.scalars(
                select(Message)
                .where(Message.conversation_id == conversation_id)
                .order_by(Message.created_at.asc(), Message.id.asc())
            )
        )


async def create_conversation(
    test_database, conversation_id: UUID, user_id: UUID
) -> None:
    async with test_database.session_factory() as session:
        session.add(Conversation(id=conversation_id, user_id=user_id))
        await session.commit()


async def create_authenticated_client(user_factory, session_factory, transport):
    user = await user_factory()
    _, token = await session_factory(user=user)
    client = AsyncClient(transport=transport, base_url="http://test")
    client.cookies.set("assistant_session", token)
    return user, client


@pytest.mark.asyncio
async def test_llm_failure_keeps_user_only_and_sends_error_event(
    test_database, user_factory, session_factory, monkeypatch: pytest.MonkeyPatch, capfd
) -> None:
    transport = ASGITransport(app=app.main.app, raise_app_exceptions=False)
    conversation_id = UUID(int=500)
    monkeypatch.setattr(app.dependencies, "database", test_database)
    monkeypatch.setattr(app.main, "agent", FailingAgent())
    before_failure_count = LLM_STREAM_FAILURES_TOTAL._value.get()

    user, client = await create_authenticated_client(
        user_factory, session_factory, transport
    )
    await create_conversation(test_database, conversation_id, user.id)
    capfd.readouterr()
    async with client:
        async with client.stream(
            "POST",
            f"/api/conversations/{conversation_id}/messages",
            json={"message": "will fail"},
        ) as response:
            body = "".join([chunk async for chunk in response.aiter_text()])

    assert response.status_code == 200
    assert "event: error" in body
    assert "data: Unable to generate a response." in body
    assert "event: done" not in body
    assert LLM_STREAM_FAILURES_TOTAL._value.get() == before_failure_count + 1
    records = [json.loads(line) for line in capfd.readouterr().out.splitlines() if line]
    [failure_log] = [
        record for record in records if record["event"] == "message_stream_failed"
    ]
    [access_log] = [
        record for record in records if record["event"] == "http_request_complete"
    ]
    assert failure_log["request_id"] == access_log["request_id"]
    UUID(failure_log["request_id"])
    assert [
        message.role
        for message in await collect_messages(test_database, conversation_id)
    ] == ["user"]


@pytest.mark.asyncio
async def test_failed_stream_releases_lock_for_retry(
    test_database, user_factory, session_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    transport = ASGITransport(app=app.main.app, raise_app_exceptions=False)
    conversation_id = UUID(int=501)
    monkeypatch.setattr(app.dependencies, "database", test_database)
    monkeypatch.setattr(app.main, "agent", FailingAgent())

    user, client = await create_authenticated_client(
        user_factory, session_factory, transport
    )
    await create_conversation(test_database, conversation_id, user.id)
    async with client:
        async with client.stream(
            "POST",
            f"/api/conversations/{conversation_id}/messages",
            json={"message": "first attempt"},
        ) as response:
            _ = "".join([chunk async for chunk in response.aiter_text()])

        monkeypatch.setattr(app.main, "agent", SuccessfulAgent())
        async with client.stream(
            "POST",
            f"/api/conversations/{conversation_id}/messages",
            json={"message": "retry"},
        ) as retry_response:
            retry_body = "".join([chunk async for chunk in retry_response.aiter_text()])

    assert retry_response.status_code == 200
    assert "data: retry answer" in retry_body
    assert "event: done" in retry_body
