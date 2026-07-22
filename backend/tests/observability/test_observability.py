import json
from typing import cast
from uuid import UUID

from httpx import AsyncClient
import pytest


from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

import app.database.dependencies
import app.main
from app.routers import chat as chat_router
from app.concurrency import ConversationLease
from app.database.core import Database
from app.observability.logging import configure_observability, get_logger
from app.observability.metrics import (
    HTTP_REQUEST_DURATION_SECONDS,
    HTTP_REQUESTS_TOTAL,
    LLM_FIRST_TOKEN_SECONDS,
    METRICS,
)
from app.auth.security import hash_password

pytestmark = [pytest.mark.integration, pytest.mark.contract]


class SuccessfulStream:
    async def __aenter__(self) -> "SuccessfulStream":
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def stream_text(self, *, delta: bool):
        assert delta is True
        yield "safe assistant response"


class SuccessfulAgent:
    def run_stream(self, *_: object, **__: object) -> SuccessfulStream:
        return SuccessfulStream()


class RecordingSession:
    def add(self, _: object) -> None:
        return None

    async def commit(self) -> None:
        return None

    async def __aenter__(self) -> "RecordingSession":
        return self

    async def __aexit__(self, *args: object) -> None:
        return None


class RecordingDatabase:
    def session_factory(self) -> RecordingSession:
        return RecordingSession()


class RecordingLease:
    async def release(self) -> None:
        return None


def metric_sample_value(metric, sample_name: str, labels: dict[str, str]) -> float:
    for family in metric.collect():
        for sample in family.samples:
            if sample.name == sample_name and sample.labels == labels:
                return sample.value

    raise AssertionError(f"Missing {sample_name} sample with labels {labels}")


def metric_total(metric, sample_name: str) -> float:
    return sum(
        sample.value
        for family in metric.collect()
        for sample in family.samples
        if sample.name == sample_name
    )


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


@pytest.mark.asyncio
async def test_stream_logs_exact_ttft_without_prompt_content(
    monkeypatch, capsys
) -> None:
    structlog.reset_defaults()
    configure_observability()
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(request_id="request-ttft")
    monkeypatch.setattr(chat_router, "get_stream_agent", SuccessfulAgent)
    prompt = "prompt-must-not-appear-in-ttft-log"

    _ = [
        event
        async for event in chat_router.stream_persisted_message(
            cast(Database, RecordingDatabase()),
            UUID(int=1),
            prompt,
            [],
            cast(ConversationLease, RecordingLease()),
        )
    ]

    records = [
        json.loads(line) for line in capsys.readouterr().out.splitlines() if line
    ]
    [ttft_log] = [record for record in records if record["event"] == "llm_first_token"]
    assert ttft_log["ttft_ms"] >= 0
    assert ttft_log["request_id"] == "request-ttft"
    assert prompt not in json.dumps(ttft_log)


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


def test_ttft_histogram_has_buckets_above_ten_seconds() -> None:
    bounds = {
        sample.labels["le"]
        for family in LLM_FIRST_TOKEN_SECONDS.collect()
        for sample in family.samples
        if sample.name == "llm_first_token_seconds_bucket"
    }

    assert {"10.0", "12.5", "15.0", "20.0", "30.0", "45.0", "60.0"} <= bounds


@pytest.mark.asyncio
async def test_metrics_endpoint_exposes_metrics_without_recording_its_scrape(
    client: AsyncClient,
) -> None:
    before_requests = metric_total(HTTP_REQUESTS_TOTAL, "http_requests_total")

    response = await client.get("/metrics", follow_redirects=True)
    direct_response = await client.get("/metrics/")

    assert response.status_code == 200
    assert direct_response.status_code == 200
    assert "http_requests_total" in response.text
    metric_paths = {
        sample.labels["path"]
        for family in HTTP_REQUESTS_TOTAL.collect()
        for sample in family.samples
        if "path" in sample.labels
    }
    assert "/metrics" not in metric_paths
    assert metric_total(HTTP_REQUESTS_TOTAL, "http_requests_total") == before_requests


@pytest.mark.asyncio
async def test_login_and_message_logs_exclude_sensitive_values(
    client: AsyncClient, test_database, user_factory, monkeypatch, capfd
) -> None:
    password = "password-secret-7c5a1471"
    message = "message-secret-2a90db8e"
    monkeypatch.setattr(app.database.dependencies, "database", test_database)
    monkeypatch.setattr(app.main, "agent", SuccessfulAgent())
    await user_factory(
        username="observabilityuser",
        password_hash=await hash_password(password),
    )
    capfd.readouterr()

    login = await client.post(
        "/api/auth/login",
        json={"username": "observabilityuser", "password": password},
    )
    raw_token = login.cookies.get("assistant_session")
    assert login.status_code == 204
    assert raw_token is not None

    conversation = await client.post("/api/conversations", json={})
    assert conversation.status_code == 201

    response = await client.post(
        f"/api/conversations/{conversation.json()['id']}/messages",
        json={"message": message},
    )

    assert response.status_code == 200
    captured_logs = capfd.readouterr().out
    for sensitive_value in (password, raw_token, message):
        assert sensitive_value not in captured_logs


@pytest.mark.asyncio
async def test_message_stream_logs_exact_ttft_without_message_content(
    client: AsyncClient,
    test_database,
    user_factory,
    session_factory,
    monkeypatch,
    capfd,
) -> None:
    user = await user_factory(username="ttft-log-user")
    _, token = await session_factory(user=user)
    client.cookies.set("assistant_session", token)
    monkeypatch.setattr(app.database.dependencies, "database", test_database)
    monkeypatch.setattr(app.main, "agent", SuccessfulAgent())
    prompt = "prompt-must-not-appear-in-ttft-log"
    capfd.readouterr()

    conversation = await client.post("/api/conversations", json={})
    response = await client.post(
        f"/api/conversations/{conversation.json()['id']}/messages",
        json={"message": prompt},
    )

    assert response.status_code == 200
    records = [json.loads(line) for line in capfd.readouterr().out.splitlines() if line]
    [ttft_log] = [record for record in records if record["event"] == "llm_first_token"]
    assert ttft_log["ttft_ms"] >= 0
    UUID(ttft_log["request_id"])
    assert prompt not in json.dumps(ttft_log)


@pytest.mark.asyncio
async def test_message_request_uses_route_template_for_logs_and_metrics(
    client: AsyncClient, capsys, test_database, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app.database.dependencies, "database", test_database)
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


@pytest.mark.asyncio
async def test_unknown_http_methods_share_fixed_metric_label(
    client: AsyncClient,
) -> None:
    counter = HTTP_REQUESTS_TOTAL.labels(
        method="OTHER", path="__unmatched__", status="404"
    )
    before_requests = counter._value.get()

    first_response = await client.request("X-UNRECOGNIZED-ONE", "/api/not-a-route")
    second_response = await client.request("X-UNRECOGNIZED-TWO", "/api/not-a-route")

    assert first_response.status_code == 404
    assert second_response.status_code == 404
    assert counter._value.get() == before_requests + 2
    metric_methods = {
        sample.labels["method"]
        for family in HTTP_REQUESTS_TOTAL.collect()
        for sample in family.samples
        if "method" in sample.labels
    }
    assert "X-UNRECOGNIZED-ONE" not in metric_methods
    assert "X-UNRECOGNIZED-TWO" not in metric_methods


@pytest.mark.asyncio
async def test_signup_failure_correlates_failure_and_access_logs(
    client: AsyncClient, capfd, test_database, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app.database.dependencies, "database", test_database)

    async def fail_commit(_: AsyncSession) -> None:
        raise SQLAlchemyError("controlled signup failure")

    monkeypatch.setattr(AsyncSession, "commit", fail_commit)
    capfd.readouterr()
    response = await client.post(
        "/api/auth/signup",
        json={
            "username": "correlation_user",
            "password": "correct horse battery staple",
        },
    )

    assert response.status_code == 500
    captured = capfd.readouterr()
    records = [json.loads(line) for line in captured.out.splitlines() if line]
    [failure_log] = [record for record in records if record["event"] == "signup_failed"]
    [access_log] = [
        record for record in records if record["event"] == "http_request_complete"
    ]
    assert failure_log["request_id"] == access_log["request_id"]
    UUID(failure_log["request_id"])
