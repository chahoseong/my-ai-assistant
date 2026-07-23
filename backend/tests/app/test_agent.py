from datetime import UTC, datetime
from typing import cast
from uuid import UUID

import app.agent
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


class RecordingAgent:
    def __init__(self, _: object, **kwargs: object) -> None:
        self.tools = cast(list[object], kwargs["tools"])
        self.instructions = cast(str, kwargs["instructions"])


def test_create_agent_receives_only_explicitly_injected_function_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def tft_describe_meta_decks() -> dict[str, object]:
        return {}

    monkeypatch.setattr(app.agent, "Agent", RecordingAgent)

    agent = cast(
        RecordingAgent,
        app.agent.create_agent(
            app.agent.LlamaSettings(
                model="test-model",
                base_url="http://llama.example/v1",
                api_key="test-key",
            ),
            tools=[tft_describe_meta_decks],
        ),
    )

    assert agent.tools == [tft_describe_meta_decks]
    assert "untrusted data" in agent.instructions
