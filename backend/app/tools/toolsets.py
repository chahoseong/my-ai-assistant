from collections.abc import Callable, Mapping
from contextlib import AsyncExitStack
from typing import Any, cast

from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport

from app.config import OpggTftSettings, load_opgg_tft_settings
from app.tools.runtime import ActiveAgentTools, ToolsetRegistration
from app.tools.tft_meta_deck_tools import TftMetaDeckTools
from app.tools.tft_meta_decks import (
    TftMetaDeckMcpClient,
    TftMetaDeckSnapshotCache,
    fetch_opgg_tft_meta_decks,
)

OPGG_INIT_TIMEOUT_SECONDS = 10.0
OPGG_CALL_TIMEOUT_SECONDS = 10.0


def opgg_tft_registration(environment: Mapping[str, str]) -> ToolsetRegistration:
    async def activate(stack: AsyncExitStack) -> ActiveAgentTools:
        settings = load_opgg_tft_settings(environment)
        tools = await open_opgg_tft_tools(settings, stack=stack)
        return ActiveAgentTools(
            functions=(
                tools.tft_describe_meta_decks,
                tools.tft_query_meta_decks,
            )
        )

    return ToolsetRegistration(name="opgg_tft", activate=activate)


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
