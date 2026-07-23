from contextlib import AsyncExitStack
from typing import Any, cast

import pytest
from pydantic_ai.toolsets import AbstractToolset

from app.tools.registrations import default_toolset_registrations
from app.tools.runtime import ActiveAgentTools, activate_toolset_registrations
import app.tools.toolsets
import app.tools.weather_toolset


pytestmark = pytest.mark.unit


def test_default_toolset_registrations_include_weather_and_opgg() -> None:
    registrations = default_toolset_registrations({})

    assert tuple(registration.name for registration in registrations) == (
        "weather",
        "opgg_tft",
    )


class FakeOpggTools:
    async def tft_describe_meta_decks(self) -> dict[str, object]:
        return {"record_count": 0}

    async def tft_query_meta_decks(self) -> dict[str, object]:
        return {"records": []}


@pytest.mark.asyncio
async def test_weather_startup_failure_leaves_opgg_tools_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def unavailable_weather(*_: object, **__: object) -> ActiveAgentTools:
        raise RuntimeError("weather unavailable")

    opgg_tools = FakeOpggTools()

    async def available_opgg(*_: object, **__: object) -> FakeOpggTools:
        return opgg_tools

    monkeypatch.setattr(app.tools.weather_toolset, "open_weather_toolset", unavailable_weather)
    monkeypatch.setattr(app.tools.toolsets, "open_opgg_tft_tools", available_opgg)

    async with AsyncExitStack() as stack:
        active_tools = await activate_toolset_registrations(
            default_toolset_registrations({}), stack=stack
        )

    assert tuple(tool.__name__ for tool in active_tools.functions) == (
        "tft_describe_meta_decks",
        "tft_query_meta_decks",
    )
    assert active_tools.toolsets == ()


@pytest.mark.asyncio
async def test_opgg_startup_failure_leaves_weather_toolset_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    weather_toolset = cast(AbstractToolset[Any], object())

    async def available_weather(*_: object, **__: object) -> ActiveAgentTools:
        return ActiveAgentTools(toolsets=(weather_toolset,))

    async def unavailable_opgg(*_: object, **__: object) -> FakeOpggTools:
        raise RuntimeError("OP.GG unavailable")

    monkeypatch.setattr(app.tools.weather_toolset, "open_weather_toolset", available_weather)
    monkeypatch.setattr(app.tools.toolsets, "open_opgg_tft_tools", unavailable_opgg)

    async with AsyncExitStack() as stack:
        active_tools = await activate_toolset_registrations(
            default_toolset_registrations({}), stack=stack
        )

    assert active_tools.functions == ()
    assert active_tools.toolsets == (weather_toolset,)
