from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import UUID

from httpx import ASGITransport, AsyncClient
import pytest

import app.dependencies
import app.main
from app.models import Conversation, Message


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app.main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
async def test_list_messages_returns_deterministic_created_at_and_id_order(
    client: AsyncClient, test_database, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app.dependencies, "database", test_database)
    conversation_id = UUID(int=100)
    same_time = datetime(2026, 1, 1, tzinfo=UTC)

    async with test_database.session_factory() as session:
        session.add(
            Conversation(
                id=conversation_id,
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
    client: AsyncClient, test_database, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app.dependencies, "database", test_database)
    conversation_id = UUID(int=200)

    async with test_database.session_factory() as session:
        session.add(Conversation(id=conversation_id))
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
