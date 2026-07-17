from sqlalchemy import func, select

import pytest

from app.models import Conversation, Message
from app.test_db_safety import truncate_test_database


@pytest.mark.asyncio
async def test_test_database_schema_and_cleanup(test_database) -> None:
    async with test_database.session_factory() as session:
        conversation = Conversation(title="cleanup check")
        conversation.messages.append(Message(role="user", content="hello"))
        session.add(conversation)
        await session.commit()

    await truncate_test_database(test_database.engine)

    async with test_database.session_factory() as session:
        conversation_count = await session.scalar(
            select(func.count()).select_from(Conversation)
        )
        message_count = await session.scalar(select(func.count()).select_from(Message))

    assert conversation_count == 0
    assert message_count == 0
