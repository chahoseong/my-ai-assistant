from typing import Literal, Never, Self

from pydantic import BaseModel, ConfigDict, JsonValue, model_validator
from pydantic_ai import ModelRetry

from app.tools.tft_meta_decks import (
    InvalidTftMetaDeckQuery,
    InvalidTftMetaDeckResponse,
    TftMetaDeckAll,
    TftMetaDeckAny,
    TftMetaDeckPredicate,
    TftMetaDeckResultTooLarge,
    TftMetaDeckSnapshotCache,
    TftMetaDeckSort,
    TftMetaDeckUpstreamUnavailable,
    TftMetaDeckUpstreamTimeout,
)


class TftMetaDeckWhereInput(BaseModel):
    """One leaf predicate or one all/any condition group."""

    model_config = ConfigDict(extra="forbid")

    path: str | None = None
    operator: Literal[
        "eq", "neq", "gt", "gte", "lt", "lte", "contains", "not_contains"
    ] | None = None
    value: JsonValue | None = None
    all: list[Self] | None = None
    any: list[Self] | None = None

    @model_validator(mode="after")
    def requires_one_condition_shape(self) -> Self:
        fields = self.model_fields_set
        predicate_fields = {"path", "operator", "value"}
        if fields == predicate_fields:
            return self
        if fields == {"all"} and self.all is not None:
            return self
        if fields == {"any"} and self.any is not None:
            return self
        raise ValueError(
            "A condition must be exactly a predicate, an all group, or an any group."
        )

    def to_domain_condition(self) -> TftMetaDeckPredicate | TftMetaDeckAll | TftMetaDeckAny:
        if self.all is not None:
            return TftMetaDeckAll(
                conditions=tuple(child.to_domain_condition() for child in self.all)
            )
        if self.any is not None:
            return TftMetaDeckAny(
                conditions=tuple(child.to_domain_condition() for child in self.any)
            )
        assert self.path is not None
        assert self.operator is not None
        return TftMetaDeckPredicate(
            path=self.path, operator=self.operator, value=self.value
        )


class TftMetaDeckSortInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    direction: Literal["asc", "desc"]

    def to_domain_sort(self) -> TftMetaDeckSort:
        return TftMetaDeckSort(path=self.path, direction=self.direction)


class TftMetaDeckTools:
    def __init__(self, snapshot_cache: TftMetaDeckSnapshotCache) -> None:
        self._snapshot_cache = snapshot_cache

    async def tft_describe_meta_decks(self) -> dict[str, object]:
        """Return current TFT meta-deck field paths and types, never their values."""
        try:
            snapshot = await self._snapshot_cache.get_snapshot()
        except (
            InvalidTftMetaDeckResponse,
            TftMetaDeckUpstreamTimeout,
            TftMetaDeckUpstreamUnavailable,
        ) as error:
            self._raise_model_retry(error)

        return {
            "record_count": len(snapshot.records),
            "data_as_of": snapshot.data_as_of.isoformat(),
            "fetched_at": snapshot.fetched_at.isoformat(),
            "fields": [
                {
                    "path": field.path,
                    "type": field.type,
                    "present_count": field.present_count,
                }
                for field in snapshot.describe_fields()
            ],
        }

    async def tft_query_meta_decks(
        self,
        fields: list[str],
        where: TftMetaDeckWhereInput | None = None,
        sort: TftMetaDeckSortInput | None = None,
        limit: int = 10,
    ) -> dict[str, object]:
        """Query the current TFT meta-deck snapshot with exact field paths and filters."""
        try:
            snapshot = await self._snapshot_cache.get_snapshot()
            result = snapshot.query(
                fields=tuple(fields),
                where=where.to_domain_condition() if where is not None else None,
                sort=sort.to_domain_sort() if sort is not None else None,
                limit=limit,
            )
        except (
            InvalidTftMetaDeckQuery,
            InvalidTftMetaDeckResponse,
            TftMetaDeckResultTooLarge,
            TftMetaDeckUpstreamTimeout,
            TftMetaDeckUpstreamUnavailable,
        ) as error:
            self._raise_model_retry(error)
        return result.to_payload()

    @staticmethod
    def _raise_model_retry(
        error: InvalidTftMetaDeckQuery
        | InvalidTftMetaDeckResponse
        | TftMetaDeckResultTooLarge
        | TftMetaDeckUpstreamTimeout
        | TftMetaDeckUpstreamUnavailable,
    ) -> Never:
        raise ModelRetry(f"{error.code}: Retry with a corrected or smaller request.")
