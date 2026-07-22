from datetime import UTC, datetime

from sqlalchemy import func, select

import pytest


from app.database.models import AuthSession, Conversation, Message, User
from tests.support.database_safety import truncate_test_database

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_test_database_schema_and_cleanup(test_database) -> None:
    async with test_database.session_factory() as session:
        user = User(username="cleanup_user", password_hash="$argon2id$test")
        conversation = Conversation(title="cleanup check", user=user)
        conversation.messages.append(Message(role="user", content="hello"))
        auth_session = AuthSession(
            token_hash="a" * 64,
            user=user,
            expires_at=datetime(2030, 1, 1, tzinfo=UTC),
        )
        session.add(conversation)
        session.add(auth_session)
        await session.commit()

    await truncate_test_database(test_database.engine)

    async with test_database.session_factory() as session:
        conversation_count = await session.scalar(
            select(func.count()).select_from(Conversation)
        )
        message_count = await session.scalar(select(func.count()).select_from(Message))
        user_count = await session.scalar(select(func.count()).select_from(User))
        auth_session_count = await session.scalar(
            select(func.count()).select_from(AuthSession)
        )

    assert conversation_count == 0
    assert message_count == 0
    assert user_count == 0
    assert auth_session_count == 0
