# Prometheus Python metrics: https://prometheus.github.io/client_python/instrumenting/
from collections.abc import Callable

from prometheus_client import Counter, Gauge, Histogram


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
    buckets=(
        0.005,
        0.01,
        0.025,
        0.05,
        0.075,
        0.1,
        0.25,
        0.5,
        0.75,
        1.0,
        2.5,
        5.0,
        7.5,
        10.0,
        12.5,
        15.0,
        20.0,
        30.0,
        45.0,
        60.0,
    ),
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
OTHER_HTTP_METHOD = "OTHER"
KNOWN_HTTP_METHODS = frozenset(
    {"DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT", "TRACE"}
)


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
