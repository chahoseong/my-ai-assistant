# Source: https://www.starlette.io/middleware/#pure-asgi-middleware
# Source: https://www.starlette.io/middleware/#inspecting-or-modifying-the-response
from time import perf_counter
from uuid import uuid4

import structlog
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.observability.logging import get_logger
from app.observability.metrics import METRICS_PATH, record_http_request


UNMATCHED_PATH = "__unmatched__"


def route_template(scope: Scope) -> str:
    route_path = getattr(scope.get("route"), "path", None)
    if isinstance(route_path, str):
        return route_path

    return UNMATCHED_PATH


def is_metrics_request(scope: Scope) -> bool:
    return scope["path"] in (METRICS_PATH, f"{METRICS_PATH}/")


class RequestObservabilityMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or is_metrics_request(scope):
            await self.app(scope, receive, send)
            return

        request_id = str(uuid4())
        start = perf_counter()
        response_status = 500
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        async def send_with_observability(message: Message) -> None:
            nonlocal response_status
            if message["type"] == "http.response.start":
                response_status = int(message["status"])

            await send(message)

        try:
            await self.app(scope, receive, send_with_observability)
        finally:
            duration_seconds = perf_counter() - start
            path = route_template(scope)
            record_http_request(
                method=scope["method"],
                path=path,
                status=response_status,
                duration_seconds=duration_seconds,
            )
            get_logger("app.access").info(
                "http_request_complete",
                method=scope["method"],
                path=path,
                status=response_status,
                duration_ms=duration_seconds * 1_000,
            )
            structlog.contextvars.clear_contextvars()
