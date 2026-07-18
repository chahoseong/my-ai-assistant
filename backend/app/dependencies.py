import os
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import AuthSettings, load_auth_settings, load_database_settings
from app.db import Database, create_database
from app.request_security import require_allowed_origin, require_json_content_type


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
