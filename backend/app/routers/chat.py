import logging
from collections.abc import AsyncIterator, Sequence
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic_ai import ModelMessage
from sse_starlette import EventSourceResponse
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.agent import build_message_history
from app.db import Database
from app.dependencies import get_database
from app.models import Conversation, Message
from app.schemas import ConversationMessageCreate


router = APIRouter()
logger = logging.getLogger(__name__)


def get_stream_agent():
    # The composition root owns the configured agent. Import lazily to avoid a
    # module cycle while keeping the existing /api/chat test seam intact.
    from app.main import agent

    return agent


async def stream_persisted_message(
    database: Database,
    conversation_id: UUID,
    user_prompt: str,
    message_history: Sequence[ModelMessage],
) -> AsyncIterator[dict[str, str]]:
    response_parts: list[str] = []
    stream = get_stream_agent().run_stream(
        user_prompt,
        message_history=message_history,
    )

    async with stream as result:
        async for token in result.stream_text(delta=True):
            response_parts.append(token)
            yield {"data": token}

    async with database.session_factory() as session:
        assistant_message = Message(
            conversation_id=conversation_id,
            role="assistant",
            content="".join(response_parts),
        )
        session.add(assistant_message)
        await session.commit()
        await session.refresh(assistant_message)

    yield {"event": "done", "data": str(assistant_message.id)}


@router.post("/{conversation_id}/messages")
async def send_message(
    conversation_id: UUID,
    payload: ConversationMessageCreate,
    database: Database = Depends(get_database),
) -> EventSourceResponse:
    async with database.session_factory() as session:
        try:
            conversation = await session.get(Conversation, conversation_id)
            if conversation is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Conversation not found.",
                )

            result = await session.scalars(
                select(Message)
                .where(Message.conversation_id == conversation_id)
                .order_by(Message.created_at.asc(), Message.id.asc())
            )
            history = build_message_history(list(result))

            session.add(
                Message(
                    conversation_id=conversation_id,
                    role="user",
                    content=payload.message,
                )
            )
            await session.commit()
        except HTTPException:
            raise
        except SQLAlchemyError as exc:
            await session.rollback()
            logger.exception("message_prepare_failed")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Unable to prepare message.",
            ) from exc

    return EventSourceResponse(
        stream_persisted_message(
            database,
            conversation_id,
            payload.message,
            history,
        )
    )
