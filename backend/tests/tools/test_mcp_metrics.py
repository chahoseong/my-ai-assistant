from typing import Any, cast

import pytest
from pydantic_ai import RunContext
from pydantic_ai.mcp import CallToolFunc

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
async def test_mcp_tool_callback_records_a_timeout_and_reraises_it() -> None:
    async def call_tool(
        _: str, __: dict[str, Any], *, metadata: dict[str, Any] | None = None
    ) -> object:
        raise TimeoutError("upstream timeout")

    before = tool_call_count(outcome="timeout")

    with pytest.raises(TimeoutError, match="upstream timeout"):
        await record_mcp_tool_call(
            cast(RunContext[Any], object()),
            cast(CallToolFunc, call_tool),
            "get_current_weather",
            {"city": "서울"},
        )

    assert tool_call_count(outcome="timeout") == before + 1
