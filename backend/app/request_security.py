from fastapi import HTTPException, Request, status

from app.config import AuthSettings


def require_allowed_origin(request: Request, settings: AuthSettings) -> None:
    origin = request.headers.get("origin")
    if origin is None:
        return
    if origin == "null" or origin not in settings.allowed_origins:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Origin not allowed.",
        )


def require_json_content_type(request: Request) -> None:
    content_type = request.headers.get("content-type", "")
    media_type = content_type.split(";", maxsplit=1)[0].strip().lower()
    if media_type != "application/json":
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Content-Type must be application/json.",
        )
