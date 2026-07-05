"""Pure value normalization helpers for event-store adapters."""

from __future__ import annotations

import json
from typing import Mapping, Sequence


EXPERIMENT_RUN_FIELDS: tuple[str, ...] = (
    "experiment_run_id",
    "experiment_id",
    "run_id",
    "status",
    "created_at",
    "finished_at",
    "strategy_id",
    "strategy_name",
    "strategy_version",
    "symbols",
    "asset_class",
    "timeframe",
    "start_ts",
    "end_ts",
    "parameters",
    "assumptions",
    "provenance",
    "data_quality",
    "result_summary",
    "artifact_dir",
    "error_message",
)
"""Column order returned by the experiment-run listing query."""


def json_payload_or_none(value: object | None) -> str | None:
    """Serialize an optional JSON payload using stable event-store defaults."""
    if value is None:
        return None
    return json.dumps(value, default=str)


def json_payload_or_empty(value: Mapping[str, object] | None) -> str:
    """Serialize a mapping payload, using an empty JSON object when absent."""
    return json.dumps(value or {}, default=str)


def postgres_text_array_or_none(values: Sequence[str] | None) -> list[str] | None:
    """Normalize optional symbol/tag sequences for Postgres text-array fields."""
    if values is None:
        return None
    return list(values)


def postgres_text_array_or_empty(values: Sequence[str] | None) -> list[str]:
    """Normalize optional symbol/tag sequences to a non-null Postgres text array."""
    return list(values or ())


def experiment_run_row_to_record(row: Sequence[object]) -> Mapping[str, object]:
    """Map an experiment-run row into the public dictionary shape."""
    return dict(zip(EXPERIMENT_RUN_FIELDS, row))


__all__ = [
    "EXPERIMENT_RUN_FIELDS",
    "experiment_run_row_to_record",
    "json_payload_or_empty",
    "json_payload_or_none",
    "postgres_text_array_or_empty",
    "postgres_text_array_or_none",
]
