import os
from contextlib import AsyncExitStack, asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI
from prometheus_client import make_asgi_app

from app.agent import (
    create_agent,
    load_llama_settings,
)
from app.auth.dependencies import get_auth_settings
from app.config import load_opgg_tft_settings
from app.database.dependencies import dispose_database, get_database
from app.llama import LlamaContextLimitCache
from app.observability.logging import configure_observability, get_logger
from app.observability.metrics import METRICS_PATH
from app.observability.middleware import RequestObservabilityMiddleware
from app.routers.conversations import router as conversations_router
from app.routers.chat import router as chat_router
from app.routers.messages import router as messages_router
from app.routers.auth import router as auth_router
from app.tools.toolsets import open_opgg_tft_tools


logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    global agent
    get_auth_settings()
    get_database()
    tool_stack = AsyncExitStack()
    try:
        tool_functions = []
        opgg_settings = load_opgg_tft_settings(os.environ)
        try:
            tft_tools = await open_opgg_tft_tools(
                settings=opgg_settings,
                stack=tool_stack,
            )
        except Exception as error:
            logger.warning(
                "toolset_startup_failed",
                toolset="opgg_tft",
                error_type=type(error).__name__,
            )
        else:
            tool_functions = [
                tft_tools.tft_describe_meta_decks,
                tft_tools.tft_query_meta_decks,
            ]
        agent = create_agent(llama_settings, tools=tool_functions)
        yield
    finally:
        await tool_stack.aclose()
        agent = create_agent(llama_settings)
        await dispose_database()


configure_observability()


def create_app() -> FastAPI:
    app = FastAPI(lifespan=lifespan)
    app.add_middleware(RequestObservabilityMiddleware)
    app.mount(METRICS_PATH, make_asgi_app())
    app.include_router(auth_router)
    app.include_router(conversations_router)
    app.include_router(messages_router)
    app.include_router(chat_router)
    return app


llama_settings = load_llama_settings()
app = create_app()
agent = create_agent(llama_settings)
context_limit_cache = LlamaContextLimitCache(llama_settings.base_url)
