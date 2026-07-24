import pytest
from pydantic_ai import RunContext, Tool
from pydantic_ai.models.test import TestModel
from pydantic_ai.toolsets.function import FunctionToolset
from pydantic_ai.usage import RunUsage

from app.tools.tool_progress import (
    ToolProgressToolset,
    capture_tool_selection_messages,
    selection_message_from_metadata,
)


pytestmark = pytest.mark.unit


def test_selection_message_accepts_a_trimmed_namespaced_message() -> None:
    metadata = {
        "meta": {
            "my_ai_assistant": {
                "selection_message": "  현재 날씨를 확인하고 있어요.  ",
            }
        }
    }

    assert selection_message_from_metadata(metadata) == "현재 날씨를 확인하고 있어요."


@pytest.mark.parametrize(
    "metadata",
    [
        None,
        {},
        {"meta": {"my_ai_assistant": {"selection_message": ""}}},
        {"meta": {"my_ai_assistant": {"selection_message": "   "}}},
        {"meta": {"my_ai_assistant": {"selection_message": "x" * 121}}},
        {"meta": {"my_ai_assistant": {"selection_message": 1}}},
    ],
)
def test_selection_message_rejects_missing_or_unsafe_metadata(
    metadata: object,
) -> None:
    assert selection_message_from_metadata(metadata) is None


@pytest.mark.asyncio
async def test_toolset_captures_only_opted_in_tool_messages_for_one_run() -> None:
    async def opted_in_tool() -> str:
        return "ok"

    async def unannotated_tool() -> str:
        return "ok"

    toolset = ToolProgressToolset(
        wrapped=FunctionToolset(
            [
                Tool(
                    opted_in_tool,
                    metadata={
                        "meta": {
                            "my_ai_assistant": {
                                "selection_message": "도구를 확인하고 있어요."
                            }
                        }
                    },
                ),
                Tool(unannotated_tool),
            ]
        )
    )
    context = RunContext(
        deps=None,
        model=TestModel(),
        usage=RunUsage(),
        max_retries=1,
    )

    with capture_tool_selection_messages() as captured_messages:
        await toolset.get_tools(context)

    assert dict(toolset.selection_messages) == {
        "opted_in_tool": "도구를 확인하고 있어요."
    }
    assert captured_messages == {"opted_in_tool": "도구를 확인하고 있어요."}
