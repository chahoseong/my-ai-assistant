from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import UUID

from httpx import ASGITransport, AsyncClient
import pytest

import app.dependencies
import app.main
from app.models import Conversation, Message


@pytest.fixture
async def authenticated_user(test_database, user_factory, session_factory, monkeypatch):
    monkeypatch.setattr(app.dependencies, "database", test_database)
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
async def test_list_messages_returns_deterministic_created_at_and_id_order(
    client: AsyncClient,
    authenticated_user,
    test_database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(app.dependencies, "database", test_database)
    conversation_id = UUID(int=100)
    same_time = datetime(2026, 1, 1, tzinfo=UTC)

    async with test_database.session_factory() as session:
        session.add(
            Conversation(
                id=conversation_id,
                user_id=authenticated_user[0].id,
                messages=[
                    Message(
                        id=UUID(int=2),
                        role="assistant",
                        content="second",
                        created_at=same_time,
                    ),
                    Message(
                        id=UUID(int=1),
                        role="user",
                        content="first",
                        created_at=same_time,
                    ),
                    Message(
                        id=UUID(int=3),
                        role="assistant",
                        content="last",
                        created_at=datetime(2026, 1, 2, tzinfo=UTC),
                    ),
                ],
            )
        )
        await session.commit()

    response = await client.get(f"/api/conversations/{conversation_id}/messages")

    assert response.status_code == 200
    assert [message["content"] for message in response.json()] == [
        "first",
        "second",
        "last",
    ]


@pytest.mark.asyncio
async def test_list_messages_returns_empty_list_for_existing_empty_conversation(
    client: AsyncClient,
    authenticated_user,
    test_database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(app.dependencies, "database", test_database)
    conversation_id = UUID(int=200)

    async with test_database.session_factory() as session:
        session.add(Conversation(id=conversation_id, user_id=authenticated_user[0].id))
        await session.commit()

    response = await client.get(f"/api/conversations/{conversation_id}/messages")

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_list_messages_returns_not_found_for_missing_conversation(
    client: AsyncClient, test_database, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app.dependencies, "database", test_database)

    response = await client.get(f"/api/conversations/{UUID(int=300)}/messages")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_messages_hides_other_users_conversation(
    client: AsyncClient,
    test_database,
    user_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(app.dependencies, "database", test_database)
    owner = await user_factory(username="owner")
    conversation_id = UUID(int=400)

    async with test_database.session_factory() as session:
        session.add(Conversation(id=conversation_id, user_id=owner.id))
        await session.commit()

    response = await client.get(f"/api/conversations/{conversation_id}/messages")

    assert response.status_code == 404
    assert response.json() == {"detail": "Conversation not found."}
