import pytest

from app.web.schemas import ToolSelectedPayload, StreamDonePayload, StreamUsagePayload


pytestmark = pytest.mark.unit


def test_stream_done_payload_serializes_usage_contract() -> None:
    payload = StreamDonePayload(
        usage=StreamUsagePayload(
            input_tokens=37,
            output_tokens=11,
            context_limit=8192,
        )
    )

    assert payload.model_dump() == {
        "usage": {
            "input_tokens": 37,
            "output_tokens": 11,
            "context_limit": 8192,
        }
    }


def test_tool_selected_payload_serializes_only_the_safe_display_message() -> None:
    payload = ToolSelectedPayload(message="현재 날씨를 확인하고 있어요.")

    assert payload.model_dump() == {"message": "현재 날씨를 확인하고 있어요."}
