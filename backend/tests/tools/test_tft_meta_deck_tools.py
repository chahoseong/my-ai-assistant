from datetime import UTC, datetime
import json

import pytest
import structlog
from pydantic_ai import ModelRetry

from app.tools.tft_meta_deck_tools import (
    TftMetaDeckSortInput,
    TftMetaDeckTools,
    TftMetaDeckWhereInput,
)
from app.tools.tft_meta_decks import (
    TftMetaDeckSnapshotCache,
    TftMetaDeckUpstreamTimeout,
)
from app.observability.metrics import (
    AGENT_TOOL_CALLS_TOTAL,
    AGENT_TOOL_DURATION_SECONDS,
)
from app.observability.logging import configure_observability


pytestmark = pytest.mark.unit


def histogram_count(*, tool_name: str, outcome: str) -> float:
    [metric] = AGENT_TOOL_DURATION_SECONDS.labels(
        tool_name=tool_name, outcome=outcome
    ).collect()
    return next(
        sample.value
        for sample in metric.samples
        if sample.name == "agent_tool_duration_seconds_count"
    )


@pytest.fixture
def tools() -> TftMetaDeckTools:
    async def fetch_payload() -> object:
        return {
            "data": [
                {
                    "name": {"ko_KR": "테스트 덱"},
                    "stat": {"deck": {"winRate": 0.21}},
                    "traits": [{"key": "trait-a"}],
                }
            ],
            "metadata": {"gameStatDateTime": "2026-07-23T12:00:00Z"},
        }

    return TftMetaDeckTools(
        TftMetaDeckSnapshotCache(
            fetch_payload=fetch_payload,
            now=lambda: datetime(2026, 7, 23, 12, 5, tzinfo=UTC),
        )
    )


@pytest.mark.asyncio
async def test_describe_tool_returns_schema_without_meta_deck_values(
    tools: TftMetaDeckTools,
) -> None:
    result = await tools.tft_describe_meta_decks()

    assert result == {
        "record_count": 1,
        "data_as_of": "2026-07-23T12:00:00+00:00",
        "fetched_at": "2026-07-23T12:05:00+00:00",
        "fields": [
            {"path": "name.ko_KR", "type": "string", "present_count": 1},
            {
                "path": "stat.deck.winRate",
                "type": "number",
                "present_count": 1,
            },
            {"path": "traits[].key", "type": "string", "present_count": 1},
        ],
    }


@pytest.mark.asyncio
async def test_describe_tool_records_a_successful_model_tool_call(
    tools: TftMetaDeckTools,
) -> None:
    calls = AGENT_TOOL_CALLS_TOTAL.labels(
        tool_name="tft_describe_meta_decks", outcome="success"
    )._value.get()
    durations = histogram_count(
        tool_name="tft_describe_meta_decks", outcome="success"
    )

    await tools.tft_describe_meta_decks()

    assert (
        AGENT_TOOL_CALLS_TOTAL.labels(
            tool_name="tft_describe_meta_decks", outcome="success"
        )._value.get()
        == calls + 1
    )
    assert (
        histogram_count(tool_name="tft_describe_meta_decks", outcome="success")
        == durations + 1
    )


@pytest.mark.asyncio
async def test_query_tool_converts_the_typed_condition_and_returns_only_requested_values(
    tools: TftMetaDeckTools,
) -> None:
    result = await tools.tft_query_meta_decks(
        fields=["name.ko_KR", "stat.deck.winRate"],
        where=TftMetaDeckWhereInput.model_validate(
            {"path": "traits[].key", "operator": "contains", "value": "trait-a"}
        ),
        sort=TftMetaDeckSortInput(path="stat.deck.winRate", direction="desc"),
        limit=3,
    )

    assert result == {
        "records": [
            {
                "name": {"ko_KR": "테스트 덱"},
                "stat": {"deck": {"winRate": 0.21}},
            }
        ],
        "matched_count": 1,
        "sort_excluded_count": 0,
        "data_as_of": "2026-07-23T12:00:00+00:00",
        "fetched_at": "2026-07-23T12:05:00+00:00",
    }


@pytest.mark.asyncio
async def test_query_tool_requests_a_model_retry_for_invalid_queries(
    tools: TftMetaDeckTools,
) -> None:
    with pytest.raises(ModelRetry) as error:
        await tools.tft_query_meta_decks(
            fields=["unknown.field"], where=None, sort=None, limit=3
        )

    assert error.value.message.startswith("INVALID_QUERY:")

    assert (
        AGENT_TOOL_CALLS_TOTAL.labels(
            tool_name="tft_query_meta_decks", outcome="denied"
        )._value.get()
        >= 1
    )


@pytest.mark.asyncio
async def test_describe_tool_records_an_upstream_timeout_before_requesting_a_retry() -> None:
    async def fetch_payload() -> object:
        raise TftMetaDeckUpstreamTimeout("timed out")

    tools = TftMetaDeckTools(TftMetaDeckSnapshotCache(fetch_payload=fetch_payload))
    calls = AGENT_TOOL_CALLS_TOTAL.labels(
        tool_name="tft_describe_meta_decks", outcome="timeout"
    )._value.get()

    with pytest.raises(ModelRetry) as error:
        await tools.tft_describe_meta_decks()

    assert error.value.message.startswith("UPSTREAM_TIMEOUT:")
    assert (
        AGENT_TOOL_CALLS_TOTAL.labels(
            tool_name="tft_describe_meta_decks", outcome="timeout"
        )._value.get()
        == calls + 1
    )


@pytest.mark.asyncio
async def test_query_tool_logs_a_safe_timeout_with_request_correlation(
    capsys: pytest.CaptureFixture[str],
) -> None:
    structlog.reset_defaults()
    configure_observability()
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(request_id="request-tool-timeout")
    secret_error_detail = "upstream response must not be logged"
    sensitive_argument = "tool argument must not be logged"

    async def fetch_payload() -> object:
        raise TftMetaDeckUpstreamTimeout(secret_error_detail)

    tools = TftMetaDeckTools(TftMetaDeckSnapshotCache(fetch_payload=fetch_payload))

    with pytest.raises(ModelRetry):
        await tools.tft_query_meta_decks(
            fields=[sensitive_argument], where=None, sort=None, limit=1
        )

    records = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line]
    [failure_log] = [
        record for record in records if record["event"] == "agent_tool_call_failed"
    ]
    assert failure_log["tool_name"] == "tft_query_meta_decks"
    assert failure_log["outcome"] == "timeout"
    assert failure_log["error_type"] == "TftMetaDeckUpstreamTimeout"
    assert failure_log["duration_ms"] >= 0
    assert failure_log["request_id"] == "request-tool-timeout"
    assert secret_error_detail not in json.dumps(failure_log)
    assert sensitive_argument not in json.dumps(failure_log)


def test_where_input_requires_exactly_one_predicate_or_condition_group() -> None:
    with pytest.raises(ValueError):
        TftMetaDeckWhereInput.model_validate(
            {
                "path": "traits[].key",
                "operator": "contains",
                "value": "trait-a",
                "all": [],
            }
        )
