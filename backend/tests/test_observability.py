import json

import structlog

from app.observability import METRICS, configure_observability, get_logger


def test_configured_logger_writes_json_with_bound_request_id(capsys) -> None:
    structlog.reset_defaults()
    configure_observability()
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(request_id="request-123")

    get_logger("app.test").info("observability_probe")

    payload = json.loads(capsys.readouterr().out)
    assert payload["event"] == "observability_probe"
    assert payload["request_id"] == "request-123"
    assert payload["level"] == "info"


def test_metrics_match_the_issue_contract() -> None:
    assert set(METRICS) == {
        "http_requests_total",
        "http_request_duration_seconds",
        "llm_first_token_seconds",
        "llm_stream_duration_seconds",
        "llm_stream_deltas_total",
        "llm_stream_failures_total",
        "conversation_lock_conflicts_total",
        "db_pool_in_use",
    }
    assert {name: metric._labelnames for name, metric in METRICS.items()} == {
        "http_requests_total": ("method", "path", "status"),
        "http_request_duration_seconds": ("method", "path"),
        "llm_first_token_seconds": (),
        "llm_stream_duration_seconds": (),
        "llm_stream_deltas_total": (),
        "llm_stream_failures_total": (),
        "conversation_lock_conflicts_total": (),
        "db_pool_in_use": (),
    }
