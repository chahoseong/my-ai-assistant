import asyncio
from uuid import UUID

import pytest

from app.concurrency import release_conversation, try_acquire_conversation


@pytest.mark.asyncio
async def test_conversation_lock_rejects_duplicate_until_released() -> None:
    conversation_id = UUID(int=700)

    assert await try_acquire_conversation(conversation_id) is True
    assert await try_acquire_conversation(conversation_id) is False

    await release_conversation(conversation_id)

    assert await try_acquire_conversation(conversation_id) is True
    await release_conversation(conversation_id)


@pytest.mark.asyncio
async def test_conversation_lock_allows_only_one_racing_acquisition() -> None:
    conversation_id = UUID(int=701)

    results = await asyncio.gather(
        *(try_acquire_conversation(conversation_id) for _ in range(20))
    )

    assert results.count(True) == 1
    assert results.count(False) == 19
    await release_conversation(conversation_id)
