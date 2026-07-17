from collections.abc import AsyncIterator
from typing import ClassVar
from uuid import UUID

from httpx import ASGITransport, AsyncClient
import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

import app.dependencies
import app.main
from app.models import Conversation
from app.dependencies import get_session


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app.main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
async def test_create_conversation_persists_and_returns_created_resource(
    client: AsyncClient, test_database, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app.dependencies, "database", test_database)

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
async def test_create_conversation_allows_missing_title(
    client: AsyncClient, test_database, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app.dependencies, "database", test_database)

    response = await client.post("/api/conversations", json={})

    assert response.status_code == 201
    assert response.json()["title"] is None


@pytest.mark.asyncio
async def test_create_conversation_accepts_title_at_maximum_length(
    client: AsyncClient, test_database, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app.dependencies, "database", test_database)
    title = "t" * 200

    response = await client.post("/api/conversations", json={"title": title})

    assert response.status_code == 201
    assert response.json()["title"] == title


@pytest.mark.asyncio
async def test_create_conversation_rejects_title_over_maximum_length(
    client: AsyncClient, test_database, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app.dependencies, "database", test_database)

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
    try:
        response = await client.post("/api/conversations", json={"title": "will fail"})
    finally:
        app.main.app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 500
    assert response.json() == {"detail": "Unable to create conversation."}
    assert "database details" not in response.text
    assert FailingSession.last_instance is not None
    assert FailingSession.last_instance.rolled_back is True
