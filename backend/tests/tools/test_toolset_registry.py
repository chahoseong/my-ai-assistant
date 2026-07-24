from contextlib import AsyncExitStack

import pytest

from app.tools.runtime import (
    ActiveAgentTools,
    ToolsetRegistration,
    activate_toolset_registrations,
)


pytestmark = pytest.mark.unit


class RecordingResource:
    def __init__(self) -> None:
        self.entered = False
        self.closed = False

    async def __aenter__(self) -> "RecordingResource":
        self.entered = True
        return self

    async def __aexit__(self, *_: object) -> None:
        self.closed = True


async def successful_tool() -> str:
    return "ok"


@pytest.mark.asyncio
async def test_registration_failure_closes_its_resources_and_keeps_later_tools_active() -> None:
    failed_resource = RecordingResource()
    successful_resource = RecordingResource()
    states: list[tuple[str, bool]] = []

    async def fail_after_acquiring_resource(stack: AsyncExitStack) -> ActiveAgentTools:
        await stack.enter_async_context(failed_resource)
        raise RuntimeError("unavailable")

    async def activate_successful_tool(stack: AsyncExitStack) -> ActiveAgentTools:
        await stack.enter_async_context(successful_resource)
        return ActiveAgentTools(functions=(successful_tool,))

    async with AsyncExitStack() as app_stack:
        active_tools = await activate_toolset_registrations(
            (
                ToolsetRegistration("failed", fail_after_acquiring_resource),
                ToolsetRegistration("successful", activate_successful_tool),
            ),
            stack=app_stack,
            report_availability=lambda name, is_up: states.append((name, is_up)),
        )

        assert failed_resource.entered is True
        assert failed_resource.closed is True
        assert successful_resource.entered is True
        assert successful_resource.closed is False
        assert active_tools.functions == (successful_tool,)
        assert states == [("failed", False), ("successful", True)]

    assert successful_resource.closed is True
