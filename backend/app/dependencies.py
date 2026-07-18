import os
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import AuthSettings, load_auth_settings, load_database_settings
from app.db import Database, create_database
from app.models import AuthSession, User
from app.request_security import require_allowed_origin, require_json_content_type
from app.security import SESSION_COOKIE_NAME, hash_session_token


database: Database | None = None


def get_database() -> Database:
    global database
    if database is None:
        settings = load_database_settings(os.environ)
        database = create_database(settings.url)
    return database


async def dispose_database() -> None:
    global database
    current_database = database
    database = None
    if current_database is not None:
        await current_database.dispose()


async def get_session() -> AsyncIterator[AsyncSession]:
    current_database = get_database()
    async with current_database.session_factory() as session:
        yield session


def get_auth_settings() -> AuthSettings:
    return load_auth_settings(os.environ)


def enforce_allowed_origin(
    request: Request,
    settings: Annotated[AuthSettings, Depends(get_auth_settings)],
) -> None:
    require_allowed_origin(request, settings)


def enforce_json_request(request: Request) -> None:
    require_json_content_type(request)


AllowedOrigin = Annotated[None, Depends(enforce_allowed_origin)]
JsonRequest = Annotated[None, Depends(enforce_json_request)]


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


async def get_current_user_for_unsafe_request(
    user: Annotated[User, Depends(get_current_user)],
    request: Request,
    settings: Annotated[AuthSettings, Depends(get_auth_settings)],
) -> User:
    require_allowed_origin(request, settings)
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
CurrentUserForUnsafeRequest = Annotated[
    User, Depends(get_current_user_for_unsafe_request)
]


def _invalid_session() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid session.",
    )
