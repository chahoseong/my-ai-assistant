from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import ClassVar
from uuid import UUID

from httpx import ASGITransport, AsyncClient
import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

import app.database.dependencies
import app.main
from app.database.models import Conversation
from app.database.dependencies import get_session
from app.auth.dependencies import get_current_user
from app.database.models import User
from app.web.dependencies import get_current_user_for_unsafe_request


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
async def test_create_conversation_persists_and_returns_created_resource(
    client: AsyncClient, test_database, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app.database.dependencies, "database", test_database)

    response = await client.post(
        "/api/conversations", json={"title": "Learning conversation"}
    )

    assert response.status_code == 201
    payload = response.json()
    conversation_id = UUID(payload["id"])
    assert payload["title"] == "Learning conversation"
    assert payload["created_at"]

    async with test_database.session_factory() as session:
        conversation = await session.get(Conversation, conversation_id)

    assert conversation is not None
    assert conversation.title == "Learning conversation"


@pytest.mark.asyncio
async def test_create_conversation_requires_authentication() -> None:
    transport = ASGITransport(app=app.main.app)
    async with AsyncClient(
        transport=transport, base_url="http://test"
    ) as anonymous_client:
        response = await anonymous_client.post("/api/conversations", json={})

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_conversations_requires_authentication() -> None:
    transport = ASGITransport(app=app.main.app)
    async with AsyncClient(
        transport=transport, base_url="http://test"
    ) as anonymous_client:
        response = await anonymous_client.get("/api/conversations")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_conversations_returns_only_current_users_conversations(
    client: AsyncClient,
    authenticated_user,
    conversation_factory,
    user_factory,
) -> None:
    current_user, _ = authenticated_user
    current_users_conversation = await conversation_factory(
        user=current_user, title="Current user's conversation"
    )
    other_user = await user_factory()
    await conversation_factory(user=other_user, title="Other user's conversation")

    response = await client.get("/api/conversations")

    assert response.status_code == 200
    assert [conversation["id"] for conversation in response.json()] == [
        str(current_users_conversation.id)
    ]


@pytest.mark.asyncio
async def test_list_conversations_orders_by_created_at_then_id_descending(
    client: AsyncClient,
    authenticated_user,
    test_database,
) -> None:
    current_user, _ = authenticated_user
    oldest = Conversation(
        id=UUID("00000000-0000-0000-0000-000000000099"),
        user_id=current_user.id,
        title="Oldest",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    tied_lower_id = Conversation(
        id=UUID("00000000-0000-0000-0000-000000000001"),
        user_id=current_user.id,
        title="Tied lower ID",
        created_at=datetime(2026, 1, 2, tzinfo=UTC),
    )
    tied_higher_id = Conversation(
        id=UUID("00000000-0000-0000-0000-000000000002"),
        user_id=current_user.id,
        title="Tied higher ID",
        created_at=datetime(2026, 1, 2, tzinfo=UTC),
    )
    newest = Conversation(
        id=UUID("00000000-0000-0000-0000-000000000003"),
        user_id=current_user.id,
        title="Newest",
        created_at=datetime(2026, 1, 3, tzinfo=UTC),
    )

    async with test_database.session_factory() as session:
        session.add_all([oldest, tied_lower_id, tied_higher_id, newest])
        await session.commit()

    response = await client.get("/api/conversations")

    assert response.status_code == 200
    assert [conversation["id"] for conversation in response.json()] == [
        str(newest.id),
        str(tied_higher_id.id),
        str(tied_lower_id.id),
        str(oldest.id),
    ]


class FailingListSession:
    async def scalars(self, _statement: object) -> None:
        raise SQLAlchemyError("database details must stay private")


async def failing_list_session() -> AsyncIterator[FailingListSession]:
    yield FailingListSession()


@pytest.mark.asyncio
async def test_list_conversations_returns_safe_error_when_query_fails() -> None:
    app.main.app.dependency_overrides[get_session] = failing_list_session
    app.main.app.dependency_overrides[get_current_user] = lambda: User(
        username="test_user", password_hash="$argon2id$test"
    )
    transport = ASGITransport(app=app.main.app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/conversations")
    finally:
        app.main.app.dependency_overrides.pop(get_session, None)
        app.main.app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 500
    assert response.json() == {"detail": "Unable to list conversations."}
    assert "database details" not in response.text


@pytest.mark.asyncio
async def test_create_conversation_rejects_non_json_content_type(
    client: AsyncClient, test_database, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app.database.dependencies, "database", test_database)

    response = await client.post(
        "/api/conversations",
        content='{"title":"plain"}',
        headers={"content-type": "text/plain"},
    )

    assert response.status_code == 415


@pytest.mark.asyncio
async def test_create_conversation_allows_missing_title(
    client: AsyncClient, test_database, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app.database.dependencies, "database", test_database)

    response = await client.post("/api/conversations", json={})

    assert response.status_code == 201
    assert response.json()["title"] is None


@pytest.mark.asyncio
async def test_create_conversation_accepts_title_at_maximum_length(
    client: AsyncClient, test_database, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app.database.dependencies, "database", test_database)
    title = "t" * 200

    response = await client.post("/api/conversations", json={"title": title})

    assert response.status_code == 201
    assert response.json()["title"] == title


@pytest.mark.asyncio
async def test_create_conversation_rejects_title_over_maximum_length(
    client: AsyncClient, test_database, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app.database.dependencies, "database", test_database)

    async with test_database.session_factory() as session:
        before_count = await session.scalar(
            select(func.count()).select_from(Conversation)
        )

    response = await client.post("/api/conversations", json={"title": "t" * 201})

    assert response.status_code == 422

    async with test_database.session_factory() as session:
        after_count = await session.scalar(
            select(func.count()).select_from(Conversation)
        )

    assert after_count == before_count


class FailingSession:
    last_instance: ClassVar["FailingSession | None"] = None
    rolled_back = False

    def __init__(self) -> None:
        FailingSession.last_instance = self

    def add(self, _object: object) -> None:
        return None

    async def commit(self) -> None:
        raise SQLAlchemyError("database details must stay private")

    async def refresh(self, _object: object) -> None:
        raise AssertionError("refresh must not run after a failed commit")

    async def rollback(self) -> None:
        self.rolled_back = True


async def failing_session() -> AsyncIterator[FailingSession]:
    session = FailingSession()
    yield session


@pytest.mark.asyncio
async def test_create_conversation_returns_safe_error_when_commit_fails(
    client: AsyncClient,
) -> None:
    app.main.app.dependency_overrides[get_session] = failing_session
    app.main.app.dependency_overrides[get_current_user_for_unsafe_request] = lambda: (
        User(username="test_user", password_hash="$argon2id$test")
    )
    try:
        response = await client.post("/api/conversations", json={"title": "will fail"})
    finally:
        app.main.app.dependency_overrides.pop(get_session, None)
        app.main.app.dependency_overrides.pop(get_current_user_for_unsafe_request, None)

    assert response.status_code == 500
    assert response.json() == {"detail": "Unable to create conversation."}
    assert "database details" not in response.text
    assert FailingSession.last_instance is not None
    assert FailingSession.last_instance.rolled_back is True
