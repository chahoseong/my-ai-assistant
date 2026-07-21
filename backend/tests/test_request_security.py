import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.config import AuthSettings


def make_request(headers: dict[str, str]) -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "scheme": "http",
            "path": "/api/example",
            "headers": [
                (name.encode(), value.encode()) for name, value in headers.items()
            ],
        }
    )


def test_exact_allowed_origin_and_missing_origin_are_allowed() -> None:
    from app.web.security import require_allowed_origin

    settings = AuthSettings(
        app_env="local",
        cookie_secure=False,
        allowed_origins=frozenset({"http://localhost:8000"}),
    )

    require_allowed_origin(make_request({"origin": "http://localhost:8000"}), settings)
    require_allowed_origin(make_request({}), settings)


@pytest.mark.parametrize("origin", ["http://localhost:8000.evil", "null"])
def test_mismatched_and_null_origin_are_rejected(origin: str) -> None:
    from app.web.security import require_allowed_origin

    settings = AuthSettings(
        app_env="local",
        cookie_secure=False,
        allowed_origins=frozenset({"http://localhost:8000"}),
    )

    with pytest.raises(HTTPException) as exc_info:
        require_allowed_origin(make_request({"origin": origin}), settings)

    assert exc_info.value.status_code == 403


@pytest.mark.parametrize(
    "content_type", ["application/json", "application/json; charset=utf-8"]
)
def test_json_content_type_is_allowed(content_type: str) -> None:
    from app.web.security import require_json_content_type

    require_json_content_type(make_request({"content-type": content_type}))


@pytest.mark.parametrize(
    "content_type", [None, "text/plain", "application/x-www-form-urlencoded"]
)
def test_non_json_content_type_is_rejected(content_type: str | None) -> None:
    from app.web.security import require_json_content_type

    headers = {} if content_type is None else {"content-type": content_type}

    with pytest.raises(HTTPException) as exc_info:
        require_json_content_type(make_request(headers))

    assert exc_info.value.status_code == 415
