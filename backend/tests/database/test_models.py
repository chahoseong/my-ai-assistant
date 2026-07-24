import importlib

import pytest
from sqlalchemy.dialects.postgresql import JSONB


pytestmark = pytest.mark.contract


def _foreign_key_ondelete(table, column_name: str) -> str | None:
    foreign_key = next(iter(table.c[column_name].foreign_keys))
    return foreign_key.ondelete


def test_message_metadata_declares_conversation_history_contract() -> None:
    models = importlib.import_module("app.database.models")

    conversations = models.Conversation.__table__
    messages = models.Message.__table__

    assert conversations.name == "conversations"
    assert messages.name == "messages"
    assert conversations.c.id.primary_key
    assert messages.c.id.primary_key
    assert _foreign_key_ondelete(messages, "conversation_id") == "CASCADE"
    assert {"ix_messages_conversation_created_at_id"} == {
        index.name for index in messages.indexes
    }
    assert {"ck_messages_role"} == {
        constraint.name for constraint in messages.constraints if constraint.name
    }


def test_model_message_metadata_declares_agent_history_contract() -> None:
    models = importlib.import_module("app.database.models")

    model_messages = models.ModelMessageRecord.__table__

    assert model_messages.name == "model_messages"
    assert model_messages.c.id.primary_key
    assert model_messages.c.conversation_id.nullable is False
    assert model_messages.c.sequence.nullable is False
    assert isinstance(model_messages.c.payload.type, JSONB)
    assert _foreign_key_ondelete(model_messages, "conversation_id") == "CASCADE"
    assert {"ix_model_messages_conversation_sequence"} == {
        index.name for index in model_messages.indexes
    }
    assert {"uq_model_messages_conversation_sequence"} <= {
        constraint.name for constraint in model_messages.constraints if constraint.name
    }
    assert "model_messages" in models.Conversation.__mapper__.relationships


def test_authentication_metadata_declares_ownership_and_session_contract() -> None:
    models = importlib.import_module("app.database.models")

    users = models.User.__table__
    sessions = models.AuthSession.__table__
    conversations = models.Conversation.__table__

    assert users.name == "users"
    assert sessions.name == "sessions"
    assert users.c.username.unique
    assert sessions.c.token_hash.unique
    assert _foreign_key_ondelete(sessions, "user_id") == "CASCADE"
    assert _foreign_key_ondelete(conversations, "user_id") == "RESTRICT"
    assert conversations.c.user_id.nullable is False
