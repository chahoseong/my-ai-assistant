from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import CurrentUser
from app.database.dependencies import get_session
from app.database.models import Conversation, Message
from app.observability.logging import get_logger
from app.web.schemas import MessageResponse


router = APIRouter(prefix="/api/conversations")
logger = get_logger(__name__)


@router.get(
    "/{conversation_id}/messages",
    response_model=list[MessageResponse],
)
async def list_messages(
    conversation_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> list[Message]:
    try:
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

        result = await session.scalars(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.asc(), Message.id.asc())
        )
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        logger.error("message_list_failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to list messages.",
        ) from exc

    return list(result)
