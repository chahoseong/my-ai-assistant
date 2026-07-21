from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
import pytest


import app.database.dependencies

pytestmark = pytest.mark.integration



async def authenticated_client(client: AsyncClient, user_factory, session_factory):
    user = await user_factory(username="alice")
    _, token = await session_factory(user=user)
    client.cookies.set("assistant_session", token)
    return token


@pytest.mark.asyncio
async def test_me_returns_public_user_for_valid_session(
    client: AsyncClient,
    test_database,
    user_factory,
    session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(app.database.dependencies, "database", test_database)
    await authenticated_client(client, user_factory, session_factory)

    response = await client.get("/api/auth/me")

    assert response.status_code == 200
    assert response.json()["username"] == "alice"
    assert "password_hash" not in response.json()


@pytest.mark.asyncio
@pytest.mark.parametrize("token", [None, "unknown-token", "x" * 257])
async def test_me_returns_same_401_for_invalid_session_states(
    client: AsyncClient,
    test_database,
    monkeypatch: pytest.MonkeyPatch,
    token: str | None,
) -> None:
    monkeypatch.setattr(app.database.dependencies, "database", test_database)
    if token is not None:
        client.cookies.set("assistant_session", token)

    response = await client.get("/api/auth/me")

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid session."}


@pytest.mark.asyncio
async def test_me_rejects_expired_session(
    client: AsyncClient, test_database, user_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.database.models import AuthSession
    from app.auth.security import generate_session_token, hash_session_token

    monkeypatch.setattr(app.database.dependencies, "database", test_database)
    user = await user_factory(username="alice")
    token = generate_session_token()
    async with test_database.session_factory() as session:
        session.add(
            AuthSession(
                token_hash=hash_session_token(token),
                user_id=user.id,
                expires_at=datetime.now(UTC) - timedelta(seconds=1),
            )
        )
        await session.commit()
    client.cookies.set("assistant_session", token)

    response = await client.get("/api/auth/me")

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid session."}


@pytest.mark.asyncio
async def test_logout_is_idempotent_and_revokes_session(
    client: AsyncClient,
    test_database,
    user_factory,
    session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(app.database.dependencies, "database", test_database)
    token = await authenticated_client(client, user_factory, session_factory)

    first_logout = await client.post("/api/auth/logout")
    client.cookies.set("assistant_session", token)
    second_logout = await client.post("/api/auth/logout")
    client.cookies.set("assistant_session", token)
    me_response = await client.get("/api/auth/me")

    assert first_logout.status_code == second_logout.status_code == 204
    assert "Max-Age=0" in first_logout.headers["set-cookie"]
    assert me_response.status_code == 401
