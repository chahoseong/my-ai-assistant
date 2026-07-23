from time import monotonic
from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.mcp import CallToolFunc, ToolResult

from app.observability.metrics import record_agent_tool_call


async def record_mcp_tool_call(
    _: RunContext[Any],
    call_tool: CallToolFunc,
    tool_name: str,
    tool_args: dict[str, Any],
) -> ToolResult:
    """Record bounded MCP tool metrics without retaining tool arguments or results."""
    started_at = monotonic()
    outcome = "failed"
    try:
        result = await call_tool(tool_name, tool_args)
    except TimeoutError:
        outcome = "timeout"
        raise
    else:
        outcome = "success"
        return result
    finally:
        record_agent_tool_call(
            tool_name=tool_name,
            outcome=outcome,
            duration_seconds=monotonic() - started_at,
        )
