import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import CurrentUserForUnsafeRequest, JsonRequest, get_session
from app.models import Conversation
from app.schemas import ConversationCreate, ConversationResponse


router = APIRouter()
logger = logging.getLogger(__name__)


@router.post(
    "",
    response_model=ConversationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_conversation(
    payload: ConversationCreate,
    current_user: CurrentUserForUnsafeRequest,
    _: JsonRequest,
    session: AsyncSession = Depends(get_session),
) -> Conversation:
    conversation = Conversation(title=payload.title, user_id=current_user.id)
    session.add(conversation)

    try:
        await session.commit()
        await session.refresh(conversation)
    except SQLAlchemyError as exc:
        await session.rollback()
        logger.exception("conversation_create_failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to create conversation.",
        ) from exc

    return conversation
