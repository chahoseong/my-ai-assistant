import asyncio

import httpx


class LlamaContextLimitCache:
    def __init__(
        self,
        base_url: str,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._props_url = httpx.URL(base_url).copy_with(
            path="/props",
            query=None,
            fragment=None,
        )
        self._transport = transport
        self._lock = asyncio.Lock()
        self._loaded = False
        self._context_limit: int | None = None

    async def get_context_limit(self) -> int | None:
        if self._loaded:
            return self._context_limit

        async with self._lock:
            if not self._loaded:
                try:
                    async with httpx.AsyncClient(transport=self._transport) as client:
                        response = await client.get(self._props_url)
                    response.raise_for_status()
                    body = response.json()
                    context_limit = body["default_generation_settings"]["n_ctx"]
                    if (
                        not isinstance(context_limit, int)
                        or isinstance(context_limit, bool)
                        or context_limit <= 0
                    ):
                        raise ValueError("n_ctx must be a positive integer")
                    self._context_limit = context_limit
                except httpx.HTTPError, KeyError, TypeError, ValueError:
                    self._context_limit = None
                self._loaded = True

        return self._context_limit
