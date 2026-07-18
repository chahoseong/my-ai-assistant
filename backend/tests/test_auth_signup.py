import asyncio

from httpx import AsyncClient
import pytest
from sqlalchemy import select

import app.dependencies
from app.models import User


@pytest.mark.asyncio
async def test_signup_normalizes_username_and_does_not_expose_password_hash(
    client: AsyncClient, test_database, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app.dependencies, "database", test_database)

    response = await client.post(
        "/api/auth/signup",
        json={"username": "  Alice_42 ", "password": "correct horse battery staple"},
    )

    assert response.status_code == 201
    assert response.json()["username"] == "alice_42"
    assert "password" not in response.json()
    assert "password_hash" not in response.json()

    async with test_database.session_factory() as session:
        user = await session.scalar(select(User).where(User.username == "alice_42"))

    assert user is not None
    assert user.password_hash.startswith("$argon2id$")


@pytest.mark.asyncio
@pytest.mark.parametrize("password", ["a" * 14, "a" * 129])
async def test_signup_rejects_password_outside_allowed_length(
    client: AsyncClient,
    test_database,
    monkeypatch: pytest.MonkeyPatch,
    password: str,
) -> None:
    monkeypatch.setattr(app.dependencies, "database", test_database)

    response = await client.post(
        "/api/auth/signup",
        json={"username": "alice", "password": password},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_signup_returns_conflict_for_duplicate_username(
    client: AsyncClient, test_database, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app.dependencies, "database", test_database)
    payload = {"username": "alice", "password": "correct horse battery staple"}

    first_response = await client.post("/api/auth/signup", json=payload)
    second_response = await client.post("/api/auth/signup", json=payload)

    assert first_response.status_code == 201
    assert second_response.status_code == 409


@pytest.mark.asyncio
async def test_concurrent_duplicate_signups_allow_only_one_success(
    client: AsyncClient, test_database, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app.dependencies, "database", test_database)
    payload = {
        "username": "concurrent_user",
        "password": "correct horse battery staple",
    }

    responses = await asyncio.gather(
        client.post("/api/auth/signup", json=payload),
        client.post("/api/auth/signup", json=payload),
    )

    assert sorted(response.status_code for response in responses) == [201, 409]


@pytest.mark.asyncio
async def test_signup_rejects_disallowed_origin_before_creating_user(
    client: AsyncClient, test_database, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app.dependencies, "database", test_database)

    response = await client.post(
        "/api/auth/signup",
        headers={"origin": "https://evil.example"},
        json={"username": "alice", "password": "correct horse battery staple"},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_signup_rejects_non_json_content_type(
    client: AsyncClient, test_database, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app.dependencies, "database", test_database)

    response = await client.post(
        "/api/auth/signup",
        headers={"content-type": "text/plain"},
        content='{"username":"alice","password":"correct horse battery staple"}',
    )

    assert response.status_code == 415
