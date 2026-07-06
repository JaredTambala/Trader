"""Pure value normalization helpers for event-store adapters."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Mapping, Sequence

from .schema import BAR_EVENT_TABLES, POSTGRES_EVENT_TABLES
from .statements import LIST_EXPERIMENT_RUNS_SQL


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


@dataclass(frozen=True)
class PostgresEventInsertPlan:
    """Validated append-only event insert plan for Postgres adapters.

    Attributes:
        event_type: Target Postgres event table.
        columns: Payload columns in caller-provided insertion order.
        values: Payload values aligned to `columns`.
        ignore_bar_conflicts: Whether bar idempotency conflict handling applies.
    """

    event_type: str
    columns: tuple[str, ...]
    values: tuple[object, ...]
    ignore_bar_conflicts: bool


@dataclass(frozen=True)
class PostgresQueryPlan:
    """Parameterized Postgres query prepared for adapter execution.

    Attributes:
        query: SQL text with psycopg placeholders.
        parameters: Query parameters aligned to placeholders.
    """

    query: str
    parameters: tuple[object, ...]


def build_postgres_event_insert_plan(
    event_type: str,
    payload: Mapping[str, object],
) -> PostgresEventInsertPlan:
    """Validate and normalize one generic Postgres event insert.

    Args:
        event_type: Requested event table name.
        payload: Event payload mapping. Key order is preserved for SQL column
            and value alignment.

    Returns:
        Insert plan consumed by the Postgres adapter shell.

    Raises:
        ValueError: If `event_type` is not part of the supported schema.
    """
    if event_type not in POSTGRES_EVENT_TABLES:
        raise ValueError(f"Unknown event type: {event_type}")
    return PostgresEventInsertPlan(
        event_type=event_type,
        columns=tuple(payload.keys()),
        values=tuple(payload.values()),
        ignore_bar_conflicts=event_type in BAR_EVENT_TABLES,
    )


def list_experiment_runs_query_plan(
    experiment_id: str,
    *,
    limit: int | None = None,
) -> PostgresQueryPlan:
    """Return the query and parameters for listing experiment runs."""
    if limit is None:
        return PostgresQueryPlan(LIST_EXPERIMENT_RUNS_SQL, (experiment_id,))
    return PostgresQueryPlan(
        LIST_EXPERIMENT_RUNS_SQL + " LIMIT %s",
        (experiment_id, limit),
    )


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


def run_session_start_parameters(
    *,
    run_id: str,
    run_type: str,
    started_at: object,
    status: str,
    config_snapshot: object | None,
    mode: str | None,
    symbols: Sequence[str] | None,
    timeframe: str | None,
    start_ts: object | None,
    end_ts: object | None,
) -> list[object]:
    """Return SQL parameters for the run-session start statement."""
    return [
        run_id,
        run_type,
        started_at,
        status,
        None,
        json_payload_or_none(config_snapshot),
        mode,
        postgres_text_array_or_none(symbols),
        timeframe,
        start_ts,
        end_ts,
    ]


def trading_session_start_parameters(
    *,
    run_id: str,
    strategy_id: str | None,
    started_at: object,
    status: str,
    config_snapshot: object | None,
    mode: str | None,
    symbols: Sequence[str] | None,
    timeframe: str | None,
    start_ts: object | None,
    end_ts: object | None,
) -> list[object]:
    """Return SQL parameters for the trading-session start statement."""
    return [
        run_id,
        strategy_id,
        started_at,
        status,
        None,
        json_payload_or_none(config_snapshot),
        mode,
        postgres_text_array_or_none(symbols),
        timeframe,
        start_ts,
        end_ts,
    ]


def run_session_finish_parameters(
    *,
    run_id: str,
    run_type: str,
    started_at: object,
    finished_at: object,
    status: str,
    error_message: str | None,
    config_snapshot: object | None,
    mode: str | None,
    symbols: Sequence[str] | None,
    timeframe: str | None,
    start_ts: object | None,
    end_ts: object | None,
) -> list[object]:
    """Return SQL parameters for the run-session finish statement."""
    return [
        run_id,
        run_type,
        started_at,
        finished_at,
        status,
        error_message,
        json_payload_or_none(config_snapshot),
        mode,
        postgres_text_array_or_none(symbols),
        timeframe,
        start_ts,
        end_ts,
    ]


def trading_session_finish_parameters(
    *,
    run_id: str,
    strategy_id: str | None,
    started_at: object,
    finished_at: object,
    status: str,
    error_message: str | None,
    config_snapshot: object | None,
    mode: str | None,
    symbols: Sequence[str] | None,
    timeframe: str | None,
    start_ts: object | None,
    end_ts: object | None,
) -> list[object]:
    """Return SQL parameters for the trading-session finish statement."""
    return [
        run_id,
        strategy_id,
        started_at,
        finished_at,
        status,
        error_message,
        json_payload_or_none(config_snapshot),
        mode,
        postgres_text_array_or_none(symbols),
        timeframe,
        start_ts,
        end_ts,
    ]


def cycle_start_parameters(
    *,
    run_id: str,
    cycle_id: str,
    strategy_id: str,
    mode: str,
    decision_ts: object,
    started_at: object,
) -> list[object]:
    """Return SQL parameters for the cycle-start statement."""
    return [cycle_id, run_id, run_id, strategy_id, mode, decision_ts, started_at]


def cycle_finish_parameters(
    *,
    run_id: str,
    cycle_id: str,
    strategy_id: str,
    mode: str,
    decision_ts: object,
    started_at: object,
    finished_at: object,
    status: str,
    error_message: str | None,
) -> list[object]:
    """Return SQL parameters for the cycle-finish statement."""
    return [
        cycle_id,
        run_id,
        run_id,
        strategy_id,
        mode,
        decision_ts,
        started_at,
        finished_at,
        status,
        error_message,
    ]


def upsert_experiment_parameters(
    *,
    experiment_id: str,
    name: str,
    description: str | None,
    tags: Sequence[str] | None,
    created_at: object | None,
    updated_at: object | None,
    metadata: Mapping[str, object] | None,
) -> list[object]:
    """Return SQL parameters for the experiment upsert statement."""
    return [
        experiment_id,
        name,
        description,
        postgres_text_array_or_empty(tags),
        created_at,
        updated_at,
        json_payload_or_empty(metadata),
    ]


def experiment_run_start_parameters(
    *,
    experiment_run_id: str,
    experiment_id: str,
    run_id: str,
    status: str,
    created_at: object,
    strategy_id: str | None,
    strategy_name: str | None,
    strategy_version: str | None,
    symbols: Sequence[str] | None,
    asset_class: str | None,
    timeframe: str | None,
    start_ts: object | None,
    end_ts: object | None,
    parameters: Mapping[str, object] | None,
    assumptions: Mapping[str, object] | None,
    provenance: Mapping[str, object] | None,
    data_quality: Mapping[str, object] | None,
    artifact_dir: str | None,
) -> list[object]:
    """Return SQL parameters for the experiment-run start statement."""
    return [
        experiment_run_id,
        experiment_id,
        run_id,
        status,
        created_at,
        strategy_id,
        strategy_name,
        strategy_version,
        postgres_text_array_or_none(symbols),
        asset_class,
        timeframe,
        start_ts,
        end_ts,
        json_payload_or_empty(parameters),
        json_payload_or_empty(assumptions),
        json_payload_or_empty(provenance),
        json_payload_or_empty(data_quality),
        artifact_dir,
    ]


def experiment_run_finish_parameters(
    *,
    experiment_run_id: str,
    experiment_id: str,
    run_id: str,
    status: str,
    finished_at: object,
    provenance: Mapping[str, object] | None,
    data_quality: Mapping[str, object] | None,
    result_summary: Mapping[str, object] | None,
    artifact_dir: str | None,
    error_message: str | None,
) -> list[object]:
    """Return SQL parameters for the experiment-run finish statement."""
    return [
        experiment_run_id,
        experiment_id,
        run_id,
        status,
        finished_at,
        finished_at,
        json_payload_or_empty(provenance),
        json_payload_or_empty(data_quality),
        json_payload_or_empty(result_summary),
        artifact_dir,
        error_message,
    ]


def experiment_run_row_to_record(row: Sequence[object]) -> Mapping[str, object]:
    """Map an experiment-run row into the public dictionary shape."""
    return dict(zip(EXPERIMENT_RUN_FIELDS, row))


__all__ = [
    "EXPERIMENT_RUN_FIELDS",
    "PostgresEventInsertPlan",
    "PostgresQueryPlan",
    "build_postgres_event_insert_plan",
    "cycle_finish_parameters",
    "cycle_start_parameters",
    "experiment_run_finish_parameters",
    "experiment_run_row_to_record",
    "experiment_run_start_parameters",
    "run_session_finish_parameters",
    "run_session_start_parameters",
    "trading_session_finish_parameters",
    "trading_session_start_parameters",
    "upsert_experiment_parameters",
    "json_payload_or_empty",
    "json_payload_or_none",
    "postgres_text_array_or_empty",
    "postgres_text_array_or_none",
    "list_experiment_runs_query_plan",
]
