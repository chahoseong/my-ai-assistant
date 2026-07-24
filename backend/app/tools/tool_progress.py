"""Resolve tool-owned, user-safe progress messages.

Tools may opt in through MCP metadata.  This module deliberately does not know
any individual tool name: adding a tool therefore does not require changing the
chat integration or the browser contract.
"""

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.toolsets import AbstractToolset
from pydantic_ai.toolsets.abstract import ToolsetTool
from pydantic_ai.toolsets.wrapper import WrapperToolset


_MAX_SELECTION_MESSAGE_LENGTH = 120
_captured_selection_messages: ContextVar[dict[str, str] | None] = ContextVar(
    "captured_selection_messages", default=None
)


def selection_message_from_metadata(metadata: object) -> str | None:
    """Return the validated opt-in progress message from MCP tool metadata."""
    if not isinstance(metadata, Mapping):
        return None
    meta = metadata.get("meta")
    if not isinstance(meta, Mapping):
        return None
    progress = meta.get("my_ai_assistant")
    if not isinstance(progress, Mapping):
        return None
    message = progress.get("selection_message")
    if not isinstance(message, str):
        return None

    message = message.strip()
    if not 0 < len(message) <= _MAX_SELECTION_MESSAGE_LENGTH:
        return None
    return message


@contextmanager
def capture_tool_selection_messages() -> Iterator[dict[str, str]]:
    """Capture the opt-in messages discovered while preparing one agent run."""
    messages: dict[str, str] = {}
    token = _captured_selection_messages.set(messages)
    try:
        yield messages
    finally:
        _captured_selection_messages.reset(token)


@dataclass
class ToolProgressToolset(WrapperToolset[Any]):
    """Collect safe tool progress messages without naming any concrete tool."""

    _selection_messages: dict[str, str] = field(default_factory=dict, init=False)

    @property
    def selection_messages(self) -> Mapping[str, str]:
        return self._selection_messages

    async def for_run(self, ctx: RunContext[Any]) -> AbstractToolset[Any]:
        return ToolProgressToolset(wrapped=await self.wrapped.for_run(ctx))

    async def for_run_step(self, ctx: RunContext[Any]) -> AbstractToolset[Any]:
        wrapped = await self.wrapped.for_run_step(ctx)
        if wrapped is self.wrapped:
            return self

        toolset = ToolProgressToolset(wrapped=wrapped)
        toolset._selection_messages = self._selection_messages.copy()
        return toolset

    async def get_tools(
        self, ctx: RunContext[Any]
    ) -> dict[str, ToolsetTool[Any]]:
        tools = await super().get_tools(ctx)
        self._selection_messages = {
            name: message
            for name, tool in tools.items()
            if (message := selection_message_from_metadata(tool.tool_def.metadata))
            is not None
        }
        captured_messages = _captured_selection_messages.get()
        if captured_messages is not None:
            captured_messages.update(self._selection_messages)
        return tools
