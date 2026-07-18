import os
import subprocess
import sys
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from httpx import ASGITransport, AsyncClient
import pytest
import pytest_asyncio

import app.main
from app.db import Database, create_database
from app.models import AuthSession, Conversation, User
from app.security import generate_session_token, hash_session_token
from app.test_db_safety import (
    truncate_test_database,
    validate_test_database_identity,
    validate_test_database_url,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def upgrade_test_schema(test_url: str) -> None:
    migration_env = dict(os.environ)
    migration_env["DATABASE_URL"] = test_url
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=PROJECT_ROOT,
        env=migration_env,
        check=True,
    )


@pytest_asyncio.fixture
async def test_database() -> AsyncIterator[Database]:
    test_url = validate_test_database_url(os.environ)
    database_url = os.environ["DATABASE_URL"]
    await validate_test_database_identity(database_url, test_url)
    upgrade_test_schema(test_url)
    database = create_database(test_url)

    try:
        await truncate_test_database(database.engine)
        yield database
    finally:
        await truncate_test_database(database.engine)
        await database.dispose()


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app.main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client


@pytest.fixture
def user_factory(test_database: Database):
    async def create_user(
        *,
        username: str | None = None,
        password_hash: str = "$argon2id$test-password-hash",
    ) -> User:
        user = User(
            username=username or f"user_{uuid4().hex}",
            password_hash=password_hash,
        )
        async with test_database.session_factory() as session:
            session.add(user)
            await session.commit()
            await session.refresh(user)
        return user

    return create_user


@pytest.fixture
def session_factory(test_database: Database):
    async def create_session(*, user: User) -> tuple[AuthSession, str]:
        token = generate_session_token()
        auth_session = AuthSession(
            token_hash=hash_session_token(token),
            user_id=user.id,
            expires_at=datetime.now(UTC) + timedelta(days=30),
        )
        async with test_database.session_factory() as session:
            session.add(auth_session)
            await session.commit()
            await session.refresh(auth_session)
        return auth_session, token

    return create_session


@pytest.fixture
def conversation_factory(test_database: Database):
    async def create_conversation(
        *,
        user: User | None = None,
        title: str | None = None,
    ) -> Conversation:
        conversation = Conversation(
            user_id=user.id if user is not None else None, title=title
        )
        async with test_database.session_factory() as session:
            session.add(conversation)
            await session.commit()
            await session.refresh(conversation)
        return conversation

    return create_conversation
