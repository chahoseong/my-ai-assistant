import asyncio
from collections.abc import AsyncIterator, Sequence
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
)
from pydantic_ai.messages import PartStartEvent
from pydantic_ai.usage import RunUsage
import pytest


from starlette.types import Message, Scope

import app.database.dependencies
import app.main
import app.routers.chat as chat_router
from app.concurrency import release_conversation, try_acquire_conversation
from app.database.models import Conversation
from app.observability.metrics import (
    CONVERSATION_LOCK_CONFLICTS_TOTAL,
    LLM_STREAM_FAILURES_TOTAL,
)
from app.web.schemas import ConversationMessageCreate

pytestmark = pytest.mark.integration


class BlockingStreamResult:
    def __init__(self, owner: "BlockingAgent", message: str) -> None:
        self.owner = owner
        self.message = message
        self.usage = RunUsage()

    async def __aenter__(self) -> AsyncIterator[object]:
        async def iterate() -> AsyncIterator[object]:
            self.owner.started_count += 1
            if self.owner.started_count >= self.owner.expected_started:
                self.owner.started.set()
            await self.owner.release.wait()
            yield PartStartEvent(index=0, part=TextPart("answer"))
            yield AgentRunResultEvent(result=cast(Any, self))

        return iterate()

    async def __aexit__(self, *args: object) -> None:
        return None

    def new_messages(self) -> list[ModelMessage]:
        return [
            ModelRequest(parts=[UserPromptPart(self.message)]),
            ModelResponse(parts=[TextPart("answer")]),
        ]


class BlockingAgent:
    def __init__(self, expected_started: int = 1) -> None:
        self.expected_started = expected_started
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.started_count = 0

    def run_stream_events(
        self,
        message: str,
        *,
        message_history: Sequence[ModelMessage] | None = None,
        **_: object,
    ) -> BlockingStreamResult:
        return BlockingStreamResult(self, message)


class CancelledStreamResult:
    def __init__(self, started: asyncio.Event) -> None:
        self.started = started

    async def __aenter__(self) -> AsyncIterator[object]:
        async def iterate() -> AsyncIterator[object]:
            self.started.set()
            await asyncio.Event().wait()
            yield None

        return iterate()

    async def __aexit__(self, *args: object) -> None:
        return None


class CancelThenSuccessAgent:
    def __init__(self) -> None:
        self.first_started = asyncio.Event()
        self.second_agent = BlockingAgent()
        self.calls = 0

    def run_stream_events(
        self,
        message: str,
        *,
        message_history: Sequence[ModelMessage] | None = None,
        **_: object,
    ) -> CancelledStreamResult | BlockingStreamResult:
        self.calls += 1
        if self.calls == 1:
            return CancelledStreamResult(self.first_started)

        return BlockingStreamResult(self.second_agent, message)


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
async def test_same_conversation_is_rejected_without_waiting(
    test_database, user_factory, session_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    transport = ASGITransport(app=app.main.app)
    conversation_id = UUID(int=600)
    agent = BlockingAgent()
    monkeypatch.setattr(app.database.dependencies, "database", test_database)
    monkeypatch.setattr(app.main, "agent", agent)

    user, client = await create_authenticated_client(
        user_factory, session_factory, transport
    )
    await create_conversation(test_database, conversation_id, user.id)
    before_conflicts = CONVERSATION_LOCK_CONFLICTS_TOTAL._value.get()
    async with client:
        first = asyncio.create_task(
            client.post(
                f"/api/conversations/{conversation_id}/messages",
                json={"message": "first"},
            )
        )
        await asyncio.wait_for(agent.started.wait(), timeout=1)

        second_task = asyncio.create_task(
            client.post(
                f"/api/conversations/{conversation_id}/messages",
                json={"message": "second"},
            )
        )
        try:
            await asyncio.sleep(0.05)
            assert second_task.done()
            second = await second_task
            assert second.status_code == 409
            assert (
                CONVERSATION_LOCK_CONFLICTS_TOTAL._value.get() == before_conflicts + 1
            )
        finally:
            agent.release.set()
            first_response = await first
            if not second_task.done():
                second_task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await second_task

    assert first_response.status_code == 200


@pytest.mark.asyncio
async def test_different_conversations_can_stream_together(
    test_database, user_factory, session_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    transport = ASGITransport(app=app.main.app)
    first_id = UUID(int=601)
    second_id = UUID(int=602)
    agent = BlockingAgent(expected_started=2)
    monkeypatch.setattr(app.database.dependencies, "database", test_database)
    monkeypatch.setattr(app.main, "agent", agent)

    user, client = await create_authenticated_client(
        user_factory, session_factory, transport
    )
    await create_conversation(test_database, first_id, user.id)
    await create_conversation(test_database, second_id, user.id)
    async with client:
        first = asyncio.create_task(
            client.post(
                f"/api/conversations/{first_id}/messages",
                json={"message": "first"},
            )
        )
        second = asyncio.create_task(
            client.post(
                f"/api/conversations/{second_id}/messages",
                json={"message": "second"},
            )
        )

        await asyncio.wait_for(agent.started.wait(), timeout=1)
        agent.release.set()
        first_response, second_response = await asyncio.gather(first, second)

    assert first_response.status_code == 200
    assert second_response.status_code == 200


@pytest.mark.asyncio
async def test_cancelled_stream_releases_lock_for_next_request(
    test_database, user_factory, session_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    transport = ASGITransport(app=app.main.app)
    conversation_id = UUID(int=603)
    agent = CancelThenSuccessAgent()
    before_failure_count = LLM_STREAM_FAILURES_TOTAL._value.get()
    monkeypatch.setattr(app.database.dependencies, "database", test_database)
    monkeypatch.setattr(app.main, "agent", agent)

    user, client = await create_authenticated_client(
        user_factory, session_factory, transport
    )
    await create_conversation(test_database, conversation_id, user.id)
    async with client:
        first = asyncio.create_task(
            client.post(
                f"/api/conversations/{conversation_id}/messages",
                json={"message": "cancel me"},
            )
        )
        await asyncio.wait_for(agent.first_started.wait(), timeout=1)
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first

        second_task = asyncio.create_task(
            client.post(
                f"/api/conversations/{conversation_id}/messages",
                json={"message": "after cancel"},
            )
        )
        await asyncio.wait_for(agent.second_agent.started.wait(), timeout=1)

        third_task = asyncio.create_task(
            client.post(
                f"/api/conversations/{conversation_id}/messages",
                json={"message": "while retry runs"},
            )
        )
        try:
            await asyncio.sleep(0.05)
            assert third_task.done()
            third = await third_task
            assert third.status_code == 409
        finally:
            agent.second_agent.release.set()
            second = await second_task
            if not third_task.done():
                third_task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await third_task

    assert second.status_code == 200
    assert LLM_STREAM_FAILURES_TOTAL._value.get() == before_failure_count


@pytest.mark.asyncio
async def test_disconnect_before_stream_iterator_starts_releases_lock(
    test_database, user_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    conversation_id = UUID(int=604)
    owner = await user_factory()
    await create_conversation(test_database, conversation_id, owner.id)

    agent_called = False

    def fail_if_stream_starts():
        nonlocal agent_called
        agent_called = True
        raise AssertionError("the stream iterator must not start")

    monkeypatch.setattr(chat_router, "get_stream_agent", fail_if_stream_starts)
    response = await chat_router.send_message(
        conversation_id,
        ConversationMessageCreate(message="disconnect before stream"),
        owner,
        None,
        test_database,
    )

    response_started = asyncio.Event()

    async def send(message: Message) -> None:
        if message["type"] == "http.response.start":
            response_started.set()
            await asyncio.Event().wait()

    async def receive() -> Message:
        await response_started.wait()
        return {"type": "http.disconnect"}

    scope: Scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "method": "POST",
        "path": "/api/conversations/604/messages",
        "raw_path": b"/api/conversations/604/messages",
        "query_string": b"",
        "headers": [],
        "scheme": "http",
        "client": ("test", 123),
        "server": ("test", 80),
    }

    await response(scope, receive, send)

    assert agent_called is False
    acquired = await try_acquire_conversation(conversation_id)
    try:
        assert acquired is True
    finally:
        if acquired:
            await release_conversation(conversation_id)
