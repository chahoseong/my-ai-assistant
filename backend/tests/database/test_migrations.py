"""Destructive migration safety tests run only against TEST_DATABASE_URL."""

import os
import subprocess
import sys
from importlib import import_module
from pathlib import Path
from uuid import uuid4

import pytest


from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = pytest.mark.integration


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def alembic(*arguments: str) -> None:
    environment = dict(os.environ)
    environment["DATABASE_URL"] = environment["TEST_DATABASE_URL"]
    subprocess.run(
        [sys.executable, "-m", "alembic", *arguments],
        cwd=PROJECT_ROOT,
        env=environment,
        check=True,
    )


def test_destructive_owner_migration_round_trip_uses_test_database() -> None:
    """0003 may discard legacy rows; downgrade restores schema only."""
    alembic("downgrade", "20260718_0002")
    try:
        alembic("upgrade", "head")
    finally:
        alembic("upgrade", "head")


@pytest.mark.asyncio
async def test_destructive_migration_rolls_back_legacy_rows_on_failure() -> None:
    alembic("downgrade", "20260718_0002")
    engine = create_async_engine(os.environ["TEST_DATABASE_URL"])
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text("INSERT INTO conversations (id, title) VALUES (:id, 'legacy')"),
                {"id": uuid4()},
            )
        revision = import_module(
            "migrations.versions.20260718_0003_require_conversation_owners"
        )
        with pytest.raises(RuntimeError, match="abort migration"):
            async with engine.begin() as connection:

                def apply_then_abort(sync_connection) -> None:
                    operations = Operations(MigrationContext.configure(sync_connection))
                    revision.apply_owner_requirement(operations)
                    raise RuntimeError("abort migration")

                await connection.run_sync(apply_then_abort)

        async with engine.connect() as connection:
            count = await connection.scalar(text("SELECT count(*) FROM conversations"))
            nullable = await connection.scalar(
                text(
                    "SELECT is_nullable = 'YES' FROM information_schema.columns "
                    "WHERE table_name = 'conversations' AND column_name = 'user_id'"
                )
            )
        assert count == 1
        assert nullable is True
    finally:
        await engine.dispose()
        alembic("upgrade", "head")


@pytest.mark.asyncio
async def test_model_messages_migration_round_trip_uses_test_database() -> None:
    alembic("downgrade", "20260718_0003")
    engine = create_async_engine(os.environ["TEST_DATABASE_URL"])
    try:
        alembic("upgrade", "head")
        async with engine.connect() as connection:
            table_name = await connection.scalar(
                text("SELECT to_regclass('public.model_messages')")
            )
            payload_type = await connection.scalar(
                text(
                    "SELECT udt_name FROM information_schema.columns "
                    "WHERE table_name = 'model_messages' AND column_name = 'payload'"
                )
            )
            constraints = set(
                (
                    await connection.scalars(
                        text(
                            "SELECT conname FROM pg_constraint "
                            "WHERE conrelid = 'model_messages'::regclass"
                        )
                    )
                ).all()
            )
            foreign_key_delete_action = await connection.scalar(
                text(
                    "SELECT confdeltype FROM pg_constraint "
                    "WHERE conname = 'fk_model_messages_conversation_id_conversations'"
                )
            )
            index_name = await connection.scalar(
                text("SELECT to_regclass('public.ix_model_messages_conversation_sequence')")
            )

        assert table_name == "model_messages"
        assert payload_type == "jsonb"
        assert "uq_model_messages_conversation_sequence" in constraints
        assert foreign_key_delete_action == b"c"
        assert index_name == "ix_model_messages_conversation_sequence"

        alembic("downgrade", "20260718_0003")
        async with engine.connect() as connection:
            table_name = await connection.scalar(
                text("SELECT to_regclass('public.model_messages')")
            )
        assert table_name is None
    finally:
        await engine.dispose()
        alembic("upgrade", "head")
