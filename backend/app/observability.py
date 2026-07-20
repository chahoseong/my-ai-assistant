# structlog contextvars: https://www.structlog.org/en/stable/contextvars.html
# Prometheus Python metrics: https://prometheus.github.io/client_python/instrumenting/
from collections.abc import Callable
from time import perf_counter
from uuid import uuid4

import structlog
from prometheus_client import Counter, Gauge, Histogram
from starlette.types import ASGIApp, Message, Receive, Scope, Send


HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total",
    "Total HTTP requests by method, route template, and status.",
    labelnames=("method", "path", "status"),
)
HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds by method and route template.",
    labelnames=("method", "path"),
)
LLM_FIRST_TOKEN_SECONDS = Histogram(
    "llm_first_token_seconds",
    "Time from LLM invocation to the first stream delta in seconds.",
)
LLM_STREAM_DURATION_SECONDS = Histogram(
    "llm_stream_duration_seconds",
    "LLM stream duration in seconds.",
)
LLM_STREAM_DELTAS_TOTAL = Counter(
    "llm_stream_deltas_total",
    "Total LLM stream delta chunks.",
)
LLM_STREAM_FAILURES_TOTAL = Counter(
    "llm_stream_failures_total",
    "Total failed LLM streams.",
)
CONVERSATION_LOCK_CONFLICTS_TOTAL = Counter(
    "conversation_lock_conflicts_total",
    "Total conversation lock conflicts.",
)
DB_POOL_IN_USE = Gauge(
    "db_pool_in_use",
    "Current number of checked-out SQLAlchemy database connections.",
)

METRICS = {
    "http_requests_total": HTTP_REQUESTS_TOTAL,
    "http_request_duration_seconds": HTTP_REQUEST_DURATION_SECONDS,
    "llm_first_token_seconds": LLM_FIRST_TOKEN_SECONDS,
    "llm_stream_duration_seconds": LLM_STREAM_DURATION_SECONDS,
    "llm_stream_deltas_total": LLM_STREAM_DELTAS_TOTAL,
    "llm_stream_failures_total": LLM_STREAM_FAILURES_TOTAL,
    "conversation_lock_conflicts_total": CONVERSATION_LOCK_CONFLICTS_TOTAL,
    "db_pool_in_use": DB_POOL_IN_USE,
}
METRICS_PATH = "/metrics"
UNMATCHED_PATH = "__unmatched__"
OTHER_HTTP_METHOD = "OTHER"
KNOWN_HTTP_METHODS = frozenset(
    {"DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT", "TRACE"}
)


def configure_observability() -> None:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str):
    return structlog.get_logger(name)


def route_template(scope: Scope) -> str:
    route_path = getattr(scope.get("route"), "path", None)
    if isinstance(route_path, str):
        return route_path

    return UNMATCHED_PATH


def is_metrics_request(scope: Scope) -> bool:
    return scope["path"] in (METRICS_PATH, f"{METRICS_PATH}/")


def metric_http_method(method: str) -> str:
    if method in KNOWN_HTTP_METHODS:
        return method

    return OTHER_HTTP_METHOD


def record_http_request(
    *, method: str, path: str, status: int, duration_seconds: float
) -> None:
    normalized_method = metric_http_method(method)
    HTTP_REQUESTS_TOTAL.labels(
        method=normalized_method, path=path, status=str(status)
    ).inc()
    HTTP_REQUEST_DURATION_SECONDS.labels(method=normalized_method, path=path).observe(
        duration_seconds
    )


def record_llm_first_token(duration_seconds: float) -> None:
    LLM_FIRST_TOKEN_SECONDS.observe(duration_seconds)


def record_llm_stream_duration(duration_seconds: float) -> None:
    LLM_STREAM_DURATION_SECONDS.observe(duration_seconds)


def record_llm_stream_delta() -> None:
    LLM_STREAM_DELTAS_TOTAL.inc()


def record_llm_stream_failure() -> None:
    LLM_STREAM_FAILURES_TOTAL.inc()


def record_conversation_lock_conflict() -> None:
    CONVERSATION_LOCK_CONFLICTS_TOTAL.inc()


# Source: https://prometheus.github.io/client_python/instrumenting/gauge/
def bind_db_pool_in_use(pool_checkedout: Callable[[], int]) -> None:
    DB_POOL_IN_USE.set_function(pool_checkedout)


# Source: https://www.starlette.io/middleware/#pure-asgi-middleware
# Source: https://www.starlette.io/middleware/#inspecting-or-modifying-the-response
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
