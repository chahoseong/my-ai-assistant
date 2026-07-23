from collections.abc import Callable
from contextlib import AsyncExitStack
from typing import Any, cast

from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport

from app.config import OpggTftSettings
from app.tools.tft_meta_deck_tools import TftMetaDeckTools
from app.tools.tft_meta_decks import (
    TftMetaDeckMcpClient,
    TftMetaDeckSnapshotCache,
    fetch_opgg_tft_meta_decks,
)

OPGG_INIT_TIMEOUT_SECONDS = 10.0
OPGG_CALL_TIMEOUT_SECONDS = 10.0


async def open_opgg_tft_tools(
    settings: OpggTftSettings,
    *,
    stack: AsyncExitStack,
    client_factory: Callable[..., Any] = Client,
) -> TftMetaDeckTools:
    """Open the private OP.GG client; only local function tools reach the agent."""
    client = await stack.enter_async_context(
        client_factory(
            StreamableHttpTransport(settings.mcp_url),
            timeout=OPGG_CALL_TIMEOUT_SECONDS,
            init_timeout=OPGG_INIT_TIMEOUT_SECONDS,
        )
    )
    mcp_client = cast(TftMetaDeckMcpClient, client)
    snapshot_cache = TftMetaDeckSnapshotCache(
        fetch_payload=lambda: fetch_opgg_tft_meta_decks(mcp_client),
        ttl_seconds=settings.cache_ttl_seconds,
    )
    return TftMetaDeckTools(snapshot_cache)
