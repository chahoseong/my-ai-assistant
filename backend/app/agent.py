import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from pydantic_ai import (
    Agent,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    UserPromptPart,
)
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from app.database.models import Message


DEFAULT_MODEL = "google/gemma-4-E4B-it-qat-q4_0-gguf"
DEFAULT_BASE_URL = "http://127.0.0.1:8080/v1"
DEFAULT_API_KEY = "llama.cpp"


@dataclass(frozen=True)
class LlamaSettings:
    model: str
    base_url: str
    api_key: str


def load_llama_settings(env: Mapping[str, str] | None = None) -> LlamaSettings:
    environment = os.environ if env is None else env
    return LlamaSettings(
        model=environment.get("LLAMA_MODEL", DEFAULT_MODEL),
        base_url=environment.get("LLAMA_BASE_URL", DEFAULT_BASE_URL),
        api_key=environment.get("LLAMA_API_KEY", DEFAULT_API_KEY),
    )


def create_agent(settings: LlamaSettings) -> Agent:
    model = OpenAIChatModel(
        settings.model,
        provider=OpenAIProvider(
            base_url=settings.base_url,
            api_key=settings.api_key,
        ),
    )
    return Agent(model)


def build_message_history(messages: Sequence[Message]) -> list[ModelMessage]:
    history: list[ModelMessage] = []

    for message in messages:
        if message.role == "user":
            history.append(
                ModelRequest(
                    parts=[
                        UserPromptPart(
                            content=message.content,
                            timestamp=message.created_at,
                        )
                    ],
                    timestamp=message.created_at,
                )
            )
        elif message.role == "assistant":
            history.append(
                ModelResponse(
                    parts=[TextPart(content=message.content)],
                    timestamp=message.created_at,
                )
            )
        else:
            raise ValueError(f"Unsupported message role: {message.role}")

    return history
