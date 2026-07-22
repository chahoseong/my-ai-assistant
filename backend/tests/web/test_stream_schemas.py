import pytest

from app.web.schemas import StreamDonePayload, StreamUsagePayload


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
