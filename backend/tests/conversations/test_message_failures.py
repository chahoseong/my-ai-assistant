from collections.abc import AsyncIterator, Sequence
import json
from typing import Any, cast
from uuid import UUID

from httpx import ASGITransport, AsyncClient
from pydantic_ai import (
    AgentRunResultEvent,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    UserPromptPart,
    UsageLimitExceeded,
)
from pydantic_ai.messages import PartStartEvent
from pydantic_ai.usage import RunUsage
import pytest


from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

import app.database.dependencies
import app.main
from app.database.models import Conversation, Message, ModelMessageRecord
from app.model_history import deserialize_model_messages
from app.observability.metrics import (
    LLM_STREAM_FAILURES_TOTAL,
    TOOL_CALLS_LIMIT_EXCEEDED_TOTAL,
)

pytestmark = pytest.mark.integration


class FailingEventStream:
    def __init__(self, error_message: str = "model unavailable") -> None:
        self.error_message = error_message

    async def __aenter__(self) -> AsyncIterator[object]:
        async def iterate() -> AsyncIterator[object]:
            raise RuntimeError(self.error_message)
            yield None

        return iterate()

    async def __aexit__(self, *args: object) -> None:
        return None


class FailingAgent:
    def __init__(self, error_message: str = "model unavailable") -> None:
        self.error_message = error_message

    def run_stream(
        self,
        message: str,
        *,
        message_history: Sequence[ModelMessage] | None = None,
    ) -> FailingEventStream:
        return FailingEventStream(self.error_message)


class SuccessfulRunResult:
    def __init__(self, message: str) -> None:
        self.message = message
        self.usage = RunUsage()

    def new_messages(self) -> list[ModelMessage]:
        return [
            ModelRequest(parts=[UserPromptPart(self.message)]),
            ModelResponse(parts=[TextPart("retry answer")]),
        ]


class SuccessfulEventStream:
    def __init__(self, result: SuccessfulRunResult) -> None:
        self.result = result

    async def __aenter__(self) -> AsyncIterator[object]:
        async def iterate() -> AsyncIterator[object]:
            yield PartStartEvent(index=0, part=TextPart("retry answer"))
            yield AgentRunResultEvent(result=cast(Any, self.result))

        return iterate()

    async def __aexit__(self, *args: object) -> None:
        return None


class SuccessfulAgent:
    def run_stream_events(
        self,
        message: str,
        *,
        message_history: Sequence[ModelMessage] | None = None,
        **_: object,
    ) -> SuccessfulEventStream:
        return SuccessfulEventStream(SuccessfulRunResult(message))


class UsageLimitedAgent:
    def __init__(self, message: str) -> None:
        self.message = message

    def run_stream_events(self, *_: object, **__: object) -> object:
        raise UsageLimitExceeded(self.message)


async def collect_messages(test_database, conversation_id: UUID) -> list[Message]:
    async with test_database.session_factory() as session:
        return list(
            await session.scalars(
                select(Message)
                .where(Message.conversation_id == conversation_id)
                .order_by(Message.created_at.asc(), Message.id.asc())
            )
        )


async def collect_model_messages(
    test_database, conversation_id: UUID
) -> list[ModelMessageRecord]:
    async with test_database.session_factory() as session:
        return list(
            await session.scalars(
                select(ModelMessageRecord)
                .where(ModelMessageRecord.conversation_id == conversation_id)
                .order_by(ModelMessageRecord.sequence.asc())
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
    monkeypatch.setattr(app.database.dependencies, "database", test_database)
    failure_secret = "stream-error-secret-6e2b73f1"
    monkeypatch.setattr(app.main, "agent", FailingAgent(failure_secret))
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
    captured_logs = capfd.readouterr().out
    assert failure_secret not in captured_logs
    records = [json.loads(line) for line in captured_logs.splitlines() if line]
    [failure_log] = [
        record for record in records if record["event"] == "message_stream_failed"
    ]
    [access_log] = [
        record for record in records if record["event"] == "http_request_complete"
    ]
    assert failure_log["request_id"] == access_log["request_id"]
    assert "exception" not in failure_log
    UUID(failure_log["request_id"])
    assert [
        message.role
        for message in await collect_messages(test_database, conversation_id)
    ] == ["user"]
    stored_model_messages = await collect_model_messages(test_database, conversation_id)
    assert [record.sequence for record in stored_model_messages] == [0]
    [stored_request] = deserialize_model_messages(
        [record.payload for record in stored_model_messages]
    )
    assert isinstance(stored_request, ModelRequest)
    [stored_prompt] = stored_request.parts
    assert isinstance(stored_prompt, UserPromptPart)
    assert stored_prompt.content == "will fail"


@pytest.mark.asyncio
async def test_usage_limit_sends_a_distinct_terminal_error_event(
    test_database, user_factory, session_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    transport = ASGITransport(app=app.main.app, raise_app_exceptions=False)
    conversation_id = UUID(int=503)
    monkeypatch.setattr(app.database.dependencies, "database", test_database)
    monkeypatch.setattr(
        app.main,
        "agent",
        UsageLimitedAgent(
            "The next tool call(s) would exceed the tool_calls_limit of 5 "
            "(tool_calls=6)."
        ),
    )
    before_limit_count = TOOL_CALLS_LIMIT_EXCEEDED_TOTAL._value.get()

    user, client = await create_authenticated_client(
        user_factory, session_factory, transport
    )
    await create_conversation(test_database, conversation_id, user.id)

    async with client:
        async with client.stream(
            "POST",
            f"/api/conversations/{conversation_id}/messages",
            json={"message": "use too many tools"},
        ) as response:
            body = "".join([chunk async for chunk in response.aiter_text()])

    assert response.status_code == 200
    assert "event: error" in body
    assert "data: The assistant reached its execution limit." in body
    assert "data: Unable to generate a response." not in body
    assert "event: done" not in body
    assert TOOL_CALLS_LIMIT_EXCEEDED_TOTAL._value.get() == before_limit_count + 1
    assert [
        message.role
        for message in await collect_messages(test_database, conversation_id)
    ] == ["user"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "limit_message",
    [
        "The next request would exceed the request_limit of 8 (requests=9).",
        "A future Pydantic AI version reported an unknown usage limit.",
    ],
)
async def test_non_tool_usage_limits_do_not_increment_the_tool_calls_limit_counter(
    limit_message: str,
    test_database,
    user_factory,
    session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = ASGITransport(app=app.main.app, raise_app_exceptions=False)
    conversation_id = UUID(int=504 if "request_limit" in limit_message else 505)
    monkeypatch.setattr(app.database.dependencies, "database", test_database)
    monkeypatch.setattr(app.main, "agent", UsageLimitedAgent(limit_message))
    before_limit_count = TOOL_CALLS_LIMIT_EXCEEDED_TOTAL._value.get()

    user, client = await create_authenticated_client(
        user_factory, session_factory, transport
    )
    await create_conversation(test_database, conversation_id, user.id)

    async with client:
        async with client.stream(
            "POST",
            f"/api/conversations/{conversation_id}/messages",
            json={"message": "reach a different limit"},
        ) as response:
            body = "".join([chunk async for chunk in response.aiter_text()])

    assert response.status_code == 200
    assert "data: The assistant reached its execution limit." in body
    assert TOOL_CALLS_LIMIT_EXCEEDED_TOTAL._value.get() == before_limit_count


@pytest.mark.asyncio
async def test_failed_stream_releases_lock_for_retry(
    test_database, user_factory, session_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    transport = ASGITransport(app=app.main.app, raise_app_exceptions=False)
    conversation_id = UUID(int=501)
    monkeypatch.setattr(app.database.dependencies, "database", test_database)
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


@pytest.mark.asyncio
async def test_final_persistence_failure_keeps_only_user_records(
    test_database, user_factory, session_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    transport = ASGITransport(app=app.main.app, raise_app_exceptions=False)
    conversation_id = UUID(int=502)
    monkeypatch.setattr(app.database.dependencies, "database", test_database)
    monkeypatch.setattr(app.main, "agent", SuccessfulAgent())

    user, client = await create_authenticated_client(
        user_factory, session_factory, transport
    )
    await create_conversation(test_database, conversation_id, user.id)

    original_commit = AsyncSession.commit
    commit_count = 0

    async def fail_final_commit(
        session: AsyncSession, *args: object, **kwargs: object
    ) -> None:
        nonlocal commit_count
        commit_count += 1
        if commit_count == 2:
            raise SQLAlchemyError("simulated final persistence failure")
        await original_commit(session, *args, **kwargs)

    monkeypatch.setattr(AsyncSession, "commit", fail_final_commit)

    async with client:
        async with client.stream(
            "POST",
            f"/api/conversations/{conversation_id}/messages",
            json={"message": "will not persist final"},
        ) as response:
            body = "".join([chunk async for chunk in response.aiter_text()])

    assert response.status_code == 200
    assert "event: error" in body
    assert "event: done" not in body
    assert commit_count == 2
    assert [
        message.role
        for message in await collect_messages(test_database, conversation_id)
    ] == ["user"]
    stored_model_messages = await collect_model_messages(test_database, conversation_id)
    assert [record.sequence for record in stored_model_messages] == [0]
    [stored_request] = deserialize_model_messages(
        [record.payload for record in stored_model_messages]
    )
    assert isinstance(stored_request, ModelRequest)
    [stored_prompt] = stored_request.parts
    assert isinstance(stored_prompt, UserPromptPart)
    assert stored_prompt.content == "will not persist final"
