from collections.abc import Sequence
from typing import cast

from pydantic_ai.messages import ModelMessage, ModelMessagesTypeAdapter


ModelMessagePayload = dict[str, object]


def serialize_model_messages(
    messages: Sequence[ModelMessage],
) -> list[ModelMessagePayload]:
    """Convert Pydantic AI history to JSON-compatible database payloads."""
    payloads = ModelMessagesTypeAdapter.dump_python(list(messages), mode="json")
    return cast(list[ModelMessagePayload], payloads)


def deserialize_model_messages(
    payloads: Sequence[ModelMessagePayload],
) -> list[ModelMessage]:
    """Restore Pydantic AI history from database payloads."""
    return ModelMessagesTypeAdapter.validate_python(list(payloads))
