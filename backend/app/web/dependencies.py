from typing import Annotated

from fastapi import Depends, Request

from app.auth.dependencies import CurrentUser, get_auth_settings
from app.config import AuthSettings
from app.database.models import User
from app.web.security import require_allowed_origin, require_json_content_type


def enforce_allowed_origin(
    request: Request,
    settings: Annotated[AuthSettings, Depends(get_auth_settings)],
) -> None:
    require_allowed_origin(request, settings)


def enforce_json_request(request: Request) -> None:
    require_json_content_type(request)


async def get_current_user_for_unsafe_request(
    user: CurrentUser,
    request: Request,
    settings: Annotated[AuthSettings, Depends(get_auth_settings)],
) -> User:
    require_allowed_origin(request, settings)
    return user


AllowedOrigin = Annotated[None, Depends(enforce_allowed_origin)]
JsonRequest = Annotated[None, Depends(enforce_json_request)]
CurrentUserForUnsafeRequest = Annotated[
    User, Depends(get_current_user_for_unsafe_request)
]
