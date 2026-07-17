import asyncio
from uuid import UUID

_active_conversations: set[UUID] = set()
_active_guard = asyncio.Lock()


class ConversationLease:
    def __init__(self, conversation_id: UUID) -> None:
        self._conversation_id = conversation_id
        self._release_guard = asyncio.Lock()
        self._released = False

    async def release(self) -> None:
        async with self._release_guard:
            if self._released:
                return

            await release_conversation(self._conversation_id)
            self._released = True


async def try_acquire_conversation(conversation_id: UUID) -> bool:
    async with _active_guard:
        if conversation_id in _active_conversations:
            return False

        _active_conversations.add(conversation_id)
        return True


async def release_conversation(conversation_id: UUID) -> None:
    async with _active_guard:
        _active_conversations.discard(conversation_id)
