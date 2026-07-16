from datetime import UTC, datetime
from uuid import UUID

from pydantic_ai import ModelRequest, ModelResponse, TextPart, UserPromptPart

from app.agent import build_message_history
from app.models import Message


def test_build_message_history_maps_database_messages_to_model_messages() -> None:
    user_time = datetime(2026, 1, 1, tzinfo=UTC)
    assistant_time = datetime(2026, 1, 2, tzinfo=UTC)
    messages = [
        Message(
            id=UUID(int=1),
            role="user",
            content="hello",
            created_at=user_time,
        ),
        Message(
            id=UUID(int=2),
            role="assistant",
            content="hi there",
            created_at=assistant_time,
        ),
    ]

    history = build_message_history(messages)

    assert len(history) == 2
    assert isinstance(history[0], ModelRequest)
    assert isinstance(history[0].parts[0], UserPromptPart)
    assert history[0].parts[0].content == "hello"
    assert history[0].timestamp == user_time
    assert isinstance(history[1], ModelResponse)
    assert isinstance(history[1].parts[0], TextPart)
    assert history[1].parts[0].content == "hi there"
    assert history[1].timestamp == assistant_time
