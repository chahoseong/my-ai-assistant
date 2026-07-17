import logging
from collections.abc import AsyncIterator, Sequence

from fastapi import FastAPI
from pydantic import BaseModel, Field
from pydantic_ai import ModelMessage
from sse_starlette import EventSourceResponse

from app.agent import (
    create_agent,
    load_llama_settings,
)
from app.routers.conversations import router as conversations_router
from app.routers.chat import router as chat_router
from app.routers.messages import router as messages_router


app = FastAPI()
app.include_router(conversations_router, prefix="/api/conversations")
app.include_router(messages_router, prefix="/api/conversations")
app.include_router(chat_router, prefix="/api/conversations")
logger = logging.getLogger("app")

STREAM_ERROR_MESSAGE = "Unable to generate a response."


def configure_logger() -> None:
    if not any(type(handler) is logging.StreamHandler for handler in logger.handlers):
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)s %(name)s %(message)s"))
        logger.addHandler(handler)

    logger.setLevel(logging.INFO)
    logger.propagate = False


configure_logger()


agent = create_agent(load_llama_settings())


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8_000)


async def stream_response(
    message: str,
    message_history: Sequence[ModelMessage] | None = None,
) -> AsyncIterator[dict[str, str]]:
    try:
        if message_history:
            stream = agent.run_stream(message, message_history=message_history)
        else:
            stream = agent.run_stream(message)

        async with stream as result:
            async for token in result.stream_text(delta=True):
                yield {"data": token}
    except Exception:
        logger.exception("chat_stream_failed", extra={"event": "chat_stream_failed"})
        yield {"event": "error", "data": STREAM_ERROR_MESSAGE}


@app.post("/api/chat")
async def chat(request: ChatRequest) -> EventSourceResponse:
    return EventSourceResponse(stream_response(request.message))
