from contextlib import AsyncExitStack
from types import SimpleNamespace

import pytest

from app.config import OpggTftSettings
from app.tools.toolsets import open_opgg_tft_tools


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


@pytest.mark.asyncio
async def test_opgg_runtime_opens_a_streamable_http_client_and_closes_it_with_its_stack() -> None:
    created: list[FakeMcpClient] = []

    def client_factory(_: object) -> FakeMcpClient:
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
                client_factory=lambda _: FakeMcpClient(fail_on_enter=True),
            )

        # The caller keeps control of the lifespan and can still activate other tools.
        assert stack is not None
