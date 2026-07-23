from datetime import UTC, datetime
from uuid import UUID

from pydantic_ai import ModelRequest, ModelResponse, TextPart, UserPromptPart
import pytest

from app.agent import build_message_history
from app.database.models import ModelMessageRecord
from app.model_history import serialize_model_messages


pytestmark = pytest.mark.unit


def test_build_message_history_restores_canonical_database_records() -> None:
    user_time = datetime(2026, 1, 1, tzinfo=UTC)
    assistant_time = datetime(2026, 1, 2, tzinfo=UTC)
    canonical_messages = [
        ModelRequest(
            parts=[UserPromptPart("hello", timestamp=user_time)],
            timestamp=user_time,
        ),
        ModelResponse(
            parts=[TextPart("hi there")],
            timestamp=assistant_time,
        ),
    ]
    records = [
        ModelMessageRecord(
            id=UUID(int=sequence + 1),
            sequence=sequence,
            payload=payload,
        )
        for sequence, payload in enumerate(serialize_model_messages(canonical_messages))
    ]

    history = build_message_history(records)

    assert len(history) == 2
    assert isinstance(history[0], ModelRequest)
    assert isinstance(history[0].parts[0], UserPromptPart)
    assert history[0].parts[0].content == "hello"
    assert history[0].timestamp == user_time
    assert isinstance(history[1], ModelResponse)
    assert isinstance(history[1].parts[0], TextPart)
    assert history[1].parts[0].content == "hi there"
    assert history[1].timestamp == assistant_time
