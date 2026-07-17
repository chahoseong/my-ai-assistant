import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI

from app.agent import (
    create_agent,
    load_llama_settings,
)
from app.dependencies import dispose_database, get_database
from app.routers.conversations import router as conversations_router
from app.routers.chat import router as chat_router
from app.routers.messages import router as messages_router


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    get_database()
    try:
        yield
    finally:
        await dispose_database()


app = FastAPI(lifespan=lifespan)
app.include_router(conversations_router, prefix="/api/conversations")
app.include_router(messages_router, prefix="/api/conversations")
app.include_router(chat_router, prefix="/api/conversations")
logger = logging.getLogger("app")


def configure_logger() -> None:
    if not any(type(handler) is logging.StreamHandler for handler in logger.handlers):
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)s %(name)s %(message)s"))
        logger.addHandler(handler)

    logger.setLevel(logging.INFO)
    logger.propagate = False


configure_logger()


agent = create_agent(load_llama_settings())
