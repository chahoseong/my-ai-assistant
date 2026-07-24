from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import CurrentUser
from app.concurrency import ConversationLease, try_acquire_conversation
from app.database.dependencies import get_session
from app.database.models import Conversation
from app.observability.logging import get_logger
from app.observability.metrics import record_conversation_lock_conflict
from app.web.dependencies import CurrentUserForUnsafeRequest, JsonRequest
from app.web.schemas import ConversationCreate, ConversationResponse


router = APIRouter(prefix="/api/conversations")
logger = get_logger(__name__)


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
        logger.error("conversation_list_failed")
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
        logger.error("conversation_create_failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to create conversation.",
        ) from exc

    return conversation


@router.delete(
    "/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_conversation(
    conversation_id: UUID,
    current_user: CurrentUserForUnsafeRequest,
    session: AsyncSession = Depends(get_session),
) -> None:
    try:
        conversation = await session.scalar(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.user_id == current_user.id,
            )
        )
    except SQLAlchemyError as exc:
        logger.error("conversation_delete_failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to delete conversation.",
        ) from exc

    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found.",
        )

    if not await try_acquire_conversation(conversation_id):
        record_conversation_lock_conflict()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="응답 생성 중에는 삭제할 수 없습니다",
        )

    lease = ConversationLease(conversation_id)
    try:
        try:
            await session.delete(conversation)
            await session.commit()
        except SQLAlchemyError as exc:
            await session.rollback()
            logger.error("conversation_delete_failed")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Unable to delete conversation.",
            ) from exc
    finally:
        await lease.release()
