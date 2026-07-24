import asyncio
from collections.abc import Awaitable, Callable, Sequence
from contextlib import AsyncExitStack
from dataclasses import dataclass
from typing import Any

from pydantic_ai.toolsets import AbstractToolset

from app.observability.logging import get_logger


logger = get_logger(__name__)


@dataclass(frozen=True)
class ActiveAgentTools:
    """The model-facing tools that one successfully activated integration provides."""

    functions: tuple[Callable[..., Any], ...] = ()
    toolsets: tuple[AbstractToolset[Any], ...] = ()


@dataclass(frozen=True)
class ToolsetRegistration:
    """One independently activated external-tool integration."""

    name: str
    activate: Callable[[AsyncExitStack], Awaitable[ActiveAgentTools]]


async def activate_toolset_registrations(
    registrations: Sequence[ToolsetRegistration],
    *,
    stack: AsyncExitStack,
    report_availability: Callable[[str, bool], None] | None = None,
) -> ActiveAgentTools:
    """Activate each registration independently and retain only successful tools."""
    functions: list[Callable[..., Any]] = []
    toolsets: list[AbstractToolset[Any]] = []

    for registration in registrations:
        registration_stack = AsyncExitStack()
        try:
            active_tools = await registration.activate(registration_stack)
        except asyncio.CancelledError:
            await registration_stack.aclose()
            raise
        except Exception as error:
            await registration_stack.aclose()
            logger.warning(
                "toolset_startup_failed",
                toolset=registration.name,
                error_type=type(error).__name__,
            )
            if report_availability is not None:
                report_availability(registration.name, False)
        else:
            stack.push_async_callback(registration_stack.aclose)
            functions.extend(active_tools.functions)
            toolsets.extend(active_tools.toolsets)
            if report_availability is not None:
                report_availability(registration.name, True)

    return ActiveAgentTools(functions=tuple(functions), toolsets=tuple(toolsets))
