"""Normalize JSON-boundary values used by orchestration contracts.

Private helpers enforce closed vocabularies, non-empty identifiers, finite
numbers, timestamps, mappings, and sequences before immutable domain objects are
created. They have no persistence or workflow-execution side effects.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import datetime
from enum import Enum
from typing import Any, TypeVar

from ..handoffs import ArtifactReportRef


ContractValue = TypeVar("ContractValue")
EnumValue = TypeVar("EnumValue", bound=Enum)

def _validate_ref_type(
    reference: ArtifactReportRef,
    artifact_type: str,
    label: str,
) -> None:
    if reference.artifact_type != artifact_type:
        raise ValueError(f"{label} ref must have artifact type {artifact_type}")


def _validate_payload_artifact_type(
    payload: Mapping[str, Any],
    expected: str,
) -> None:
    artifact_type = payload.get("artifact_type")
    if artifact_type is not None and artifact_type != expected:
        raise ValueError(
            f"artifact_type {artifact_type} does not match expected {expected}"
        )


def _required_text(value: str, label: str) -> None:
    if not value.strip():
        raise ValueError(f"{label} is required")


def _required_text_sequence(
    values: Sequence[str],
    label: str,
    *,
    allow_empty: bool = False,
) -> None:
    if not values and not allow_empty:
        raise ValueError(f"{label} are required")
    for value in values:
        _required_text(value, label)


def _validate_text_mapping(values: Mapping[str, str], label: str) -> None:
    for key, value in values.items():
        _required_text(str(key), f"{label} key")
        _required_text(str(value), f"{label} value")


def _unique(values: Iterable[str], label: str) -> None:
    materialized = list(values)
    if len(materialized) != len(set(materialized)):
        raise ValueError(f"{label} must be unique")


def _index_unique(
    values: Sequence[ContractValue],
    key: Callable[[ContractValue], str],
    label: str,
) -> dict[str, ContractValue]:
    result: dict[str, ContractValue] = {}
    for item in values:
        item_key = key(item)
        if item_key in result:
            raise ValueError(f"{label} must be unique")
        result[item_key] = item
    return result


def _enum_value(
    enum_type: type[EnumValue],
    value: object,
    label: str,
) -> EnumValue:
    try:
        return enum_type(str(value))
    except ValueError as exc:
        raise ValueError(f"unsupported {label}: {value}") from exc


def _number(value: object) -> int | float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"expected numeric value, got {value!r}")
    return value


def _parse_timestamp(value: str, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{label} must include a timezone")
    return parsed


def _mapping(value: object) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return {}


def _sequence(value: object) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return value
    return ()


def _mapping_sequence(value: object) -> tuple[Mapping[str, Any], ...]:
    return tuple(item for item in _sequence(value) if isinstance(item, Mapping))


def _text_tuple(value: object) -> tuple[str, ...]:
    return tuple(str(item) for item in _sequence(value))


def _text_mapping(value: object) -> Mapping[str, str]:
    return {str(key): str(item) for key, item in _mapping(value).items()}


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
