import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from mcp.types import ErrorData
from mcp import McpError

from app.tools.tft_meta_decks import (
    FieldDescription,
    InvalidTftMetaDeckResponse,
    InvalidTftMetaDeckQuery,
    MISSING,
    TftMetaDeckAll,
    TftMetaDeckAny,
    TftMetaDeckPredicate,
    TftMetaDeckQueryResult,
    TftMetaDeckResultTooLarge,
    TftMetaDeckSnapshot,
    TftMetaDeckSort,
    TftMetaDeckSnapshotCache,
    TftMetaDeckUpstreamUnavailable,
    TftMetaDeckUpstreamTimeout,
    fetch_opgg_tft_meta_decks,
    resolve_field_path,
)


pytestmark = pytest.mark.unit


class FakeMcpClient:
    def __init__(self, result: object | None = None, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.calls: list[tuple[str, dict[str, object] | None]] = []

    async def call_tool(
        self, name: str, arguments: dict[str, object] | None = None
    ) -> object:
        self.calls.append((name, arguments))
        if self.error is not None:
            raise self.error
        return self.result


@pytest.mark.asyncio
async def test_opgg_fetcher_uses_only_the_meta_deck_tool_and_returns_structured_data() -> None:
    payload = {"data": [], "metadata": {"gameStatDateTime": "2026-07-23T12:00:00Z"}}
    client = FakeMcpClient(SimpleNamespace(data=payload, is_error=False))

    result = await fetch_opgg_tft_meta_decks(client)

    assert result == payload
    assert client.calls == [("tft_list_meta_decks", {})]


@pytest.mark.asyncio
async def test_opgg_fetcher_accepts_a_json_text_content_result() -> None:
    payload = {"data": [], "metadata": {"gameStatDateTime": "2026-07-23T12:00:00Z"}}
    client = FakeMcpClient(
        SimpleNamespace(
            data=None,
            content=[SimpleNamespace(text=json.dumps(payload))],
            is_error=False,
        )
    )

    assert await fetch_opgg_tft_meta_decks(client) == payload


@pytest.mark.asyncio
async def test_opgg_fetcher_rejects_a_malformed_success_response() -> None:
    client = FakeMcpClient(
        SimpleNamespace(
            data=None,
            content=[SimpleNamespace(text="not-json")],
            is_error=False,
        )
    )

    with pytest.raises(InvalidTftMetaDeckResponse) as error:
        await fetch_opgg_tft_meta_decks(client)

    assert error.value.code == "UPSTREAM_INVALID_RESPONSE"


@pytest.mark.asyncio
async def test_opgg_fetcher_translates_remote_call_failures_to_unavailable() -> None:
    client = FakeMcpClient(error=RuntimeError("connection lost"))

    with pytest.raises(TftMetaDeckUpstreamUnavailable) as error:
        await fetch_opgg_tft_meta_decks(client)

    assert error.value.code == "UPSTREAM_UNAVAILABLE"


@pytest.mark.asyncio
async def test_opgg_fetcher_classifies_the_mcp_request_timeout_without_reading_its_message() -> None:
    client = FakeMcpClient(
        error=McpError(ErrorData(code=408, message="provider-specific text"))
    )

    with pytest.raises(TftMetaDeckUpstreamTimeout) as error:
        await fetch_opgg_tft_meta_decks(client)

    assert error.value.code == "UPSTREAM_TIMEOUT"


def test_snapshot_preserves_valid_meta_deck_records_and_timestamps() -> None:
    fetched_at = datetime(2026, 7, 23, 12, 5, tzinfo=UTC)

    snapshot = TftMetaDeckSnapshot.from_payload(
        {
            "data": [
                {
                    "name": {"ko_KR": "테스트 덱"},
                    "stat": {"deck": {"winRate": 0.18}},
                }
            ],
            "metadata": {"gameStatDateTime": "2026-07-23T12:00:00Z"},
        },
        fetched_at=fetched_at,
    )

    assert snapshot.records == (
        {
            "name": {"ko_KR": "테스트 덱"},
            "stat": {"deck": {"winRate": 0.18}},
        },
    )
    assert snapshot.data_as_of == datetime(2026, 7, 23, 12, tzinfo=UTC)
    assert snapshot.fetched_at == fetched_at


def test_snapshot_allows_a_valid_empty_meta_deck_list() -> None:
    snapshot = TftMetaDeckSnapshot.from_payload(
        {
            "data": [],
            "metadata": {"gameStatDateTime": "2026-07-23T12:00:00Z"},
        },
        fetched_at=datetime(2026, 7, 23, 12, 5, tzinfo=UTC),
    )

    assert snapshot.records == ()


@pytest.mark.parametrize(
    "payload",
    [
        {"metadata": {"gameStatDateTime": "2026-07-23T12:00:00Z"}},
        {
            "data": "not an array",
            "metadata": {"gameStatDateTime": "2026-07-23T12:00:00Z"},
        },
        {"data": [], "metadata": {}},
        {
            "data": [],
            "metadata": {"gameStatDateTime": "not-a-timestamp"},
        },
    ],
)
def test_snapshot_rejects_an_invalid_external_response(payload: object) -> None:
    with pytest.raises(InvalidTftMetaDeckResponse) as error:
        TftMetaDeckSnapshot.from_payload(
            payload,
            fetched_at=datetime(2026, 7, 23, 12, 5, tzinfo=UTC),
        )

    assert error.value.code == "UPSTREAM_INVALID_RESPONSE"


def test_snapshot_describes_nested_fields_without_exposing_values() -> None:
    snapshot = TftMetaDeckSnapshot.from_payload(
        {
            "data": [
                {
                    "name": {"ko_KR": "테스트 덱 A"},
                    "stat": {"deck": {"winRate": 0.18}},
                    "units": [
                        {"key": "unit-a", "isCore": True},
                        {"key": "unit-b"},
                    ],
                },
                {
                    "name": {"ko_KR": "테스트 덱 B"},
                    "stat": {"deck": {"winRate": 0.21}},
                    "units": [{"key": "unit-c"}],
                },
            ],
            "metadata": {"gameStatDateTime": "2026-07-23T12:00:00Z"},
        },
        fetched_at=datetime(2026, 7, 23, 12, 5, tzinfo=UTC),
    )

    assert snapshot.describe_fields() == (
        FieldDescription(path="name.ko_KR", type="string", present_count=2),
        FieldDescription(path="stat.deck.winRate", type="number", present_count=2),
        FieldDescription(path="units[].isCore", type="boolean", present_count=1),
        FieldDescription(path="units[].key", type="string", present_count=2),
    )


def test_field_path_resolver_preserves_arrays_missing_values_and_json_null() -> None:
    record = {
        "stat": {"deck": {"winRate": 0.18, "pickRate": None}},
        "units": [
            {"key": "unit-a", "isCore": True},
            {"key": "unit-b"},
        ],
    }

    assert resolve_field_path(record, "stat.deck.winRate") == (0.18,)
    assert resolve_field_path(record, "units[].key") == ("unit-a", "unit-b")
    assert resolve_field_path(record, "units[].isCore") == (True, MISSING)
    assert resolve_field_path(record, "stat.deck.pickRate") == (None,)
    assert resolve_field_path(record, "stat.deck.avgPlacement") == (MISSING,)


def test_query_projects_only_requested_scalar_fields_in_source_order() -> None:
    fetched_at = datetime(2026, 7, 23, 12, 5, tzinfo=UTC)
    snapshot = TftMetaDeckSnapshot.from_payload(
        {
            "data": [
                {
                    "name": {"ko_KR": "테스트 덱 A"},
                    "stat": {"deck": {"winRate": 0.18, "pickRate": 0.12}},
                },
                {
                    "name": {"ko_KR": "테스트 덱 B"},
                    "stat": {"deck": {"winRate": 0.21, "pickRate": 0.08}},
                },
            ],
            "metadata": {"gameStatDateTime": "2026-07-23T12:00:00Z"},
        },
        fetched_at=fetched_at,
    )

    result = snapshot.query(
        fields=("name.ko_KR", "stat.deck.winRate"),
        where=None,
        sort=None,
        limit=10,
    )

    assert result == TftMetaDeckQueryResult(
        records=(
            {
                "name": {"ko_KR": "테스트 덱 A"},
                "stat": {"deck": {"winRate": 0.18}},
            },
            {
                "name": {"ko_KR": "테스트 덱 B"},
                "stat": {"deck": {"winRate": 0.21}},
            },
        ),
        matched_count=2,
        sort_excluded_count=0,
        data_as_of=datetime(2026, 7, 23, 12, tzinfo=UTC),
        fetched_at=fetched_at,
    )


def test_query_preserves_array_element_relationships_in_projection() -> None:
    snapshot = TftMetaDeckSnapshot.from_payload(
        {
            "data": [
                {
                    "name": {"ko_KR": "테스트 덱"},
                    "units": [
                        {"key": "unit-a", "isCore": True},
                        {"key": "unit-b"},
                    ],
                }
            ],
            "metadata": {"gameStatDateTime": "2026-07-23T12:00:00Z"},
        },
        fetched_at=datetime(2026, 7, 23, 12, 5, tzinfo=UTC),
    )

    result = snapshot.query(
        fields=("name.ko_KR", "units[].key", "units[].isCore"),
        where=None,
        sort=None,
        limit=10,
    )

    assert result.records == (
        {
            "name": {"ko_KR": "테스트 덱"},
            "units": [
                {"key": "unit-a", "isCore": True},
                {"key": "unit-b"},
            ],
        },
    )


def test_query_filters_records_with_a_scalar_gte_predicate() -> None:
    snapshot = TftMetaDeckSnapshot.from_payload(
        {
            "data": [
                {
                    "name": {"ko_KR": "테스트 덱 A"},
                    "stat": {"deck": {"winRate": 0.18}},
                },
                {
                    "name": {"ko_KR": "테스트 덱 B"},
                    "stat": {"deck": {"winRate": 0.21}},
                },
            ],
            "metadata": {"gameStatDateTime": "2026-07-23T12:00:00Z"},
        },
        fetched_at=datetime(2026, 7, 23, 12, 5, tzinfo=UTC),
    )

    result = snapshot.query(
        fields=("name.ko_KR", "stat.deck.winRate"),
        where=TftMetaDeckPredicate(
            path="stat.deck.winRate", operator="gte", value=0.2
        ),
        sort=None,
        limit=10,
    )

    assert result.records == (
        {
            "name": {"ko_KR": "테스트 덱 B"},
            "stat": {"deck": {"winRate": 0.21}},
        },
    )
    assert result.matched_count == 1


def test_query_filters_records_when_an_array_contains_a_requested_value() -> None:
    snapshot = TftMetaDeckSnapshot.from_payload(
        {
            "data": [
                {
                    "name": {"ko_KR": "특성 A 덱"},
                    "traits": [{"key": "trait-a"}, {"key": "trait-b"}],
                },
                {
                    "name": {"ko_KR": "특성 C 덱"},
                    "traits": [{"key": "trait-c"}],
                },
            ],
            "metadata": {"gameStatDateTime": "2026-07-23T12:00:00Z"},
        },
        fetched_at=datetime(2026, 7, 23, 12, 5, tzinfo=UTC),
    )

    result = snapshot.query(
        fields=("name.ko_KR", "traits[].key"),
        where=TftMetaDeckPredicate(
            path="traits[].key", operator="contains", value="trait-a"
        ),
        sort=None,
        limit=10,
    )

    assert result.records == (
        {
            "name": {"ko_KR": "특성 A 덱"},
            "traits": [{"key": "trait-a"}, {"key": "trait-b"}],
        },
    )
    assert result.matched_count == 1


def test_query_treats_only_a_known_empty_array_as_not_containing_a_value() -> None:
    snapshot = TftMetaDeckSnapshot.from_payload(
        {
            "data": [
                {"name": {"ko_KR": "특성 정보 없음"}},
                {"name": {"ko_KR": "특성 없음"}, "traits": []},
                {
                    "name": {"ko_KR": "특성 A 덱"},
                    "traits": [{"key": "trait-a"}],
                },
            ],
            "metadata": {"gameStatDateTime": "2026-07-23T12:00:00Z"},
        },
        fetched_at=datetime(2026, 7, 23, 12, 5, tzinfo=UTC),
    )

    result = snapshot.query(
        fields=("name.ko_KR",),
        where=TftMetaDeckPredicate(
            path="traits[].key", operator="not_contains", value="trait-a"
        ),
        sort=None,
        limit=10,
    )

    assert result.records == ({"name": {"ko_KR": "특성 없음"}},)
    assert result.matched_count == 1


def test_query_requires_every_predicate_in_an_all_group_to_match() -> None:
    snapshot = TftMetaDeckSnapshot.from_payload(
        {
            "data": [
                {
                    "name": {"ko_KR": "조건 모두 충족"},
                    "stat": {"deck": {"winRate": 0.21}},
                    "traits": [{"key": "trait-a"}],
                },
                {
                    "name": {"ko_KR": "승률만 충족"},
                    "stat": {"deck": {"winRate": 0.22}},
                    "traits": [{"key": "trait-b"}],
                },
                {
                    "name": {"ko_KR": "특성만 충족"},
                    "stat": {"deck": {"winRate": 0.18}},
                    "traits": [{"key": "trait-a"}],
                },
            ],
            "metadata": {"gameStatDateTime": "2026-07-23T12:00:00Z"},
        },
        fetched_at=datetime(2026, 7, 23, 12, 5, tzinfo=UTC),
    )

    result = snapshot.query(
        fields=("name.ko_KR",),
        where=TftMetaDeckAll(
            conditions=(
                TftMetaDeckPredicate(
                    path="stat.deck.winRate", operator="gte", value=0.2
                ),
                TftMetaDeckPredicate(
                    path="traits[].key", operator="contains", value="trait-a"
                ),
            )
        ),
        sort=None,
        limit=10,
    )

    assert result.records == ({"name": {"ko_KR": "조건 모두 충족"}},)
    assert result.matched_count == 1


def test_query_evaluates_a_nested_any_group_inside_an_all_group() -> None:
    snapshot = TftMetaDeckSnapshot.from_payload(
        {
            "data": [
                {
                    "name": {"ko_KR": "A 특성"},
                    "stat": {"deck": {"winRate": 0.21}},
                    "traits": [{"key": "trait-a"}],
                },
                {
                    "name": {"ko_KR": "B 특성"},
                    "stat": {"deck": {"winRate": 0.22}},
                    "traits": [{"key": "trait-b"}],
                },
                {
                    "name": {"ko_KR": "낮은 승률"},
                    "stat": {"deck": {"winRate": 0.18}},
                    "traits": [{"key": "trait-a"}],
                },
                {
                    "name": {"ko_KR": "다른 특성"},
                    "stat": {"deck": {"winRate": 0.23}},
                    "traits": [{"key": "trait-c"}],
                },
            ],
            "metadata": {"gameStatDateTime": "2026-07-23T12:00:00Z"},
        },
        fetched_at=datetime(2026, 7, 23, 12, 5, tzinfo=UTC),
    )

    result = snapshot.query(
        fields=("name.ko_KR",),
        where=TftMetaDeckAll(
            conditions=(
                TftMetaDeckAny(
                    conditions=(
                        TftMetaDeckPredicate(
                            path="traits[].key",
                            operator="contains",
                            value="trait-a",
                        ),
                        TftMetaDeckPredicate(
                            path="traits[].key",
                            operator="contains",
                            value="trait-b",
                        ),
                    )
                ),
                TftMetaDeckPredicate(
                    path="stat.deck.winRate", operator="gte", value=0.2
                ),
            )
        ),
        sort=None,
        limit=10,
    )

    assert result.records == (
        {"name": {"ko_KR": "A 특성"}},
        {"name": {"ko_KR": "B 특성"}},
    )
    assert result.matched_count == 2


def test_query_sorts_only_records_with_a_comparable_sort_value() -> None:
    snapshot = TftMetaDeckSnapshot.from_payload(
        {
            "data": [
                {
                    "name": {"ko_KR": "낮은 승률"},
                    "stat": {"deck": {"winRate": 0.18}},
                },
                {"name": {"ko_KR": "값 없음"}, "stat": {"deck": {}}},
                {
                    "name": {"ko_KR": "높은 승률"},
                    "stat": {"deck": {"winRate": 0.21}},
                },
                {
                    "name": {"ko_KR": "null 승률"},
                    "stat": {"deck": {"winRate": None}},
                },
            ],
            "metadata": {"gameStatDateTime": "2026-07-23T12:00:00Z"},
        },
        fetched_at=datetime(2026, 7, 23, 12, 5, tzinfo=UTC),
    )

    result = snapshot.query(
        fields=("name.ko_KR", "stat.deck.winRate"),
        where=None,
        sort=TftMetaDeckSort(path="stat.deck.winRate", direction="desc"),
        limit=10,
    )

    assert result.records == (
        {
            "name": {"ko_KR": "높은 승률"},
            "stat": {"deck": {"winRate": 0.21}},
        },
        {
            "name": {"ko_KR": "낮은 승률"},
            "stat": {"deck": {"winRate": 0.18}},
        },
    )
    assert result.matched_count == 4
    assert result.sort_excluded_count == 2


def test_query_rejects_a_field_path_that_is_not_in_the_snapshot_schema() -> None:
    snapshot = TftMetaDeckSnapshot.from_payload(
        {
            "data": [{"name": {"ko_KR": "테스트 덱"}}],
            "metadata": {"gameStatDateTime": "2026-07-23T12:00:00Z"},
        },
        fetched_at=datetime(2026, 7, 23, 12, 5, tzinfo=UTC),
    )

    with pytest.raises(InvalidTftMetaDeckQuery) as error:
        snapshot.query(
            fields=("name.en_US",),
            where=None,
            sort=None,
            limit=10,
        )

    assert error.value.code == "INVALID_QUERY"


@pytest.mark.parametrize("limit", [0, 11])
def test_query_rejects_a_limit_outside_the_supported_range(limit: int) -> None:
    snapshot = TftMetaDeckSnapshot.from_payload(
        {
            "data": [{"name": {"ko_KR": "테스트 덱"}}],
            "metadata": {"gameStatDateTime": "2026-07-23T12:00:00Z"},
        },
        fetched_at=datetime(2026, 7, 23, 12, 5, tzinfo=UTC),
    )

    with pytest.raises(InvalidTftMetaDeckQuery):
        snapshot.query(
            fields=("name.ko_KR",),
            where=None,
            sort=None,
            limit=limit,
        )


def test_query_rejects_invalid_filter_paths_operators_and_group_complexity() -> None:
    snapshot = TftMetaDeckSnapshot.from_payload(
        {
            "data": [
                {
                    "name": {"ko_KR": "테스트 덱"},
                    "stat": {"deck": {"winRate": 0.2}},
                }
            ],
            "metadata": {"gameStatDateTime": "2026-07-23T12:00:00Z"},
        },
        fetched_at=datetime(2026, 7, 23, 12, 5, tzinfo=UTC),
    )

    invalid_conditions = (
        TftMetaDeckPredicate(path="stat.deck.unknown", operator="gte", value=0.2),
        TftMetaDeckPredicate(path="stat.deck.winRate", operator="approximately", value=0.2),
        TftMetaDeckAny(
            conditions=(
                TftMetaDeckAll(
                    conditions=(
                        TftMetaDeckAny(
                            conditions=(
                                TftMetaDeckPredicate(
                                    path="stat.deck.winRate", operator="gte", value=0.2
                                ),
                            )
                        ),
                    )
                ),
            )
        ),
    )

    for where in invalid_conditions:
        with pytest.raises(InvalidTftMetaDeckQuery) as error:
            snapshot.query(
                fields=("name.ko_KR",), where=where, sort=None, limit=10
            )

        assert error.value.code == "INVALID_QUERY"


def test_query_supports_exact_and_numeric_comparison_operators() -> None:
    snapshot = TftMetaDeckSnapshot.from_payload(
        {
            "data": [
                {"name": {"ko_KR": "A"}, "stat": {"deck": {"winRate": 0.2}}},
                {"name": {"ko_KR": "B"}, "stat": {"deck": {"winRate": 0.25}}},
            ],
            "metadata": {"gameStatDateTime": "2026-07-23T12:00:00Z"},
        },
        fetched_at=datetime(2026, 7, 23, 12, 5, tzinfo=UTC),
    )

    for operator, value, expected_names in (
        ("eq", 0.2, ("A",)),
        ("neq", 0.2, ("B",)),
        ("gt", 0.2, ("B",)),
        ("gte", 0.2, ("A", "B")),
        ("lt", 0.25, ("A",)),
        ("lte", 0.2, ("A",)),
    ):
        result = snapshot.query(
            fields=("name.ko_KR",),
            where=TftMetaDeckPredicate(
                path="stat.deck.winRate", operator=operator, value=value
            ),
            sort=None,
            limit=10,
        )

        assert result.records == tuple(
            {"name": {"ko_KR": name}} for name in expected_names
        )


def test_query_rejects_oversized_result_without_returning_partial_records() -> None:
    snapshot = TftMetaDeckSnapshot.from_payload(
        {
            "data": [{"name": {"ko_KR": "가" * 6_000}}],
            "metadata": {"gameStatDateTime": "2026-07-23T12:00:00Z"},
        },
        fetched_at=datetime(2026, 7, 23, 12, 5, tzinfo=UTC),
    )

    with pytest.raises(TftMetaDeckResultTooLarge) as error:
        snapshot.query(
            fields=("name.ko_KR",), where=None, sort=None, limit=10
        )

    assert error.value.code == "RESULT_TOO_LARGE"


@pytest.mark.asyncio
async def test_snapshot_cache_reuses_a_valid_snapshot_within_the_ttl() -> None:
    fetch_calls = 0

    async def fetch_payload() -> object:
        nonlocal fetch_calls
        fetch_calls += 1
        return {
            "data": [{"name": {"ko_KR": "테스트 덱"}}],
            "metadata": {"gameStatDateTime": "2026-07-23T12:00:00Z"},
        }

    cache = TftMetaDeckSnapshotCache(
        fetch_payload=fetch_payload,
        clock=lambda: 100.0,
        now=lambda: datetime(2026, 7, 23, 12, 5, tzinfo=UTC),
    )

    first = await cache.get_snapshot()
    second = await cache.get_snapshot()

    assert first is second
    assert fetch_calls == 1


@pytest.mark.asyncio
async def test_snapshot_cache_refreshes_when_the_five_minute_ttl_expires() -> None:
    clock_value = 0.0
    fetch_calls = 0

    async def fetch_payload() -> object:
        nonlocal fetch_calls
        fetch_calls += 1
        return {
            "data": [{"name": {"ko_KR": f"테스트 덱 {fetch_calls}"}}],
            "metadata": {"gameStatDateTime": "2026-07-23T12:00:00Z"},
        }

    cache = TftMetaDeckSnapshotCache(
        fetch_payload=fetch_payload,
        clock=lambda: clock_value,
        now=lambda: datetime(2026, 7, 23, 12, 5, tzinfo=UTC),
    )

    first = await cache.get_snapshot()
    clock_value = 300.0
    second = await cache.get_snapshot()

    assert first is not second
    assert second.records[0]["name"] == {"ko_KR": "테스트 덱 2"}
    assert fetch_calls == 2


@pytest.mark.asyncio
async def test_snapshot_cache_does_not_return_stale_data_after_refresh_failure() -> None:
    clock_value = 0.0
    fetch_calls = 0

    async def fetch_payload() -> object:
        nonlocal fetch_calls
        fetch_calls += 1
        if fetch_calls == 1:
            return {
                "data": [{"name": {"ko_KR": "이전 덱"}}],
                "metadata": {"gameStatDateTime": "2026-07-23T12:00:00Z"},
            }
        raise RuntimeError("upstream unavailable")

    cache = TftMetaDeckSnapshotCache(
        fetch_payload=fetch_payload,
        clock=lambda: clock_value,
        now=lambda: datetime(2026, 7, 23, 12, 5, tzinfo=UTC),
    )

    await cache.get_snapshot()
    clock_value = 300.0

    with pytest.raises(TftMetaDeckUpstreamUnavailable) as error:
        await cache.get_snapshot()

    assert error.value.code == "UPSTREAM_UNAVAILABLE"
    assert fetch_calls == 2
