from contextlib import AsyncExitStack
from types import SimpleNamespace
from typing import cast

import pytest
from pydantic_ai.mcp import MCPToolset

from app.config import OpggTftSettings
from app.tools.toolsets import open_opgg_tft_tools
from app.tools.weather_toolset import open_weather_toolset
from app.tools.mcp_metrics import record_mcp_tool_call


pytestmark = pytest.mark.unit


class FakeMcpClient:
    def __init__(self, *, fail_on_enter: bool = False) -> None:
        self.fail_on_enter = fail_on_enter
        self.entered = False
        self.closed = False
        self.calls: list[tuple[str, dict[str, object] | None]] = []

    async def __aenter__(self) -> "FakeMcpClient":
        if self.fail_on_enter:
            raise RuntimeError("OP.GG is unavailable")
        self.entered = True
        return self

    async def __aexit__(self, *_: object) -> None:
        self.closed = True

    async def call_tool(
        self, name: str, arguments: dict[str, object] | None = None
    ) -> object:
        self.calls.append((name, arguments))
        return SimpleNamespace(
            data={
                "data": [],
                "metadata": {"gameStatDateTime": "2026-07-23T12:00:00Z"},
            },
            is_error=False,
        )


class FakeMcpToolset:
    def __init__(self) -> None:
        self.entered = False
        self.closed = False

    async def __aenter__(self) -> "FakeMcpToolset":
        self.entered = True
        return self

    async def __aexit__(self, *_: object) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_opgg_runtime_opens_a_streamable_http_client_and_closes_it_with_its_stack() -> None:
    created: list[FakeMcpClient] = []
    client_options: dict[str, object] = {}

    def client_factory(_: object, **kwargs: object) -> FakeMcpClient:
        client_options.update(kwargs)
        client = FakeMcpClient()
        created.append(client)
        return client

    async with AsyncExitStack() as stack:
        tools = await open_opgg_tft_tools(
            OpggTftSettings(
                mcp_url="https://opgg.example/mcp", cache_ttl_seconds=300.0
            ),
            stack=stack,
            client_factory=client_factory,
        )

        assert (await tools.tft_describe_meta_decks())["record_count"] == 0
        assert created[0].entered is True
        assert created[0].calls == [("tft_list_meta_decks", {})]
        assert client_options == {"timeout": 10.0, "init_timeout": 10.0}

    assert created[0].closed is True


@pytest.mark.asyncio
async def test_opgg_startup_failure_is_isolated_to_its_own_runtime() -> None:
    async with AsyncExitStack() as stack:
        with pytest.raises(RuntimeError, match="OP.GG"):
            await open_opgg_tft_tools(
                OpggTftSettings(
                    mcp_url="https://opgg.example/mcp", cache_ttl_seconds=300.0
                ),
                stack=stack,
                client_factory=lambda _, **__: FakeMcpClient(fail_on_enter=True),
            )

        # The caller keeps control of the lifespan and can still activate other tools.
        assert stack is not None


@pytest.mark.asyncio
async def test_weather_runtime_opens_a_stdio_toolset_and_closes_it_with_its_stack() -> (
    None
):
    created: list[FakeMcpToolset] = []
    received_transport: object | None = None
    toolset_options: dict[str, object] = {}

    def toolset_factory(transport: object, **kwargs: object) -> FakeMcpToolset:
        nonlocal received_transport
        received_transport = transport
        toolset_options.update(kwargs)
        toolset = FakeMcpToolset()
        created.append(toolset)
        return toolset

    environment = {
        "NOMINATIM_USER_AGENT": "my-ai-assistant-test/0.1",
        "NOMINATIM_BASE_URL": "https://nominatim.test",
        "OPEN_METEO_BASE_URL": "https://weather.test",
    }

    async with AsyncExitStack() as stack:
        active_tools = await open_weather_toolset(
            environment,
            stack=stack,
            toolset_factory=toolset_factory,
        )

        assert created[0].entered is True
        assert active_tools.functions == ()
        assert active_tools.toolsets == (created[0],)
        assert toolset_options == {
            "include_instructions": False,
            "init_timeout": 10.0,
            "read_timeout": 10.0,
            "process_tool_call": record_mcp_tool_call,
        }
        assert received_transport is not None
        assert getattr(received_transport, "args") == ["-m", "app.tools.weather_server"]
        assert getattr(received_transport, "env")["NOMINATIM_USER_AGENT"] == (
            "my-ai-assistant-test/0.1"
        )

    assert created[0].closed is True


@pytest.mark.asyncio
@pytest.mark.integration
async def test_weather_runtime_starts_its_mcp_server_and_exposes_weather_tool() -> None:
    environment = {"NOMINATIM_USER_AGENT": "my-ai-assistant-test/0.1"}

    async with AsyncExitStack() as stack:
        active_tools = await open_weather_toolset(environment, stack=stack)
        weather_toolset = cast(MCPToolset[object], active_tools.toolsets[0])
        tools = await weather_toolset.list_tools()

    assert [tool.name for tool in tools] == ["get_current_weather"]
