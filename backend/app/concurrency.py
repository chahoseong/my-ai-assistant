import asyncio
from uuid import UUID

_active_conversations: set[UUID] = set()
_active_guard = asyncio.Lock()


async def try_acquire_conversation(conversation_id: UUID) -> bool:
    async with _active_guard:
        if conversation_id in _active_conversations:
            return False

        _active_conversations.add(conversation_id)
        return True


async def release_conversation(conversation_id: UUID) -> None:
    async with _active_guard:
        _active_conversations.discard(conversation_id)
