from collections.abc import AsyncIterator

from fastapi import FastAPI
from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from sse_starlette import EventSourceResponse


app = FastAPI()
model = OpenAIChatModel(
    "gemma-4-E4B-it-qat-q4_0",
    provider=OpenAIProvider(
        base_url="http://127.0.0.1:8080/v1",
        api_key="llama.cpp",
    ),
)
agent = Agent(model)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8_000)


async def stream_response(message: str) -> AsyncIterator[dict[str, str]]:
    async with agent.run_stream(message) as result:
        async for token in result.stream_text(delta=True):
            yield {"data": token}


@app.post("/api/chat")
async def chat(request: ChatRequest) -> EventSourceResponse:
    return EventSourceResponse(stream_response(request.message))
