from collections.abc import Awaitable, Callable
from time import perf_counter
from typing import Literal, Never, Self

from pydantic import BaseModel, ConfigDict, JsonValue, model_validator
from pydantic_ai import ModelRetry

from app.observability.logging import get_logger
from app.observability.metrics import record_agent_tool_call
from app.tools.tft_meta_decks import (
    FieldDescription,
    InvalidTftMetaDeckQuery,
    InvalidTftMetaDeckResponse,
    TftMetaDeckAll,
    TftMetaDeckAny,
    TftMetaDeckPredicate,
    TftMetaDeckResultTooLarge,
    TftMetaDeckSnapshot,
    TftMetaDeckSnapshotCache,
    TftMetaDeckSort,
    TftMetaDeckUpstreamUnavailable,
    TftMetaDeckUpstreamTimeout,
)

logger = get_logger(__name__)

TFT_DESCRIBE_FIRST_RETRY_INSTRUCTION = (
    "Call tft_describe_meta_decks first, then use only exact returned field paths."
)
KOREAN_DECK_NAME_PATH = "name.ko_KR"
DECK_NAME_PATH_PREFIX = "name."
_SAFE_INVALID_QUERY_REASONS = frozenset(
    {
        "The query limit must be between 1 and 10.",
        "The query must request between one and twelve unique fields.",
        "A requested field path is not available.",
        "The query has too many leaf conditions.",
        "The sort field path is not available.",
        "The sort direction must be asc or desc.",
        "The filter field path is not available.",
        "The filter operator is not supported.",
        "Numeric filter operators require a numeric value.",
        "The filter condition has an invalid shape.",
        "The filter condition is nested too deeply.",
        "A filter condition group cannot be empty.",
    }
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


class TftMetaDeckTools:
    def __init__(self, snapshot_cache: TftMetaDeckSnapshotCache) -> None:
        self._snapshot_cache = snapshot_cache

    async def tft_describe_meta_decks(self) -> dict[str, object]:
        """Return field paths and types before tft_query_meta_decks, never values."""
        return await self._run_observed(
            tool_name="tft_describe_meta_decks",
            operation=self._describe_meta_decks,
        )

    async def tft_query_meta_decks(
        self,
        fields: list[str],
        where: TftMetaDeckWhereInput | None = None,
        sort_path: str | None = None,
        sort_direction: Literal["asc", "desc"] = "desc",
        limit: int = 10,
    ) -> dict[str, object]:
        """Query exact returned field paths after describing; use name.ko_KR and sort_path."""
        return await self._run_observed(
            tool_name="tft_query_meta_decks",
            operation=lambda: self._query_meta_decks(
                fields, where, sort_path, sort_direction, limit
            ),
        )

    async def _describe_meta_decks(self) -> dict[str, object]:
        snapshot = await self._snapshot_cache.get_snapshot()
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
                for field in self._public_field_descriptions(snapshot)
            ],
        }

    async def _query_meta_decks(
        self,
        fields: list[str],
        where: TftMetaDeckWhereInput | None,
        sort_path: str | None,
        sort_direction: Literal["asc", "desc"],
        limit: int,
    ) -> dict[str, object]:
        snapshot = await self._snapshot_cache.get_snapshot()
        legacy_name_aliases = self._legacy_name_field_aliases(snapshot)
        public_paths = {
            field.path for field in self._public_field_descriptions(snapshot)
        }
        result = snapshot.query(
            fields=tuple(legacy_name_aliases.get(field, field) for field in fields),
            where=where.to_domain_condition() if where is not None else None,
            sort=(
                TftMetaDeckSort(path=sort_path, direction=sort_direction)
                if sort_path is not None
                else None
            ),
            limit=limit,
            allowed_paths=public_paths,
        )
        return result.to_payload()

    @staticmethod
    def _public_field_descriptions(
        snapshot: TftMetaDeckSnapshot,
    ) -> tuple[FieldDescription, ...]:
        return tuple(
            field
            for field in snapshot.describe_fields()
            if field.path == KOREAN_DECK_NAME_PATH
            or not field.path.startswith(DECK_NAME_PATH_PREFIX)
        )

    @staticmethod
    def _legacy_name_field_aliases(snapshot: TftMetaDeckSnapshot) -> dict[str, str]:
        raw_paths = {field.path for field in snapshot.describe_fields()}
        if KOREAN_DECK_NAME_PATH not in raw_paths:
            return {}
        return {
            path: KOREAN_DECK_NAME_PATH
            for path in raw_paths
            if path.startswith(DECK_NAME_PATH_PREFIX)
            and path != KOREAN_DECK_NAME_PATH
        }

    async def _run_observed(
        self,
        *,
        tool_name: str,
        operation: Callable[[], Awaitable[dict[str, object]]],
    ) -> dict[str, object]:
        started_at = perf_counter()
        outcome = "failed"
        error_type: str | None = None
        try:
            result = await operation()
            outcome = "success"
            return result
        except (InvalidTftMetaDeckQuery, TftMetaDeckResultTooLarge) as error:
            outcome = "denied"
            error_type = type(error).__name__
            self._raise_model_retry(error)
        except TftMetaDeckUpstreamTimeout as error:
            outcome = "timeout"
            error_type = type(error).__name__
            self._raise_model_retry(error)
        except (InvalidTftMetaDeckResponse, TftMetaDeckUpstreamUnavailable) as error:
            error_type = type(error).__name__
            self._raise_model_retry(error)
        except Exception as error:
            error_type = type(error).__name__
            raise
        finally:
            duration_seconds = perf_counter() - started_at
            if outcome != "success" and error_type is not None:
                logger.warning(
                    "agent_tool_call_failed",
                    tool_name=tool_name,
                    outcome=outcome,
                    error_type=error_type,
                    duration_ms=duration_seconds * 1_000,
                )
            record_agent_tool_call(
                tool_name=tool_name,
                outcome=outcome,
                duration_seconds=duration_seconds,
            )

    @staticmethod
    def _raise_model_retry(
        error: InvalidTftMetaDeckQuery
        | InvalidTftMetaDeckResponse
        | TftMetaDeckResultTooLarge
        | TftMetaDeckUpstreamTimeout
        | TftMetaDeckUpstreamUnavailable,
    ) -> Never:
        if isinstance(error, InvalidTftMetaDeckQuery):
            reason = str(error)
            safe_reason = (
                reason
                if reason in _SAFE_INVALID_QUERY_REASONS
                else "The query parameters are invalid."
            )
            raise ModelRetry(
                f"{error.code}: {safe_reason} "
                f"{TFT_DESCRIBE_FIRST_RETRY_INSTRUCTION}"
            )
        raise ModelRetry(f"{error.code}: Retry with a corrected or smaller request.")
