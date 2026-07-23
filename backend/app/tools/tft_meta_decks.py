import asyncio
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from http import HTTPStatus
from time import monotonic
from collections.abc import Awaitable, Callable
from typing import Any, Protocol, TypeGuard


class _Missing:
    def __repr__(self) -> str:
        return "MISSING"


MISSING = _Missing()


class InvalidTftMetaDeckResponse(Exception):
    code = "UPSTREAM_INVALID_RESPONSE"


class InvalidTftMetaDeckQuery(Exception):
    code = "INVALID_QUERY"


class TftMetaDeckResultTooLarge(Exception):
    code = "RESULT_TOO_LARGE"


class TftMetaDeckUpstreamUnavailable(Exception):
    code = "UPSTREAM_UNAVAILABLE"


class TftMetaDeckUpstreamTimeout(Exception):
    code = "UPSTREAM_TIMEOUT"


MAX_QUERY_FIELDS = 12
MAX_QUERY_LEAF_CONDITIONS = 8
MAX_QUERY_GROUP_DEPTH = 2
MAX_QUERY_RESULT_BYTES = 16 * 1024


class TftMetaDeckMcpClient(Protocol):
    async def call_tool(
        self, name: str, arguments: dict[str, Any] | None = None
    ) -> object: ...


async def fetch_opgg_tft_meta_decks(client: TftMetaDeckMcpClient) -> object:
    """Fetch the one allowlisted OP.GG MCP response as a JSON object."""
    try:
        result = await client.call_tool("tft_list_meta_decks", {})
    except TimeoutError:
        raise TftMetaDeckUpstreamTimeout("The TFT data service timed out.") from None
    except Exception as error:
        error_data = getattr(error, "error", None)
        if getattr(error_data, "code", None) == HTTPStatus.REQUEST_TIMEOUT:
            raise TftMetaDeckUpstreamTimeout(
                "The TFT data service timed out."
            ) from None
        raise TftMetaDeckUpstreamUnavailable(
            "The TFT data service is temporarily unavailable."
        ) from None

    if getattr(result, "is_error", False):
        raise TftMetaDeckUpstreamUnavailable(
            "The TFT data service is temporarily unavailable."
        )

    for value in (
        getattr(result, "data", None),
        getattr(result, "structured_content", None),
    ):
        if isinstance(value, Mapping):
            return dict(value)

    content = getattr(result, "content", None)
    if not isinstance(content, list) or len(content) != 1:
        raise InvalidTftMetaDeckResponse(
            "TFT meta-deck tool did not return one structured response."
        )

    text = getattr(content[0], "text", None)
    if not isinstance(text, str):
        raise InvalidTftMetaDeckResponse(
            "TFT meta-deck tool did not return JSON text."
        )

    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        raise InvalidTftMetaDeckResponse(
            "TFT meta-deck tool returned invalid JSON."
        ) from None

    if not isinstance(payload, Mapping):
        raise InvalidTftMetaDeckResponse(
            "TFT meta-deck tool must return a JSON object."
        )
    return dict(payload)


@dataclass(frozen=True, slots=True)
class FieldDescription:
    path: str
    type: str
    present_count: int


@dataclass(frozen=True, slots=True)
class TftMetaDeckQueryResult:
    records: tuple[dict[str, object], ...]
    matched_count: int
    sort_excluded_count: int
    data_as_of: datetime
    fetched_at: datetime

    def to_payload(self) -> dict[str, object]:
        return {
            "records": list(self.records),
            "matched_count": self.matched_count,
            "sort_excluded_count": self.sort_excluded_count,
            "data_as_of": self.data_as_of.isoformat(),
            "fetched_at": self.fetched_at.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class TftMetaDeckPredicate:
    path: str
    operator: str
    value: object


@dataclass(frozen=True, slots=True)
class TftMetaDeckAll:
    conditions: tuple[object, ...]


@dataclass(frozen=True, slots=True)
class TftMetaDeckAny:
    conditions: tuple[object, ...]


@dataclass(frozen=True, slots=True)
class TftMetaDeckSort:
    path: str
    direction: str


def resolve_field_path(value: object, path: str) -> tuple[object, ...]:
    return _resolve_path(value, tuple(path.split(".")))


def _resolve_path(value: object, segments: tuple[str, ...]) -> tuple[object, ...]:
    if not segments:
        return (value,)

    segment, *remaining_segments = segments
    expects_array = segment.endswith("[]")
    key = segment.removesuffix("[]")
    if not isinstance(value, Mapping) or not key:
        return (MISSING,)

    child = value.get(key, MISSING)
    if child is MISSING:
        return (MISSING,)

    remaining = tuple(remaining_segments)
    if not expects_array:
        return _resolve_path(child, remaining)
    if not isinstance(child, list):
        return (MISSING,)

    resolved: list[object] = []
    for item in child:
        resolved.extend(_resolve_path(item, remaining))
    return tuple(resolved)


@dataclass(frozen=True, slots=True)
class TftMetaDeckSnapshot:
    records: tuple[dict[str, object], ...]
    data_as_of: datetime
    fetched_at: datetime

    @classmethod
    def from_payload(
        cls, payload: object, *, fetched_at: datetime
    ) -> "TftMetaDeckSnapshot":
        if not isinstance(payload, Mapping):
            raise InvalidTftMetaDeckResponse(
                "TFT meta-deck payload must be an object."
            )

        data = payload.get("data")
        metadata = payload.get("metadata")
        if not isinstance(data, list) or not isinstance(metadata, Mapping):
            raise InvalidTftMetaDeckResponse(
                "TFT meta-deck payload has an invalid shape."
            )

        records: list[dict[str, object]] = []
        for record in data:
            if not isinstance(record, Mapping):
                raise InvalidTftMetaDeckResponse(
                    "TFT meta-deck records must be objects."
                )
            records.append(dict(record))

        raw_data_as_of = metadata.get("gameStatDateTime")
        if not isinstance(raw_data_as_of, str):
            raise InvalidTftMetaDeckResponse(
                "TFT meta-deck payload has no data timestamp."
            )

        try:
            data_as_of = datetime.fromisoformat(raw_data_as_of)
        except ValueError:
            raise InvalidTftMetaDeckResponse(
                "TFT meta-deck data timestamp is invalid."
            ) from None

        return cls(
            records=tuple(records),
            data_as_of=data_as_of,
            fetched_at=fetched_at,
        )

    def describe_fields(self) -> tuple[FieldDescription, ...]:
        types_by_path: dict[str, set[str]] = {}
        present_counts: dict[str, int] = {}

        for record in self.records:
            record_fields = self._describe_value(record, "")
            for path, value_type in record_fields:
                types_by_path.setdefault(path, set()).add(value_type)
                present_counts[path] = present_counts.get(path, 0) + 1

        return tuple(
            FieldDescription(
                path=path,
                type=next(iter(value_types))
                if len(value_types) == 1
                else "mixed",
                present_count=present_counts[path],
            )
            for path, value_types in sorted(types_by_path.items())
        )

    def query(
        self,
        *,
        fields: tuple[str, ...],
        where: object | None,
        sort: TftMetaDeckSort | None,
        limit: int,
    ) -> TftMetaDeckQueryResult:
        available_paths = {field.path for field in self.describe_fields()}
        self._validate_query(
            fields=fields,
            where=where,
            sort=sort,
            limit=limit,
            available_paths=available_paths,
        )

        filtered_records = tuple(
            record
            for record in self.records
            if where is None or self._matches_condition(record, where)
        )
        matched_count = len(filtered_records)
        matched_records = filtered_records
        sort_excluded_count = 0
        if sort is not None:
            sortable_records: list[tuple[dict[str, object], int | float]] = []
            for record in matched_records:
                values = resolve_field_path(record, sort.path)
                if len(values) != 1:
                    sort_excluded_count += 1
                    continue
                value = values[0]
                if isinstance(value, bool) or not isinstance(value, int | float):
                    sort_excluded_count += 1
                    continue
                sortable_records.append((record, value))
            matched_records = tuple(
                record
                for record, _ in sorted(
                    sortable_records,
                    key=lambda sortable_record: sortable_record[1],
                    reverse=sort.direction == "desc",
                )
            )
        result = TftMetaDeckQueryResult(
            records=tuple(
                self._project_fields(record, fields)
                for record in matched_records[:limit]
            ),
            matched_count=matched_count,
            sort_excluded_count=sort_excluded_count,
            data_as_of=self.data_as_of,
            fetched_at=self.fetched_at,
        )
        payload_bytes = len(
            json.dumps(
                result.to_payload(), ensure_ascii=False, separators=(",", ":")
            ).encode("utf-8")
        )
        if payload_bytes > MAX_QUERY_RESULT_BYTES:
            raise TftMetaDeckResultTooLarge(
                "The query result exceeds the supported response size."
            )
        return result

    @classmethod
    def _validate_query(
        cls,
        *,
        fields: tuple[str, ...],
        where: object | None,
        sort: TftMetaDeckSort | None,
        limit: int,
        available_paths: set[str],
    ) -> None:
        if not 1 <= limit <= 10:
            raise InvalidTftMetaDeckQuery("The query limit must be between 1 and 10.")
        if not 1 <= len(fields) <= MAX_QUERY_FIELDS or len(set(fields)) != len(fields):
            raise InvalidTftMetaDeckQuery(
                "The query must request between one and twelve unique fields."
            )
        if any(field not in available_paths for field in fields):
            raise InvalidTftMetaDeckQuery("A requested field path is not available.")

        if where is not None:
            leaf_count = cls._validate_condition(where, available_paths, group_depth=0)
            if leaf_count > MAX_QUERY_LEAF_CONDITIONS:
                raise InvalidTftMetaDeckQuery("The query has too many leaf conditions.")

        if sort is not None:
            if sort.path not in available_paths:
                raise InvalidTftMetaDeckQuery("The sort field path is not available.")
            if sort.direction not in {"asc", "desc"}:
                raise InvalidTftMetaDeckQuery("The sort direction must be asc or desc.")

    @classmethod
    def _validate_condition(
        cls,
        condition: object,
        available_paths: set[str],
        *,
        group_depth: int,
    ) -> int:
        if isinstance(condition, TftMetaDeckPredicate):
            if condition.path not in available_paths:
                raise InvalidTftMetaDeckQuery("The filter field path is not available.")
            if condition.operator not in {
                "eq",
                "neq",
                "gt",
                "gte",
                "lt",
                "lte",
                "contains",
                "not_contains",
            }:
                raise InvalidTftMetaDeckQuery("The filter operator is not supported.")
            if condition.operator in {"gt", "gte", "lt", "lte"} and not cls._is_number(
                condition.value
            ):
                raise InvalidTftMetaDeckQuery(
                    "Numeric filter operators require a numeric value."
                )
            return 1

        if not isinstance(condition, TftMetaDeckAll | TftMetaDeckAny):
            raise InvalidTftMetaDeckQuery("The filter condition has an invalid shape.")
        if group_depth >= MAX_QUERY_GROUP_DEPTH:
            raise InvalidTftMetaDeckQuery("The filter condition is nested too deeply.")
        if not condition.conditions:
            raise InvalidTftMetaDeckQuery("A filter condition group cannot be empty.")
        return sum(
            cls._validate_condition(
                child, available_paths, group_depth=group_depth + 1
            )
            for child in condition.conditions
        )

    @classmethod
    def _matches_condition(cls, record: Mapping[str, object], condition: object) -> bool:
        if isinstance(condition, TftMetaDeckPredicate):
            return cls._matches_predicate(record, condition)
        if isinstance(condition, TftMetaDeckAll):
            return all(
                cls._matches_condition(record, child)
                for child in condition.conditions
            )
        if isinstance(condition, TftMetaDeckAny):
            return any(
                cls._matches_condition(record, child)
                for child in condition.conditions
            )
        return False

    @staticmethod
    def _matches_predicate(
        record: Mapping[str, object], predicate: TftMetaDeckPredicate
    ) -> bool:
        values = resolve_field_path(record, predicate.path)
        known_values = tuple(
            value for value in values if value is not MISSING and value is not None
        )
        if predicate.operator == "eq":
            return any(value == predicate.value for value in known_values)
        if predicate.operator == "neq":
            return bool(known_values) and len(known_values) == len(values) and all(
                value != predicate.value for value in known_values
            )
        if predicate.operator == "contains":
            return any(value == predicate.value for value in known_values)
        if predicate.operator == "not_contains":
            return not any(
                value is MISSING or value is None for value in values
            ) and all(value != predicate.value for value in values)
        threshold = predicate.value
        if not TftMetaDeckSnapshot._is_number(threshold):
            return False
        numeric_values = tuple(
            value for value in known_values if TftMetaDeckSnapshot._is_number(value)
        )
        if predicate.operator == "gt":
            return any(value > threshold for value in numeric_values)
        if predicate.operator == "gte":
            return any(value >= threshold for value in numeric_values)
        if predicate.operator == "lt":
            return any(value < threshold for value in numeric_values)
        if predicate.operator == "lte":
            return any(value <= threshold for value in numeric_values)
        return False

    @classmethod
    def _project_fields(
        cls, record: Mapping[str, object], fields: tuple[str, ...]
    ) -> dict[str, object]:
        projection: dict[str, object] = {}
        for field in fields:
            cls._project_path(record, projection, tuple(field.split(".")))
        return projection

    @classmethod
    def _project_path(
        cls,
        source: object,
        projection: dict[str, object],
        segments: tuple[str, ...],
    ) -> None:
        if not segments or not isinstance(source, Mapping):
            return

        segment, *remaining_segments = segments
        expects_array = segment.endswith("[]")
        key = segment.removesuffix("[]")
        child = source.get(key, MISSING)
        if child is MISSING or not key:
            return

        remaining = tuple(remaining_segments)
        if not expects_array:
            if not remaining:
                projection[key] = child
                return

            nested_projection = projection.get(key)
            if not isinstance(nested_projection, dict):
                nested_projection = {}
                projection[key] = nested_projection
            cls._project_path(child, nested_projection, remaining)
            return

        if not isinstance(child, list):
            return
        if not remaining:
            projection[key] = list(child)
            return

        nested_projection = projection.get(key)
        if not isinstance(nested_projection, list):
            nested_projection = []
            projection[key] = nested_projection
        for index, item in enumerate(child):
            while len(nested_projection) <= index:
                nested_projection.append({})
            item_projection = nested_projection[index]
            if not isinstance(item_projection, dict):
                item_projection = {}
                nested_projection[index] = item_projection
            cls._project_path(item, item_projection, remaining)

    @classmethod
    def _describe_value(cls, value: object, path: str) -> set[tuple[str, str]]:
        if isinstance(value, Mapping):
            fields: set[tuple[str, str]] = set()
            for key, nested_value in value.items():
                if not isinstance(key, str):
                    continue
                nested_path = f"{path}.{key}" if path else key
                fields.update(cls._describe_value(nested_value, nested_path))
            return fields

        if isinstance(value, list):
            fields = set()
            for item in value:
                fields.update(cls._describe_value(item, f"{path}[]"))
            return fields

        return {(path, cls._value_type(value))}

    @staticmethod
    def _value_type(value: object) -> str:
        if value is None:
            return "null"
        if isinstance(value, bool):
            return "boolean"
        if isinstance(value, int | float):
            return "number"
        if isinstance(value, str):
            return "string"
        return "unknown"

    @staticmethod
    def _is_number(value: object) -> TypeGuard[int | float]:
        return not isinstance(value, bool) and isinstance(value, int | float)


class TftMetaDeckSnapshotCache:
    def __init__(
        self,
        *,
        fetch_payload: Callable[[], Awaitable[object]],
        ttl_seconds: float = 300.0,
        clock: Callable[[], float] = monotonic,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._fetch_payload = fetch_payload
        self._ttl_seconds = ttl_seconds
        self._clock = clock
        self._now = now
        self._snapshot: TftMetaDeckSnapshot | None = None
        self._expires_at = 0.0
        self._lock = asyncio.Lock()

    async def get_snapshot(self) -> TftMetaDeckSnapshot:
        snapshot = self._snapshot
        if snapshot is not None and self._clock() < self._expires_at:
            return snapshot

        async with self._lock:
            snapshot = self._snapshot
            if snapshot is not None and self._clock() < self._expires_at:
                return snapshot

            try:
                payload = await self._fetch_payload()
            except (
                InvalidTftMetaDeckResponse,
                TftMetaDeckUpstreamTimeout,
                TftMetaDeckUpstreamUnavailable,
            ):
                raise
            except Exception:
                raise TftMetaDeckUpstreamUnavailable(
                    "The TFT data service is temporarily unavailable."
                ) from None
            snapshot = TftMetaDeckSnapshot.from_payload(
                payload, fetched_at=self._now()
            )
            self._snapshot = snapshot
            self._expires_at = self._clock() + self._ttl_seconds
            return snapshot
