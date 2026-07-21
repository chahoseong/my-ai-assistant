from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import AuthSettings
from app.auth.dependencies import CurrentUser, get_auth_settings
from app.database.dependencies import get_session
from app.web.dependencies import (
    AllowedOrigin,
    JsonRequest,
)
from app.database.models import AuthSession, User
from app.observability.logging import get_logger
from app.web.schemas import LoginRequest, PublicUser, SignupRequest
from app.auth.security import (
    PASSWORD_HASHER,
    SESSION_COOKIE_NAME,
    SESSION_MAX_AGE_SECONDS,
    generate_session_token,
    hash_password,
    hash_session_token,
    password_needs_rehash,
    verify_password,
)


router = APIRouter(prefix="/api/auth")
logger = get_logger(__name__)
DUMMY_PASSWORD_HASH = PASSWORD_HASHER.hash("dummy-login-password")


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
        logger.error("signup_integrity_error")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to create account.",
        ) from exc
    except SQLAlchemyError as exc:
        await session.rollback()
        logger.error("signup_failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to create account.",
        ) from exc

    return user


@router.post("/login", status_code=status.HTTP_204_NO_CONTENT)
async def login(
    payload: LoginRequest,
    _: AllowedOrigin,
    __: JsonRequest,
    settings: Annotated[AuthSettings, Depends(get_auth_settings)],
    session: AsyncSession = Depends(get_session),
) -> Response:
    user = await session.scalar(select(User).where(User.username == payload.username))
    if user is None:
        await verify_password(DUMMY_PASSWORD_HASH, payload.password)
        raise _invalid_credentials()

    if not await verify_password(user.password_hash, payload.password):
        raise _invalid_credentials()

    if password_needs_rehash(user.password_hash):
        user.password_hash = await hash_password(payload.password)

    raw_token = generate_session_token()
    session.add(
        AuthSession(
            token_hash=hash_session_token(raw_token),
            user_id=user.id,
            expires_at=datetime.now(UTC) + timedelta(seconds=SESSION_MAX_AGE_SECONDS),
        )
    )

    try:
        await session.commit()
    except SQLAlchemyError as exc:
        await session.rollback()
        logger.error("login_session_create_failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to log in.",
        ) from exc

    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=raw_token,
        max_age=SESSION_MAX_AGE_SECONDS,
        path="/",
        secure=settings.cookie_secure,
        httponly=True,
        samesite="lax",
    )
    return response


@router.get("/me", response_model=PublicUser)
async def get_me(user: CurrentUser) -> User:
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    _: AllowedOrigin,
    session: AsyncSession = Depends(get_session),
    session_token: Annotated[str | None, Cookie(alias=SESSION_COOKIE_NAME)] = None,
) -> Response:
    if session_token is not None and len(session_token) <= 256:
        await session.execute(
            delete(AuthSession).where(
                AuthSession.token_hash == hash_session_token(session_token)
            )
        )
        await session.commit()

    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(key=SESSION_COOKIE_NAME, path="/")
    return response


def _invalid_credentials() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid credentials.",
    )
