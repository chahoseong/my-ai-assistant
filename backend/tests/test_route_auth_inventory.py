from httpx import ASGITransport, AsyncClient
import pytest

import app.main


def test_openapi_authentication_route_inventory_is_stable() -> None:
    paths = app.main.app.openapi()["paths"]

    assert {
        ("post", "/api/auth/signup"),
        ("post", "/api/auth/login"),
        ("post", "/api/auth/logout"),
        ("get", "/api/auth/me"),
        ("post", "/api/conversations"),
        ("get", "/api/conversations/{conversation_id}/messages"),
        ("post", "/api/conversations/{conversation_id}/messages"),
    } == {
        (method, path)
        for path, operations in paths.items()
        for method in operations
        if method in {"get", "post"}
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "path", "json"),
    [
        ("post", "/api/conversations", {}),
        (
            "get",
            "/api/conversations/00000000-0000-0000-0000-000000000001/messages",
            None,
        ),
        (
            "post",
            "/api/conversations/00000000-0000-0000-0000-000000000001/messages",
            {"message": "hello"},
        ),
        ("get", "/api/auth/me", None),
    ],
)
async def test_protected_routes_reject_anonymous_requests(
    method: str, path: str, json: dict[str, str] | None
) -> None:
    transport = ASGITransport(app=app.main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.request(method, path, json=json)

    assert response.status_code == 401
