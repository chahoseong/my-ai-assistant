from collections.abc import AsyncIterator
from typing import ClassVar
from uuid import UUID, uuid4

from httpx import ASGITransport, AsyncClient
import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

import app.database.dependencies
import app.main
from app.concurrency import release_conversation, try_acquire_conversation
from app.database.dependencies import get_session
from app.database.models import Conversation, Message, ModelMessageRecord, User
from app.web.dependencies import get_current_user_for_unsafe_request

pytestmark = pytest.mark.integration


@pytest.fixture
async def authenticated_client(
    test_database,
    user_factory,
    session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[tuple[User, AsyncClient]]:
    monkeypatch.setattr(app.database.dependencies, "database", test_database)
    user = await user_factory()
    _, token = await session_factory(user=user)
    transport = ASGITransport(app=app.main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        client.cookies.set("assistant_session", token)
        yield user, client


async def count_rows(session, model, conversation_id: UUID) -> int:
    value = await session.scalar(
        select(func.count())
        .select_from(model)
        .where(model.conversation_id == conversation_id)
    )
    assert value is not None
    return value


@pytest.mark.asyncio
async def test_delete_conversation_cascades_and_releases_lock(
    authenticated_client,
    conversation_factory,
    test_database,
) -> None:
    owner, client = authenticated_client
    conversation = await conversation_factory(user=owner, title="Delete me")
    async with test_database.session_factory() as session:
        session.add_all(
            [
                Message(
                    conversation_id=conversation.id,
                    role="user",
                    content="hello",
                ),
                ModelMessageRecord(
                    conversation_id=conversation.id,
                    sequence=0,
                    payload={"kind": "test-history"},
                ),
            ]
        )
        await session.commit()

    response = await client.delete(f"/api/conversations/{conversation.id}")

    assert response.status_code == 204
    assert response.content == b""
    async with test_database.session_factory() as session:
        assert await session.get(Conversation, conversation.id) is None
        assert await count_rows(session, Message, conversation.id) == 0
        assert await count_rows(session, ModelMessageRecord, conversation.id) == 0

    acquired = await try_acquire_conversation(conversation.id)
    try:
        assert acquired is True
    finally:
        if acquired:
            await release_conversation(conversation.id)


@pytest.mark.asyncio
async def test_delete_missing_conversation_returns_not_found(
    authenticated_client,
) -> None:
    _, client = authenticated_client

    response = await client.delete(f"/api/conversations/{uuid4()}")

    assert response.status_code == 404
    assert response.json() == {"detail": "Conversation not found."}


@pytest.mark.asyncio
async def test_delete_other_users_conversation_returns_not_found(
    authenticated_client,
    user_factory,
    conversation_factory,
) -> None:
    _, client = authenticated_client
    other_user = await user_factory()
    conversation = await conversation_factory(user=other_user)

    response = await client.delete(f"/api/conversations/{conversation.id}")

    assert response.status_code == 404
    assert response.json() == {"detail": "Conversation not found."}


@pytest.mark.asyncio
async def test_ownership_check_precedes_lock_state(
    authenticated_client,
    user_factory,
    conversation_factory,
) -> None:
    _, client = authenticated_client
    other_user = await user_factory()
    conversation = await conversation_factory(user=other_user)
    assert await try_acquire_conversation(conversation.id) is True
    try:
        response = await client.delete(f"/api/conversations/{conversation.id}")
    finally:
        await release_conversation(conversation.id)

    assert response.status_code == 404
    assert response.json() == {"detail": "Conversation not found."}


@pytest.mark.asyncio
async def test_delete_locked_conversation_returns_conflict_then_succeeds(
    authenticated_client,
    conversation_factory,
) -> None:
    owner, client = authenticated_client
    conversation = await conversation_factory(user=owner)
    assert await try_acquire_conversation(conversation.id) is True
    try:
        blocked = await client.delete(f"/api/conversations/{conversation.id}")
    finally:
        await release_conversation(conversation.id)

    assert blocked.status_code == 409
    assert blocked.json() == {"detail": "응답 생성 중에는 삭제할 수 없습니다"}

    deleted = await client.delete(f"/api/conversations/{conversation.id}")

    assert deleted.status_code == 204


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "headers",
    [{}, {"origin": "http://localhost:5173"}],
    ids=["missing-origin", "allowed-origin"],
)
async def test_delete_allows_missing_and_exact_allowed_origin(
    authenticated_client,
    conversation_factory,
    headers: dict[str, str],
) -> None:
    owner, client = authenticated_client
    conversation = await conversation_factory(user=owner)

    response = await client.delete(
        f"/api/conversations/{conversation.id}",
        headers=headers,
    )

    assert response.status_code == 204


@pytest.mark.asyncio
async def test_delete_rejects_disallowed_origin_without_deleting(
    authenticated_client,
    conversation_factory,
    test_database,
) -> None:
    owner, client = authenticated_client
    conversation = await conversation_factory(user=owner)

    response = await client.delete(
        f"/api/conversations/{conversation.id}",
        headers={"origin": "https://evil.example"},
    )

    assert response.status_code == 403
    async with test_database.session_factory() as session:
        assert await session.get(Conversation, conversation.id) is not None


class FailingDeleteSession:
    last_instance: ClassVar["FailingDeleteSession | None"] = None
    owner_id = UUID(int=820)
    conversation_id = UUID(int=821)

    def __init__(self) -> None:
        self.rolled_back = False
        self.deleted = False
        FailingDeleteSession.last_instance = self

    async def scalar(self, _statement: object) -> Conversation:
        return Conversation(
            id=self.conversation_id,
            user_id=self.owner_id,
            title="commit fails",
        )

    async def delete(self, _conversation: Conversation) -> None:
        self.deleted = True

    async def commit(self) -> None:
        raise SQLAlchemyError("database details must stay private")

    async def rollback(self) -> None:
        self.rolled_back = True


async def failing_delete_session() -> AsyncIterator[FailingDeleteSession]:
    yield FailingDeleteSession()


@pytest.mark.asyncio
async def test_delete_failure_rolls_back_returns_safe_error_and_releases_lock() -> None:
    app.main.app.dependency_overrides[get_session] = failing_delete_session
    app.main.app.dependency_overrides[get_current_user_for_unsafe_request] = lambda: (
        User(
            id=FailingDeleteSession.owner_id,
            username="delete_owner",
            password_hash="$argon2id$test",
        )
    )
    transport = ASGITransport(app=app.main.app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.delete(
                f"/api/conversations/{FailingDeleteSession.conversation_id}"
            )
    finally:
        app.main.app.dependency_overrides.pop(get_session, None)
        app.main.app.dependency_overrides.pop(
            get_current_user_for_unsafe_request,
            None,
        )

    assert response.status_code == 500
    assert response.json() == {"detail": "Unable to delete conversation."}
    assert "database details" not in response.text
    assert FailingDeleteSession.last_instance is not None
    assert FailingDeleteSession.last_instance.deleted is True
    assert FailingDeleteSession.last_instance.rolled_back is True

    acquired = await try_acquire_conversation(FailingDeleteSession.conversation_id)
    try:
        assert acquired is True
    finally:
        if acquired:
            await release_conversation(FailingDeleteSession.conversation_id)
