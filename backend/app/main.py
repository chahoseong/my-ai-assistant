import logging
import os
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass

from fastapi import FastAPI
from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from sse_starlette import EventSourceResponse

from app.routers.conversations import router as conversations_router


app = FastAPI()
app.include_router(conversations_router, prefix="/api/conversations")
logger = logging.getLogger(__name__)

DEFAULT_MODEL = "google/gemma-4-E4B-it-qat-q4_0-gguf"
DEFAULT_BASE_URL = "http://127.0.0.1:8080/v1"
DEFAULT_API_KEY = "llama.cpp"
STREAM_ERROR_MESSAGE = "Unable to generate a response."


def configure_logger() -> None:
    if not any(type(handler) is logging.StreamHandler for handler in logger.handlers):
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)s %(name)s %(message)s"))
        logger.addHandler(handler)

    logger.setLevel(logging.INFO)
    logger.propagate = False


configure_logger()


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


agent = create_agent(load_llama_settings())


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8_000)


async def stream_response(message: str) -> AsyncIterator[dict[str, str]]:
    try:
        async with agent.run_stream(message) as result:
            async for token in result.stream_text(delta=True):
                yield {"data": token}
    except Exception:
        logger.exception("chat_stream_failed", extra={"event": "chat_stream_failed"})
        yield {"event": "error", "data": STREAM_ERROR_MESSAGE}


@app.post("/api/chat")
async def chat(request: ChatRequest) -> EventSourceResponse:
    return EventSourceResponse(stream_response(request.message))
