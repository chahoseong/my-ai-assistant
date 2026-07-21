from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
import pytest
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

import app.database.dependencies
import app.routers.auth
from app.database.models import AuthSession
from app.auth.security import hash_password, hash_session_token


async def create_login_user(user_factory):
    password = "correct horse battery staple"
    return await user_factory(
        username="alice",
        password_hash=await hash_password(password),
    ), password


@pytest.mark.asyncio
async def test_login_creates_hashed_30_day_session_and_cookie(
    client: AsyncClient, test_database, user_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app.database.dependencies, "database", test_database)
    user, password = await create_login_user(user_factory)
    before_login = datetime.now(UTC)

    response = await client.post(
        "/api/auth/login", json={"username": "ALICE", "password": password}
    )

    assert response.status_code == 204
    raw_token = response.cookies.get("assistant_session")
    assert raw_token is not None
    set_cookie = response.headers["set-cookie"]
    assert "HttpOnly" in set_cookie
    assert "Max-Age=2592000" in set_cookie
    assert "Path=/" in set_cookie
    assert "SameSite=lax" in set_cookie
    assert "Domain=" not in set_cookie

    async with test_database.session_factory() as session:
        auth_session = await session.scalar(
            select(AuthSession).where(AuthSession.user_id == user.id)
        )

    assert auth_session is not None
    assert auth_session.token_hash == hash_session_token(raw_token)
    assert raw_token not in auth_session.token_hash
    assert (
        before_login + timedelta(days=30)
        <= auth_session.expires_at
        <= datetime.now(UTC) + timedelta(days=30, seconds=2)
    )


@pytest.mark.asyncio
async def test_unknown_user_and_wrong_password_have_identical_401_body(
    client: AsyncClient, test_database, user_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app.database.dependencies, "database", test_database)
    _, password = await create_login_user(user_factory)

    unknown_response = await client.post(
        "/api/auth/login", json={"username": "unknown", "password": password}
    )
    wrong_password_response = await client.post(
        "/api/auth/login",
        json={"username": "alice", "password": "wrong password value"},
    )

    assert unknown_response.status_code == wrong_password_response.status_code == 401
    assert (
        unknown_response.json()
        == wrong_password_response.json()
        == {"detail": "Invalid credentials."}
    )


@pytest.mark.asyncio
async def test_unknown_user_verifies_dummy_hash(
    client: AsyncClient, test_database, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app.database.dependencies, "database", test_database)
    verified_hashes: list[str] = []

    async def verify_spy(encoded_hash: str, password: str) -> bool:
        verified_hashes.append(encoded_hash)
        return False

    monkeypatch.setattr(app.routers.auth, "verify_password", verify_spy)

    response = await client.post(
        "/api/auth/login",
        json={"username": "unknown", "password": "correct horse battery staple"},
    )

    assert response.status_code == 401
    assert verified_hashes == [app.routers.auth.DUMMY_PASSWORD_HASH]


@pytest.mark.asyncio
async def test_login_rehashes_stale_password_hash(
    client: AsyncClient, test_database, user_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app.database.dependencies, "database", test_database)
    user, password = await create_login_user(user_factory)
    monkeypatch.setattr(app.routers.auth, "password_needs_rehash", lambda _: True)

    async def replacement_hash(_: str) -> str:
        return "$argon2id$replacement"

    monkeypatch.setattr(app.routers.auth, "hash_password", replacement_hash)

    response = await client.post(
        "/api/auth/login", json={"username": "alice", "password": password}
    )

    assert response.status_code == 204
    async with test_database.session_factory() as session:
        refreshed_user = await session.get(type(user), user.id)
    assert refreshed_user is not None
    assert refreshed_user.password_hash == "$argon2id$replacement"


@pytest.mark.asyncio
async def test_login_does_not_set_cookie_when_session_commit_fails(
    client: AsyncClient, test_database, user_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app.database.dependencies, "database", test_database)
    _, password = await create_login_user(user_factory)

    async def failing_commit(self) -> None:
        raise SQLAlchemyError("database unavailable")

    monkeypatch.setattr("sqlalchemy.ext.asyncio.AsyncSession.commit", failing_commit)

    response = await client.post(
        "/api/auth/login", json={"username": "alice", "password": password}
    )

    assert response.status_code == 500
    assert "set-cookie" not in response.headers
