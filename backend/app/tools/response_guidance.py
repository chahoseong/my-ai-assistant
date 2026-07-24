from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.messages import InstructionPart
from pydantic_ai.toolsets import AbstractToolset
from pydantic_ai.toolsets.abstract import ToolsetTool
from pydantic_ai.toolsets.wrapper import WrapperToolset


@dataclass
class ToolResponseGuidanceToolset(WrapperToolset[Any]):
    """Add each configured tool's response guidance after it returns successfully."""

    response_guidance_by_tool_name: Mapping[str, str]
    _active_guidance: list[str] = field(default_factory=list, init=False, repr=False)

    async def for_run(self, ctx: RunContext[Any]) -> AbstractToolset[Any]:
        return ToolResponseGuidanceToolset(
            wrapped=await self.wrapped.for_run(ctx),
            response_guidance_by_tool_name=self.response_guidance_by_tool_name,
        )

    async def for_run_step(self, ctx: RunContext[Any]) -> AbstractToolset[Any]:
        wrapped = await self.wrapped.for_run_step(ctx)
        if wrapped is self.wrapped:
            return self

        toolset = ToolResponseGuidanceToolset(
            wrapped=wrapped,
            response_guidance_by_tool_name=self.response_guidance_by_tool_name,
        )
        toolset._active_guidance = self._active_guidance.copy()
        return toolset

    async def get_instructions(
        self, ctx: RunContext[Any]
    ) -> str | InstructionPart | Sequence[str | InstructionPart] | None:
        inherited = await super().get_instructions(ctx)
        guidance = [
            InstructionPart(content=instruction, dynamic=True)
            for instruction in self._active_guidance
        ]
        if inherited is None:
            return guidance[0] if len(guidance) == 1 else guidance or None
        if not guidance:
            return inherited
        if isinstance(inherited, str | InstructionPart):
            return [inherited, *guidance]
        return [*inherited, *guidance]

    async def call_tool(
        self,
        name: str,
        tool_args: dict[str, Any],
        ctx: RunContext[Any],
        tool: ToolsetTool[Any],
    ) -> Any:
        result = await super().call_tool(name, tool_args, ctx, tool)
        guidance = self.response_guidance_by_tool_name.get(name)
        if guidance is not None and guidance not in self._active_guidance:
            self._active_guidance.append(guidance)
        return result
