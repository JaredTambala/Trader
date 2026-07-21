"""Test-only Postgres evidence records for task 57R bounded-scale checks."""

from __future__ import annotations

from typing import Any, Mapping

import psycopg
from psycopg.types.json import Jsonb


def ensure_57r_control_schema(connection: psycopg.Connection[Any]) -> None:
    """Create the operator-visible bounded-scale evidence table."""
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS verification_control.bounded_scale_results (
            phase TEXT NOT NULL,
            profile TEXT NOT NULL,
            status TEXT NOT NULL,
            symbols INTEGER NOT NULL,
            bars_per_symbol INTEGER NOT NULL,
            trial_count INTEGER NOT NULL,
            wall_seconds DOUBLE PRECISION NOT NULL,
            result_query_seconds DOUBLE PRECISION,
            database_bytes BIGINT NOT NULL,
            artifact_count INTEGER NOT NULL,
            query_plan JSONB NOT NULL,
            payload JSONB NOT NULL,
            recorded_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
            PRIMARY KEY (phase, profile)
        )
        """
    )


def clear_57r_control_evidence(connection: psycopg.Connection[Any]) -> None:
    """Clear prior 57R scale rows while preserving controlled phase evidence."""
    ensure_57r_control_schema(connection)
    connection.execute(
        "DELETE FROM verification_control.bounded_scale_results WHERE phase = '57R'"
    )


def save_57r_scale_result(
    connection: psycopg.Connection[Any],
    *,
    profile: str,
    symbols: int,
    bars_per_symbol: int,
    trial_count: int,
    wall_seconds: float,
    result_query_seconds: float | None,
    database_bytes: int,
    artifact_count: int,
    query_plan: Mapping[str, Any],
    payload: Mapping[str, Any],
) -> None:
    """Upsert one credential-free bounded-scale qualification result."""
    connection.execute(
        """
        INSERT INTO verification_control.bounded_scale_results (
            phase, profile, status, symbols, bars_per_symbol, trial_count,
            wall_seconds, result_query_seconds, database_bytes, artifact_count,
            query_plan, payload
        ) VALUES ('57R', %s, 'passed', %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (phase, profile) DO UPDATE SET
            status = EXCLUDED.status,
            symbols = EXCLUDED.symbols,
            bars_per_symbol = EXCLUDED.bars_per_symbol,
            trial_count = EXCLUDED.trial_count,
            wall_seconds = EXCLUDED.wall_seconds,
            result_query_seconds = EXCLUDED.result_query_seconds,
            database_bytes = EXCLUDED.database_bytes,
            artifact_count = EXCLUDED.artifact_count,
            query_plan = EXCLUDED.query_plan,
            payload = EXCLUDED.payload,
            recorded_at = clock_timestamp()
        """,
        [
            profile,
            symbols,
            bars_per_symbol,
            trial_count,
            wall_seconds,
            result_query_seconds,
            database_bytes,
            artifact_count,
            Jsonb(dict(query_plan)),
            Jsonb(dict(payload)),
        ],
    )
