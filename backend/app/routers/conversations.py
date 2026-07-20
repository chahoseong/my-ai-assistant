import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import (
    CurrentUser,
    CurrentUserForUnsafeRequest,
    JsonRequest,
    get_session,
)
from app.models import Conversation
from app.schemas import ConversationCreate, ConversationResponse


router = APIRouter(prefix="/api/conversations")
logger = logging.getLogger(__name__)


@router.get("", response_model=list[ConversationResponse])
async def list_conversations(
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> list[Conversation]:
    try:
        result = await session.scalars(
            select(Conversation)
            .where(Conversation.user_id == current_user.id)
            .order_by(Conversation.created_at.desc(), Conversation.id.desc())
        )
    except SQLAlchemyError as exc:
        logger.exception("conversation_list_failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to list conversations.",
        ) from exc

    return list(result)


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
