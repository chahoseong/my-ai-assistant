import importlib


def test_message_metadata_declares_conversation_history_contract() -> None:
    models = importlib.import_module("app.models")

    conversations = models.Conversation.__table__
    messages = models.Message.__table__

    assert conversations.name == "conversations"
    assert messages.name == "messages"
    assert conversations.c.id.primary_key
    assert messages.c.id.primary_key
    assert messages.c.conversation_id.foreign_keys.pop().ondelete == "CASCADE"
    assert {"ix_messages_conversation_created_at_id"} == {
        index.name for index in messages.indexes
    }
    assert {"ck_messages_role"} == {
        constraint.name for constraint in messages.constraints if constraint.name
    }
