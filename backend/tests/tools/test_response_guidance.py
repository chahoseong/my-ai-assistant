from typing import Any, cast

import pytest
from pydantic_ai import RunContext
from pydantic_ai.messages import InstructionPart
from pydantic_ai.toolsets import AbstractToolset
from pydantic_ai.toolsets.abstract import ToolsetTool

from app.tools.response_guidance import ToolResponseGuidanceToolset


pytestmark = pytest.mark.unit


class StubToolset(AbstractToolset[Any]):
    @property
    def id(self) -> str | None:
        return None

    async def get_tools(self, ctx: RunContext[Any]) -> dict[str, ToolsetTool[Any]]:
        del ctx
        return {}

    async def call_tool(
        self,
        name: str,
        tool_args: dict[str, Any],
        ctx: RunContext[Any],
        tool: ToolsetTool[Any],
    ) -> Any:
        del name, tool_args, ctx, tool
        return {"temperature_celsius": 25.9, "weather_code": 2}


@pytest.mark.asyncio
async def test_tool_response_guidance_is_added_only_after_its_tool_returns() -> None:
    guidance = "Use weather data to answer the user without exposing internal fields."
    toolset = ToolResponseGuidanceToolset(
        wrapped=StubToolset(),
        response_guidance_by_tool_name={"get_current_weather": guidance},
    )
    context = cast(RunContext[Any], object())

    run_toolset = await toolset.for_run(context)

    assert await run_toolset.get_instructions(context) is None

    result = await run_toolset.call_tool(
        "get_current_weather", {}, context, cast(ToolsetTool[Any], object())
    )

    assert result == {"temperature_celsius": 25.9, "weather_code": 2}
    assert await run_toolset.get_instructions(context) == InstructionPart(
        guidance, dynamic=True
    )


@pytest.mark.asyncio
async def test_tool_response_guidance_does_not_apply_to_another_tool() -> None:
    toolset = ToolResponseGuidanceToolset(
        wrapped=StubToolset(),
        response_guidance_by_tool_name={"get_current_weather": "weather guidance"},
    )
    context = cast(RunContext[Any], object())

    run_toolset = await toolset.for_run(context)
    await run_toolset.call_tool(
        "unrelated_tool", {}, context, cast(ToolsetTool[Any], object())
    )

    assert await run_toolset.get_instructions(context) is None


@pytest.mark.asyncio
async def test_tool_response_guidance_is_isolated_to_the_current_agent_run() -> None:
    toolset = ToolResponseGuidanceToolset(
        wrapped=StubToolset(),
        response_guidance_by_tool_name={"get_current_weather": "weather guidance"},
    )
    context = cast(RunContext[Any], object())

    first_run = await toolset.for_run(context)
    await first_run.call_tool(
        "get_current_weather", {}, context, cast(ToolsetTool[Any], object())
    )
    second_run = await toolset.for_run(context)

    assert await first_run.get_instructions(context) == InstructionPart(
        "weather guidance", dynamic=True
    )
    assert await second_run.get_instructions(context) is None
