import json
from uuid import UUID

from httpx import AsyncClient
import pytest
import structlog

import app.dependencies
from app.observability import (
    HTTP_REQUEST_DURATION_SECONDS,
    HTTP_REQUESTS_TOTAL,
    METRICS,
    configure_observability,
    get_logger,
)


def metric_sample_value(metric, sample_name: str, labels: dict[str, str]) -> float:
    for family in metric.collect():
        for sample in family.samples:
            if sample.name == sample_name and sample.labels == labels:
                return sample.value

    raise AssertionError(f"Missing {sample_name} sample with labels {labels}")


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


@pytest.mark.asyncio
async def test_message_request_uses_route_template_for_logs_and_metrics(
    client: AsyncClient, capsys, test_database, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app.dependencies, "database", test_database)
    route_template = "/api/conversations/{conversation_id}/messages"
    counter = HTTP_REQUESTS_TOTAL.labels(
        method="GET", path=route_template, status="401"
    )
    _ = HTTP_REQUEST_DURATION_SECONDS.labels(method="GET", path=route_template)
    before_requests = counter._value.get()
    before_duration_count = metric_sample_value(
        HTTP_REQUEST_DURATION_SECONDS,
        "http_request_duration_seconds_count",
        {"method": "GET", "path": route_template},
    )
    capsys.readouterr()

    response = await client.get(
        "/api/conversations/00000000-0000-0000-0000-000000000001/messages"
    )

    assert response.status_code == 401
    assert counter._value.get() == before_requests + 1
    assert (
        metric_sample_value(
            HTTP_REQUEST_DURATION_SECONDS,
            "http_request_duration_seconds_count",
            {"method": "GET", "path": route_template},
        )
        == before_duration_count + 1
    )
    raw_path = "/api/conversations/00000000-0000-0000-0000-000000000001/messages"
    metric_paths = {
        sample.labels["path"]
        for family in HTTP_REQUESTS_TOTAL.collect()
        for sample in family.samples
        if "path" in sample.labels
    }
    assert raw_path not in metric_paths

    records = [
        json.loads(line) for line in capsys.readouterr().out.splitlines() if line
    ]
    [access_log] = [
        record for record in records if record["event"] == "http_request_complete"
    ]
    assert access_log["method"] == "GET"
    assert access_log["path"] == route_template
    assert access_log["status"] == 401
    assert access_log["duration_ms"] >= 0
    UUID(access_log["request_id"])


@pytest.mark.asyncio
async def test_unmatched_request_uses_fixed_path_for_logs_and_metrics(
    client: AsyncClient, capsys
) -> None:
    counter = HTTP_REQUESTS_TOTAL.labels(
        method="GET", path="__unmatched__", status="404"
    )
    before_requests = counter._value.get()
    capsys.readouterr()

    response = await client.get("/api/not-a-route")

    assert response.status_code == 404
    assert counter._value.get() == before_requests + 1

    records = [
        json.loads(line) for line in capsys.readouterr().out.splitlines() if line
    ]
    [access_log] = [
        record for record in records if record["event"] == "http_request_complete"
    ]
    assert access_log["path"] == "__unmatched__"
