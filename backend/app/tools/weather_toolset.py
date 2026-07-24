import os
from collections.abc import Callable, Mapping
from contextlib import AsyncExitStack
from pathlib import Path
import sys
from typing import Any

from fastmcp.client.transports import StdioTransport
from pydantic_ai.mcp import MCPToolset

from app.config import load_weather_settings
from app.tools.mcp_metrics import record_mcp_tool_call
from app.tools.response_guidance import ToolResponseGuidanceToolset
from app.tools.runtime import ActiveAgentTools, ToolsetRegistration


WEATHER_INIT_TIMEOUT_SECONDS = 10.0
WEATHER_READ_TIMEOUT_SECONDS = 10.0
BACKEND_ROOT = Path(__file__).resolve().parents[2]
WEATHER_RESPONSE_INSTRUCTIONS = """
Use the weather data to answer the user's request directly. Do not unnecessarily expose
implementation-specific field names, numeric codes, raw JSON, identifiers, or debug details.
Use current conditions only for the present, and use today's forecast for questions about
later today or rain. Do not infer a forecast from current conditions. Separate facts observed
in the data from any interpretation or advice.
""".strip()


def weather_registration(environment: Mapping[str, str]) -> ToolsetRegistration:
    async def activate(stack: AsyncExitStack) -> ActiveAgentTools:
        return await open_weather_toolset(environment, stack=stack)

    return ToolsetRegistration(name="weather", activate=activate)


async def open_weather_toolset(
    environment: Mapping[str, str],
    *,
    stack: AsyncExitStack,
    toolset_factory: Callable[..., Any] = MCPToolset,
) -> ActiveAgentTools:
    """Start the local weather MCP server and expose its MCP toolset to the agent."""
    load_weather_settings(environment)
    transport = StdioTransport(
        command=sys.executable,
        args=["-m", "app.tools.weather_server"],
        cwd=str(BACKEND_ROOT),
        env={**os.environ, **environment},
    )
    toolset = await stack.enter_async_context(
        toolset_factory(
            transport,
            include_instructions=False,
            init_timeout=WEATHER_INIT_TIMEOUT_SECONDS,
            read_timeout=WEATHER_READ_TIMEOUT_SECONDS,
            process_tool_call=record_mcp_tool_call,
        )
    )
    return ActiveAgentTools(
        toolsets=(
            ToolResponseGuidanceToolset(
                wrapped=toolset,
                response_guidance_by_tool_name={
                    "get_current_weather": WEATHER_RESPONSE_INSTRUCTIONS,
                },
            ),
        )
    )
