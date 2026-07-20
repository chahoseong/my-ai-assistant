import asyncio
import logging
from collections.abc import AsyncIterator, Sequence
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic_ai import ModelMessage
from starlette.background import BackgroundTask
from sse_starlette import EventSourceResponse
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.agent import build_message_history
from app.concurrency import (
    ConversationLease,
    try_acquire_conversation,
)
from app.db import Database
from app.dependencies import CurrentUserForUnsafeRequest, JsonRequest, get_database
from app.models import Conversation, Message
from app.schemas import ConversationMessageCreate


router = APIRouter(prefix="/api/conversations")
logger = logging.getLogger(__name__)
STREAM_ERROR_MESSAGE = "Unable to generate a response."


def get_stream_agent():
    # The composition root owns the configured agent. Import lazily to avoid a
    # module cycle.
    from app.main import agent

    return agent


async def stream_persisted_message(
    database: Database,
    conversation_id: UUID,
    user_prompt: str,
    message_history: Sequence[ModelMessage],
    lease: ConversationLease,
) -> AsyncIterator[dict[str, str]]:
    try:
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

        yield {"event": "done", "data": str(assistant_message.id)}
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception(
            "message_stream_failed", extra={"event": "message_stream_failed"}
        )
        yield {"event": "error", "data": STREAM_ERROR_MESSAGE}
    finally:
        await lease.release()


@router.post("/{conversation_id}/messages")
async def send_message(
    conversation_id: UUID,
    payload: ConversationMessageCreate,
    current_user: CurrentUserForUnsafeRequest,
    _: JsonRequest,
    database: Database = Depends(get_database),
) -> EventSourceResponse:
    try:
        async with database.session_factory() as session:
            conversation = await session.scalar(
                select(Conversation).where(
                    Conversation.id == conversation_id,
                    Conversation.user_id == current_user.id,
                )
            )
            if conversation is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Conversation not found.",
                )
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        logger.exception("message_prepare_failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to prepare message.",
        ) from exc

    if not await try_acquire_conversation(conversation_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A message is already being generated for this conversation.",
        )

    lease = ConversationLease(conversation_id)
    ownership_transferred = False
    try:
        async with database.session_factory() as session:
            try:
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
            except SQLAlchemyError as exc:
                await session.rollback()
                logger.exception("message_prepare_failed")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Unable to prepare message.",
                ) from exc

        response = EventSourceResponse(
            stream_persisted_message(
                database,
                conversation_id,
                payload.message,
                history,
                lease,
            ),
            background=BackgroundTask(lease.release),
        )
        ownership_transferred = True
        return response
    finally:
        if not ownership_transferred:
            await lease.release()
