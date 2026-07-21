import os
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy import func, select

from app.config import AuthSettings, load_auth_settings
from app.database.dependencies import get_database
from app.database.core import Database
from app.database.models import AuthSession, User
from app.auth.security import SESSION_COOKIE_NAME, hash_session_token


def get_auth_settings() -> AuthSettings:
    return load_auth_settings(os.environ)


async def get_current_user(
    session_token: Annotated[str | None, Cookie(alias=SESSION_COOKIE_NAME)] = None,
    current_database: Database = Depends(get_database),
) -> User:
    if session_token is None or len(session_token) > 256:
        raise _invalid_session()

    async with current_database.session_factory() as session:
        user = await session.scalar(
            select(User)
            .join(AuthSession)
            .where(
                AuthSession.token_hash == hash_session_token(session_token),
                AuthSession.expires_at > func.now(),
            )
        )
    if user is None:
        raise _invalid_session()
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def _invalid_session() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid session.",
    )
