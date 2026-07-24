from http import HTTPStatus
from types import SimpleNamespace
from typing import Any, cast

import pytest
from fastmcp.client.transports import StdioTransport
from mcp.shared.exceptions import McpError
from mcp.types import ErrorData
from pydantic_ai import ModelRetry, RunContext
from pydantic_ai.mcp import CallToolFunc, MCPToolset
from pydantic_ai.models.test import TestModel
from pydantic_ai.toolsets.abstract import ToolsetTool
from pydantic_ai.usage import RunUsage

from app.observability.metrics import AGENT_TOOL_CALLS_TOTAL
from app.tools.mcp_metrics import record_mcp_tool_call


pytestmark = pytest.mark.unit


def tool_call_count(*, outcome: str) -> float:
    return AGENT_TOOL_CALLS_TOTAL.labels(
        tool_name="get_current_weather", outcome=outcome
    )._value.get()


@pytest.mark.asyncio
async def test_mcp_tool_callback_records_a_successful_model_facing_tool_call() -> None:
    async def call_tool(
        name: str, args: dict[str, Any], *, metadata: dict[str, Any] | None = None
    ) -> dict[str, str]:
        assert name == "get_current_weather"
        assert args == {"city": "서울"}
        assert metadata is None
        return {"location": "서울특별시"}

    before = tool_call_count(outcome="success")

    result = await record_mcp_tool_call(
        cast(RunContext[Any], object()),
        cast(CallToolFunc, call_tool),
        "get_current_weather",
        {"city": "서울"},
    )

    assert result == {"location": "서울특별시"}
    assert tool_call_count(outcome="success") == before + 1


@pytest.mark.asyncio
async def test_mcp_tool_callback_records_a_mcp_request_timeout_as_a_model_retryable_error() -> None:
    async def call_tool(
        _: str, __: dict[str, Any], *, metadata: dict[str, Any] | None = None
    ) -> object:
        raise McpError(
            ErrorData(code=HTTPStatus.REQUEST_TIMEOUT, message="upstream timeout")
        )

    before = tool_call_count(outcome="timeout")
    before_failed = tool_call_count(outcome="failed")

    with pytest.raises(ModelRetry, match="The tool timed out."):
        await record_mcp_tool_call(
            cast(RunContext[Any], object()),
            cast(CallToolFunc, call_tool),
            "get_current_weather",
            {"city": "서울"},
        )

    assert tool_call_count(outcome="timeout") == before + 1
    assert tool_call_count(outcome="failed") == before_failed


@pytest.mark.asyncio
async def test_mcp_tool_callback_preserves_a_bare_timeout_as_a_model_retryable_error() -> None:
    async def call_tool(
        _: str, __: dict[str, Any], *, metadata: dict[str, Any] | None = None
    ) -> object:
        raise TimeoutError("upstream timeout")

    before = tool_call_count(outcome="timeout")
    before_failed = tool_call_count(outcome="failed")

    with pytest.raises(ModelRetry, match="The tool timed out."):
        await record_mcp_tool_call(
            cast(RunContext[Any], object()),
            cast(CallToolFunc, call_tool),
            "get_current_weather",
            {"city": "서울"},
        )

    assert tool_call_count(outcome="timeout") == before + 1
    assert tool_call_count(outcome="failed") == before_failed


@pytest.mark.asyncio
async def test_mcp_toolset_exposes_a_timeout_callback_as_model_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    toolset = MCPToolset(
        StdioTransport("unused", []),
        process_tool_call=record_mcp_tool_call,
    )

    async def direct_call_tool(
        _: str, __: dict[str, Any], *, use_task: bool = False
    ) -> object:
        del use_task
        raise McpError(
            ErrorData(code=HTTPStatus.REQUEST_TIMEOUT, message="upstream timeout")
        )

    monkeypatch.setattr(toolset, "direct_call_tool", direct_call_tool)
    context = RunContext(
        deps=None,
        model=TestModel(),
        usage=RunUsage(),
        max_retries=1,
    )
    tool = cast(
        ToolsetTool[Any],
        SimpleNamespace(tool_def=SimpleNamespace(metadata=None)),
    )

    with pytest.raises(ModelRetry, match="The tool timed out."):
        await toolset.call_tool("get_current_weather", {}, context, tool)


@pytest.mark.asyncio
async def test_mcp_tool_callback_preserves_a_non_timeout_mcp_error_as_failed() -> None:
    error = McpError(ErrorData(code=500, message="upstream failure"))

    async def call_tool(
        _: str, __: dict[str, Any], *, metadata: dict[str, Any] | None = None
    ) -> object:
        raise error

    before = tool_call_count(outcome="failed")
    before_timeout = tool_call_count(outcome="timeout")

    with pytest.raises(McpError) as raised:
        await record_mcp_tool_call(
            cast(RunContext[Any], object()),
            cast(CallToolFunc, call_tool),
            "get_current_weather",
            {"city": "서울"},
        )

    assert raised.value is error
    assert tool_call_count(outcome="failed") == before + 1
    assert tool_call_count(outcome="timeout") == before_timeout
