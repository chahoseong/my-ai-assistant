import asyncio

import httpx
import pytest

from app.llama import LlamaContextLimitCache


pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_context_limit_is_loaded_once_and_shared_by_concurrent_callers() -> None:
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        assert request.url == httpx.URL("http://llama.test/props")
        return httpx.Response(
            200,
            json={"default_generation_settings": {"n_ctx": 8192}},
        )

    cache = LlamaContextLimitCache(
        "http://llama.test/v1",
        transport=httpx.MockTransport(handler),
    )

    values = await asyncio.gather(
        cache.get_context_limit(),
        cache.get_context_limit(),
        cache.get_context_limit(),
    )

    assert values == [8192, 8192, 8192]
    assert call_count == 1


@pytest.mark.asyncio
async def test_context_limit_failure_is_cached_as_none() -> None:
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        raise httpx.ConnectError("llama-server unavailable", request=request)

    cache = LlamaContextLimitCache(
        "http://llama.test/v1",
        transport=httpx.MockTransport(handler),
    )

    assert await cache.get_context_limit() is None
    assert await cache.get_context_limit() is None
    assert call_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("n_ctx", [None, True, 0, -1, "8192"])
async def test_context_limit_rejects_invalid_values(n_ctx: object) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"default_generation_settings": {"n_ctx": n_ctx}},
        )

    cache = LlamaContextLimitCache(
        "http://llama.test/v1",
        transport=httpx.MockTransport(handler),
    )

    assert await cache.get_context_limit() is None
