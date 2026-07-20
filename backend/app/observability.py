# structlog contextvars: https://www.structlog.org/en/stable/contextvars.html
# Prometheus Python metrics: https://prometheus.github.io/client_python/instrumenting/
import structlog
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


def configure_observability() -> None:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str):
    return structlog.get_logger(name)
