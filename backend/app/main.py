from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI
from prometheus_client import make_asgi_app

from app.agent import (
    create_agent,
    load_llama_settings,
)
from app.auth.dependencies import get_auth_settings
from app.database.dependencies import dispose_database, get_database
from app.observability.logging import configure_observability
from app.observability.metrics import METRICS_PATH
from app.observability.middleware import RequestObservabilityMiddleware
from app.routers.conversations import router as conversations_router
from app.routers.chat import router as chat_router
from app.routers.messages import router as messages_router
from app.routers.auth import router as auth_router


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    get_auth_settings()
    get_database()
    try:
        yield
    finally:
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


app = create_app()
agent = create_agent(load_llama_settings())
