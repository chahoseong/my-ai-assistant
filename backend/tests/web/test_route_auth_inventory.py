from httpx import ASGITransport, AsyncClient
import pytest


import app.main

pytestmark = pytest.mark.contract


def test_openapi_authentication_route_inventory_is_stable() -> None:
    paths = app.main.app.openapi()["paths"]

    assert {
        ("post", "/api/auth/signup"),
        ("post", "/api/auth/login"),
        ("post", "/api/auth/logout"),
        ("get", "/api/auth/me"),
        ("get", "/api/conversations"),
        ("post", "/api/conversations"),
        ("delete", "/api/conversations/{conversation_id}"),
        ("get", "/api/conversations/{conversation_id}/messages"),
        ("post", "/api/conversations/{conversation_id}/messages"),
    } == {
        (method, path)
        for path, operations in paths.items()
        for method in operations
        if method in {"delete", "get", "post"}
    }


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.parametrize(
    ("method", "path", "json", "expects_json_error"),
    [
        ("post", "/api/conversations", {}, False),
        (
            "delete",
            "/api/conversations/00000000-0000-0000-0000-000000000001",
            None,
            False,
        ),
        (
            "get",
            "/api/conversations/00000000-0000-0000-0000-000000000001/messages",
            None,
            False,
        ),
        (
            "post",
            "/api/conversations/00000000-0000-0000-0000-000000000001/messages",
            {"message": "hello"},
            True,
        ),
        ("get", "/api/auth/me", None, False),
    ],
)
async def test_protected_routes_reject_anonymous_requests(
    method: str,
    path: str,
    json: dict[str, str] | None,
    expects_json_error: bool,
) -> None:
    transport = ASGITransport(app=app.main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.request(method, path, json=json)

    assert response.status_code == 401
    if expects_json_error:
        assert response.headers["content-type"].startswith("application/json")
