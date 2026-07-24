from datetime import UTC, datetime

from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    ThinkingPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
import pytest

from app.model_history import deserialize_model_messages, serialize_model_messages


pytestmark = pytest.mark.unit


def test_model_message_payloads_round_trip_all_required_part_types() -> None:
    timestamp = datetime(2026, 7, 23, tzinfo=UTC)
    history = [
        ModelRequest(
            parts=[UserPromptPart("서울 날씨와 환율을 알려줘", timestamp=timestamp)],
            timestamp=timestamp,
        ),
        ModelResponse(
            parts=[
                ThinkingPart("도구로 최신 정보를 조회한다."),
                ToolCallPart(
                    tool_name="get_weather",
                    args={"city": "Seoul"},
                    tool_call_id="weather-call",
                ),
                ToolCallPart(
                    tool_name="get_exchange_rate",
                    args={},
                    tool_call_id="exchange-rate-call",
                ),
            ],
            model_name="test-model",
            timestamp=timestamp,
        ),
        ModelRequest(
            parts=[
                ToolReturnPart(
                    tool_name="get_weather",
                    content={"temperature_c": 25},
                    tool_call_id="weather-call",
                    timestamp=timestamp,
                ),
                RetryPromptPart(
                    "환율 도구 결과를 더 간결하게 설명해줘.",
                    tool_name="get_exchange_rate",
                    tool_call_id="exchange-rate-call",
                    timestamp=timestamp,
                ),
            ],
            timestamp=timestamp,
        ),
    ]

    payloads = serialize_model_messages(history)
    restored = deserialize_model_messages(payloads)

    assert serialize_model_messages(restored) == payloads
    assert isinstance(restored[1], ModelResponse)
    assert isinstance(restored[1].parts[0], ThinkingPart)
    tool_calls = [part for part in restored[1].parts if isinstance(part, ToolCallPart)]
    assert [part.tool_call_id for part in tool_calls] == [
        "weather-call",
        "exchange-rate-call",
    ]
    assert isinstance(restored[2], ModelRequest)
    assert isinstance(restored[2].parts[0], ToolReturnPart)
    assert isinstance(restored[2].parts[1], RetryPromptPart)
