from datetime import UTC, datetime

import pytest
from pydantic_ai import ModelRetry

from app.tools.tft_meta_deck_tools import (
    TftMetaDeckSortInput,
    TftMetaDeckTools,
    TftMetaDeckWhereInput,
)
from app.tools.tft_meta_decks import TftMetaDeckSnapshotCache


pytestmark = pytest.mark.unit


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
