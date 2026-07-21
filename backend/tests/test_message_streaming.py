from collections.abc import AsyncIterator, Sequence
from datetime import UTC, datetime
from uuid import UUID

from httpx import ASGITransport, AsyncClient
from pydantic_ai import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    UserPromptPart,
)
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import app.database.dependencies
import app.main
from app.concurrency import release_conversation, try_acquire_conversation
from app.database.models import Conversation, Message, User
from app.routers import chat as chat_router
from app.web.schemas import ConversationMessageCreate
from app.observability.metrics import (
    LLM_FIRST_TOKEN_SECONDS,
    LLM_STREAM_DELTAS_TOTAL,
    LLM_STREAM_DURATION_SECONDS,
)


def metric_sample_value(metric, sample_name: str) -> float:
    for family in metric.collect():
        for sample in family.samples:
            if sample.name == sample_name:
                return sample.value

    raise AssertionError(f"Missing {sample_name} sample")


class FakeStreamResult:
    def __init__(self, deltas: Sequence[str]) -> None:
        self.deltas = deltas

    async def __aenter__(self) -> "FakeStreamResult":
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def stream_text(self, *, delta: bool) -> AsyncIterator[str]:
        assert delta is True
        for value in self.deltas:
            yield value


class RecordingAgent:
    def __init__(self, deltas: Sequence[str]) -> None:
        self.deltas = deltas
        self.message: str | None = None
        self.message_history: Sequence[ModelMessage] | None = None

    def run_stream(
        self,
        message: str,
        *,
        message_history: Sequence[ModelMessage] | None = None,
    ) -> FakeStreamResult:
        self.message = message
        self.message_history = message_history
        return FakeStreamResult(self.deltas)


@pytest.fixture
async def authenticated_user(test_database, user_factory, session_factory, monkeypatch):
    monkeypatch.setattr(app.database.dependencies, "database", test_database)
    user = await user_factory()
    _, token = await session_factory(user=user)
    return user, token


@pytest.fixture
async def client(authenticated_user) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app.main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        client.cookies.set("assistant_session", authenticated_user[1])
        yield client


@pytest.mark.asyncio
async def test_send_message_streams_persists_complete_turn_and_records_metrics(
    client: AsyncClient,
    authenticated_user,
    test_database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(app.database.dependencies, "database", test_database)
    fake_agent = RecordingAgent(["Hello", " world"])
    monkeypatch.setattr(app.main, "agent", fake_agent)
    conversation_id = UUID(int=400)
    before_ttft_count = metric_sample_value(
        LLM_FIRST_TOKEN_SECONDS, "llm_first_token_seconds_count"
    )
    before_duration_count = metric_sample_value(
        LLM_STREAM_DURATION_SECONDS, "llm_stream_duration_seconds_count"
    )
    before_delta_count = LLM_STREAM_DELTAS_TOTAL._value.get()

    async with test_database.session_factory() as session:
        session.add(
            Conversation(
                id=conversation_id,
                user_id=authenticated_user[0].id,
                messages=[
                    Message(
                        id=UUID(int=401),
                        role="user",
                        content="previous question",
                        created_at=datetime(2026, 1, 1, tzinfo=UTC),
                    ),
                    Message(
                        id=UUID(int=402),
                        role="assistant",
                        content="previous answer",
                        created_at=datetime(2026, 1, 2, tzinfo=UTC),
                    ),
                ],
            )
        )
        await session.commit()

    async with client.stream(
        "POST",
        f"/api/conversations/{conversation_id}/messages",
        json={"message": "current question"},
    ) as response:
        body = "".join([chunk async for chunk in response.aiter_text()])

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "data: Hello" in body
    assert "data:  world" in body
    assert "event: done" in body
    assert body.index("data: Hello") < body.index("event: done")
    assert body.index("data:  world") < body.index("event: done")

    assert fake_agent.message == "current question"
    assert fake_agent.message_history is not None
    assert len(fake_agent.message_history) == 2
    assert isinstance(fake_agent.message_history[0], ModelRequest)
    assert isinstance(fake_agent.message_history[1], ModelResponse)
    first_part = fake_agent.message_history[0].parts[0]
    second_part = fake_agent.message_history[1].parts[0]
    assert isinstance(first_part, UserPromptPart)
    assert isinstance(second_part, TextPart)
    assert first_part.content == "previous question"
    assert second_part.content == "previous answer"

    async with test_database.session_factory() as session:
        stored_messages = list(
            await session.scalars(
                select(Message)
                .where(Message.conversation_id == conversation_id)
                .order_by(Message.created_at.asc(), Message.id.asc())
            )
        )

    assert [message.role for message in stored_messages] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]
    assert [message.content for message in stored_messages[-2:]] == [
        "current question",
        "Hello world",
    ]
    assert f"data: {stored_messages[-1].id}" in body
    assert (
        metric_sample_value(LLM_FIRST_TOKEN_SECONDS, "llm_first_token_seconds_count")
        == before_ttft_count + 1
    )
    assert (
        metric_sample_value(
            LLM_STREAM_DURATION_SECONDS, "llm_stream_duration_seconds_count"
        )
        == before_duration_count + 1
    )
    assert LLM_STREAM_DELTAS_TOTAL._value.get() == before_delta_count + 2


@pytest.mark.asyncio
async def test_refresh_failure_after_commit_does_not_turn_success_into_error(
    client: AsyncClient,
    authenticated_user,
    test_database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(app.database.dependencies, "database", test_database)
    monkeypatch.setattr(app.main, "agent", RecordingAgent(["answer"]))
    conversation_id = UUID(int=403)

    async with test_database.session_factory() as session:
        session.add(Conversation(id=conversation_id, user_id=authenticated_user[0].id))
        await session.commit()

    async def fail_refresh(
        _session: AsyncSession, _instance: object, *args: object, **kwargs: object
    ) -> None:
        raise RuntimeError("simulated refresh failure")

    monkeypatch.setattr(AsyncSession, "refresh", fail_refresh)

    async with client.stream(
        "POST",
        f"/api/conversations/{conversation_id}/messages",
        json={"message": "question"},
    ) as response:
        body = "".join([chunk async for chunk in response.aiter_text()])

    assert response.status_code == 200
    assert "event: done" in body
    assert "event: error" not in body

    async with test_database.session_factory() as session:
        stored_messages = list(
            await session.scalars(
                select(Message).where(Message.conversation_id == conversation_id)
            )
        )

    assert [(message.role, message.content) for message in stored_messages] == [
        ("user", "question"),
        ("assistant", "answer"),
    ]


@pytest.mark.asyncio
async def test_background_cleanup_does_not_release_new_owner(
    test_database, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app.database.dependencies, "database", test_database)
    monkeypatch.setattr(app.main, "agent", RecordingAgent(["answer"]))
    conversation_id = UUID(int=404)
    owner_id = UUID(int=405)

    async with test_database.session_factory() as session:
        session.add(User(id=owner_id, username="owner", password_hash="test"))
        session.add(Conversation(id=conversation_id, user_id=owner_id))
        await session.commit()

    # Direct-call coverage is handled by HTTP tests; this path only exercises
    # lease cleanup and uses an explicit owner prepared below.
    response = await chat_router.send_message(
        conversation_id,
        ConversationMessageCreate(message="question"),
        User(id=owner_id, username="owner", password_hash="test"),
        None,
        test_database,
    )
    _ = [event async for event in response.body_iterator]

    acquired_by_next_request = await try_acquire_conversation(conversation_id)
    assert acquired_by_next_request is True
    try:
        assert response.background is not None
        await response.background()

        acquired_by_third_request = await try_acquire_conversation(conversation_id)
        assert acquired_by_third_request is False
    finally:
        await release_conversation(conversation_id)


@pytest.mark.asyncio
async def test_send_message_rejects_missing_conversation_before_sse(
    client: AsyncClient, test_database, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app.database.dependencies, "database", test_database)
    fake_agent = RecordingAgent(["should not run"])
    monkeypatch.setattr(app.main, "agent", fake_agent)

    response = await client.post(
        f"/api/conversations/{UUID(int=499)}/messages",
        json={"message": "current question"},
    )

    assert response.status_code == 404
    assert fake_agent.message is None


@pytest.mark.asyncio
async def test_send_message_requires_authentication_before_sse() -> None:
    transport = ASGITransport(app=app.main.app)
    async with AsyncClient(
        transport=transport, base_url="http://test"
    ) as anonymous_client:
        response = await anonymous_client.post(
            f"/api/conversations/{UUID(int=498)}/messages",
            json={"message": "current question"},
        )

    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/json")


@pytest.mark.asyncio
async def test_send_message_rejects_non_json_content_type(
    client: AsyncClient, test_database, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app.database.dependencies, "database", test_database)

    response = await client.post(
        f"/api/conversations/{UUID(int=496)}/messages",
        content='{"message":"plain"}',
        headers={"content-type": "text/plain"},
    )

    assert response.status_code == 415


@pytest.mark.asyncio
async def test_non_owner_gets_not_found_before_conversation_lock(
    client: AsyncClient, test_database, user_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app.database.dependencies, "database", test_database)
    owner = await user_factory(username="owner")
    conversation_id = UUID(int=497)
    async with test_database.session_factory() as session:
        session.add(Conversation(id=conversation_id, user_id=owner.id))
        await session.commit()

    assert await try_acquire_conversation(conversation_id) is True
    try:
        response = await client.post(
            f"/api/conversations/{conversation_id}/messages",
            json={"message": "current question"},
        )
    finally:
        await release_conversation(conversation_id)

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")
