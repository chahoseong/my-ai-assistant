import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_session
from app.models import Conversation, Message
from app.schemas import MessageResponse


router = APIRouter()
logger = logging.getLogger(__name__)


@router.get(
    "/{conversation_id}/messages",
    response_model=list[MessageResponse],
)
async def list_messages(
    conversation_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> list[Message]:
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
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        logger.exception("message_list_failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to list messages.",
        ) from exc

    return list(result)
