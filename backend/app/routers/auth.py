import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import AllowedOrigin, JsonRequest, get_session
from app.models import User
from app.schemas import PublicUser, SignupRequest
from app.security import hash_password


router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/signup", response_model=PublicUser, status_code=status.HTTP_201_CREATED)
async def signup(
    payload: SignupRequest,
    _: AllowedOrigin,
    __: JsonRequest,
    session: AsyncSession = Depends(get_session),
) -> User:
    user = User(
        username=payload.username,
        password_hash=await hash_password(payload.password),
    )
    session.add(user)

    try:
        await session.commit()
        await session.refresh(user)
    except IntegrityError as exc:
        await session.rollback()
        if getattr(exc.orig, "sqlstate", None) == "23505":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Username already exists.",
            ) from exc
        logger.exception("signup_integrity_error")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to create account.",
        ) from exc
    except SQLAlchemyError as exc:
        await session.rollback()
        logger.exception("signup_failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to create account.",
        ) from exc

    return user
