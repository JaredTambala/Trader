"""Postgres controls and read auditing for the 57N qualification phase."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import hashlib
import os
from typing import Any, Mapping, Sequence

import psycopg
from psycopg.types.json import Jsonb

from trader.event_store import PostgresEventStore
from trader_research.foundation import json_payload_hash
from trader_research.infrastructure.postgres import PostgresResearchArtifactStore
from tests.support.postgres_verification import assert_connection_targets_verification_database


ACCESS_STAGE_ENV = "TRADER_VERIFICATION_ACCESS_STAGE"

_RUNTIME_TABLES = """
    metrics_snapshots,
    position_snapshots,
    fill_events,
    order_events,
    indicator_events,
    signal_events,
    stock_bar_events,
    crypto_bar_events,
    run_events,
    trading_sessions,
    runs,
    experiment_runs,
    experiments,
    config_kv
"""

_RESEARCH_TABLES = """
    research_ml_deployment_validations,
    research_ml_deployments,
    research_parameter_optimization_robustness_reports,
    research_parameter_optimization_audit_plans,
    research_parameter_optimization_evaluations,
    research_experiment_tracking_projections,
    research_parameter_optimization_trials,
    research_parameter_optimization_runs,
    research_parameter_optimization_plans,
    research_backtest_runs,
    research_backtest_specification_validations,
    research_backtest_specifications,
    research_risk_stack_specification_validations,
    research_risk_stack_specifications,
    research_strategy_specification_validations,
    research_strategy_specifications,
    research_implementation_validations,
    research_implementation_versions,
    research_methodology_validations,
    research_methodology_evidence_packets,
    research_methodology_field_extractions,
    research_methodology_candidates,
    research_artifacts
"""


def ensure_57n_control_schema(connection: psycopg.Connection[Any]) -> None:
    """Create test-only deterministic snapshot and data-access audit tables."""
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS verification_control.determinism_snapshots (
            phase TEXT NOT NULL,
            execution_label TEXT NOT NULL,
            graph_digest TEXT NOT NULL,
            artifact_count INTEGER NOT NULL,
            root_refs JSONB NOT NULL,
            artifact_hashes JSONB NOT NULL,
            recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (phase, execution_label)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS verification_control.data_access_log (
            access_id BIGSERIAL PRIMARY KEY,
            phase TEXT NOT NULL,
            stage TEXT NOT NULL,
            table_name TEXT NOT NULL,
            symbol TEXT,
            minimum_parameter_ts TIMESTAMPTZ,
            maximum_parameter_ts TIMESTAMPTZ,
            query_sha256 TEXT NOT NULL,
            read_count INTEGER NOT NULL DEFAULT 1,
            recorded_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
        )
        """
    )
    connection.execute(
        "ALTER TABLE verification_control.data_access_log "
        "ADD COLUMN IF NOT EXISTS read_count INTEGER NOT NULL DEFAULT 1"
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS verification_control.selection_seals (
            phase TEXT PRIMARY KEY,
            optimization_run_id TEXT NOT NULL,
            run_digest TEXT NOT NULL,
            sealed_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS verification_control.integrity_checks (
            phase TEXT NOT NULL,
            check_name TEXT NOT NULL,
            target_artifact_type TEXT NOT NULL,
            target_artifact_id TEXT NOT NULL,
            consumer_tool TEXT NOT NULL,
            error_code TEXT NOT NULL,
            error_message TEXT NOT NULL,
            passed BOOLEAN NOT NULL,
            recorded_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
            PRIMARY KEY (phase, check_name)
        )
        """
    )


def clear_57n_control_evidence(connection: psycopg.Connection[Any]) -> None:
    """Clear only prior 57N control evidence, preserving phase records."""
    ensure_57n_control_schema(connection)
    connection.execute("DELETE FROM verification_control.determinism_snapshots WHERE phase = '57N'")
    connection.execute("DELETE FROM verification_control.data_access_log WHERE phase = '57N'")
    connection.execute("DELETE FROM verification_control.selection_seals WHERE phase = '57N'")
    connection.execute("DELETE FROM verification_control.integrity_checks WHERE phase = '57N'")


def reset_57n_product_state(
    event_store: PostgresEventStore,
    artifact_store: PostgresResearchArtifactStore,
    settings: Mapping[str, object],
) -> None:
    """Return public runtime and research tables to an empty guarded state."""
    event_connection = event_store.connection()
    artifact_connection = artifact_store.connection()
    assert_connection_targets_verification_database(event_connection, settings)
    assert_connection_targets_verification_database(artifact_connection, settings)
    event_connection.execute(f"TRUNCATE TABLE {_RUNTIME_TABLES}")
    artifact_connection.execute(f"TRUNCATE TABLE {_RESEARCH_TABLES} CASCADE")
    row = artifact_connection.execute(
        "SELECT count(*) AS artifact_count FROM research_artifacts"
    ).fetchone()
    assert row["artifact_count"] == 0


def graph_snapshot(
    store: PostgresResearchArtifactStore,
    root_refs: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Return an exact canonical payload snapshot without database timestamps."""
    artifacts = [
        {
            "artifact_type": record.artifact_type,
            "artifact_id": record.artifact_id,
            "status": record.status,
            "payload": _deterministic_payload(record.artifact_type, record.payload),
            "payload_sha256": json_payload_hash(
                _deterministic_payload(record.artifact_type, record.payload)
            ),
        }
        for record in sorted(
            store.list_artifacts(),
            key=lambda item: (item.artifact_type, item.artifact_id),
        )
    ]
    payload = {"root_refs": dict(root_refs), "artifacts": artifacts}
    return {**payload, "graph_digest": json_payload_hash(payload)}


def _deterministic_payload(
    artifact_type: str, payload: Mapping[str, Any]
) -> dict[str, Any]:
    """Remove operational timing while retaining all canonical research evidence."""
    normalized = deepcopy(dict(payload))
    if artifact_type == "backtest_run":
        result = normalized.get("bundle", {}).get("result", {})
        if isinstance(result, dict):
            result.pop("finished_at", None)
            result.pop("duration_seconds", None)
    return normalized


def save_graph_snapshot(
    connection: psycopg.Connection[Any],
    *,
    execution_label: str,
    snapshot: Mapping[str, Any],
) -> None:
    """Persist one compact graph digest for pgAdmin comparison."""
    artifact_hashes = [
        {
            "artifact_type": item["artifact_type"],
            "artifact_id": item["artifact_id"],
            "payload_sha256": item["payload_sha256"],
        }
        for item in snapshot["artifacts"]
    ]
    connection.execute(
        """
        INSERT INTO verification_control.determinism_snapshots (
            phase, execution_label, graph_digest, artifact_count, root_refs, artifact_hashes
        ) VALUES ('57N', %s, %s, %s, %s, %s)
        ON CONFLICT (phase, execution_label) DO UPDATE SET
            graph_digest = EXCLUDED.graph_digest,
            artifact_count = EXCLUDED.artifact_count,
            root_refs = EXCLUDED.root_refs,
            artifact_hashes = EXCLUDED.artifact_hashes,
            recorded_at = now()
        """,
        [
            execution_label,
            snapshot["graph_digest"],
            len(snapshot["artifacts"]),
            Jsonb(dict(snapshot["root_refs"])),
            Jsonb(artifact_hashes),
        ],
    )


def seal_selection(
    connection: psycopg.Connection[Any],
    optimization_run: Mapping[str, Any],
) -> None:
    """Record the database-time boundary after deterministic selection completes."""
    connection.execute(
        """
        INSERT INTO verification_control.selection_seals (
            phase, optimization_run_id, run_digest
        ) VALUES ('57N', %s, %s)
        ON CONFLICT (phase) DO UPDATE SET
            optimization_run_id = EXCLUDED.optimization_run_id,
            run_digest = EXCLUDED.run_digest,
            sealed_at = clock_timestamp()
        """,
        [optimization_run["optimization_run_id"], json_payload_hash(optimization_run)],
    )


def save_integrity_check(
    connection: psycopg.Connection[Any],
    *,
    check_name: str,
    target_artifact_type: str,
    target_artifact_id: str,
    consumer_tool: str,
    error_code: str,
    error_message: str,
) -> None:
    """Persist one fail-closed hostile-mutation result."""
    connection.execute(
        """
        INSERT INTO verification_control.integrity_checks (
            phase, check_name, target_artifact_type, target_artifact_id,
            consumer_tool, error_code, error_message, passed
        ) VALUES ('57N', %s, %s, %s, %s, %s, %s, true)
        ON CONFLICT (phase, check_name) DO UPDATE SET
            target_artifact_type = EXCLUDED.target_artifact_type,
            target_artifact_id = EXCLUDED.target_artifact_id,
            consumer_tool = EXCLUDED.consumer_tool,
            error_code = EXCLUDED.error_code,
            error_message = EXCLUDED.error_message,
            passed = true,
            recorded_at = clock_timestamp()
        """,
        [
            check_name,
            target_artifact_type,
            target_artifact_id,
            consumer_tool,
            error_code,
            error_message,
        ],
    )


class AuditedPostgresEventStore(PostgresEventStore):
    """Postgres event store whose bounded bar reads are recorded for 57N."""

    def __init__(self, *, stage: str, **connect_kwargs: Any) -> None:
        self._audit_stage = stage
        self._audit_connect_kwargs = dict(connect_kwargs)
        self._audit_records: dict[
            tuple[str, str | None, datetime | None, datetime | None, str], int
        ] = {}
        super().__init__(**connect_kwargs)

    def connection(self) -> Any:
        """Return a cursor proxy that records bar-table reads."""
        return _AuditedConnection(
            super().connection(),
            stage=self._audit_stage,
            records=self._audit_records,
        )

    def close(self) -> None:
        """Flush aggregated audit rows before closing the event-store connection."""
        if self._audit_records:
            with psycopg.connect(**self._audit_connect_kwargs, autocommit=True) as audit:
                ensure_57n_control_schema(audit)
                for (table, symbol, minimum, maximum, query_sha256), count in sorted(
                    self._audit_records.items(), key=lambda item: str(item[0])
                ):
                    audit.execute(
                        """
                        INSERT INTO verification_control.data_access_log (
                            phase, stage, table_name, symbol, minimum_parameter_ts,
                            maximum_parameter_ts, query_sha256, read_count
                        ) VALUES ('57N', %s, %s, %s, %s, %s, %s, %s)
                        """,
                        [
                            self._audit_stage,
                            table,
                            symbol,
                            minimum,
                            maximum,
                            query_sha256,
                            count,
                        ],
                    )
        super().close()


class _AuditedConnection:
    def __init__(
        self,
        connection: psycopg.Connection[Any],
        *,
        stage: str,
        records: dict[tuple[str, str | None, datetime | None, datetime | None, str], int],
    ) -> None:
        self._connection = connection
        self._stage = stage
        self._records = records

    def cursor(self, *args: Any, **kwargs: Any) -> Any:
        return _AuditedCursor(
            self._connection.cursor(*args, **kwargs),
            connection=self._connection,
            stage=self._stage,
            records=self._records,
        )

    def __getattr__(self, name: str) -> Any:
        return getattr(self._connection, name)


class _AuditedCursor:
    def __init__(
        self,
        cursor: Any,
        *,
        connection: psycopg.Connection[Any],
        stage: str,
        records: dict[tuple[str, str | None, datetime | None, datetime | None, str], int],
    ) -> None:
        self._cursor = cursor
        self._connection = connection
        self._stage = stage
        self._records = records

    def __enter__(self) -> "_AuditedCursor":
        self._cursor.__enter__()
        return self

    def __exit__(self, *args: Any) -> Any:
        return self._cursor.__exit__(*args)

    def execute(self, query: Any, params: Sequence[Any] | Mapping[str, Any] | None = None) -> Any:
        text = query.as_string(self._connection) if hasattr(query, "as_string") else str(query)
        self._record_bar_read(text, params)
        self._cursor.execute(query, params)
        return self

    def _record_bar_read(
        self,
        query: str,
        params: Sequence[Any] | Mapping[str, Any] | None,
    ) -> None:
        lowered = " ".join(query.lower().split())
        table_name = next(
            (name for name in ("stock_bar_events", "crypto_bar_events") if name in lowered),
            None,
        )
        if table_name is None or "select" not in lowered:
            return
        values = list(params.values()) if isinstance(params, Mapping) else list(params or [])
        timestamps = [value for value in values if isinstance(value, datetime)]
        symbol = next(
            (str(value) for value in values if isinstance(value, str) and value.isupper()),
            None,
        )
        key = (
            table_name,
            symbol,
            min(timestamps) if timestamps else None,
            max(timestamps) if timestamps else None,
            hashlib.sha256(lowered.encode("utf-8")).hexdigest(),
        )
        self._records[key] = self._records.get(key, 0) + 1

    def __getattr__(self, name: str) -> Any:
        return getattr(self._cursor, name)


def access_audit_summary(connection: psycopg.Connection[Any]) -> Mapping[str, Any]:
    """Return compact stage counts and enforce post-seal holdout chronology."""
    rows = connection.execute(
        """
        SELECT stage, sum(read_count) AS read_count,
               min(minimum_parameter_ts) AS minimum_parameter_ts,
               max(maximum_parameter_ts) AS maximum_parameter_ts
        FROM verification_control.data_access_log
        WHERE phase = '57N'
        GROUP BY stage
        ORDER BY stage
        """
    ).fetchall()
    seal = connection.execute(
        "SELECT optimization_run_id, run_digest, sealed_at "
        "FROM verification_control.selection_seals WHERE phase = '57N'"
    ).fetchone()
    return {
        "stages": [
            {
                "stage": row["stage"],
                "read_count": row["read_count"],
                "minimum_parameter_ts": (
                    row["minimum_parameter_ts"].isoformat()
                    if row["minimum_parameter_ts"]
                    else None
                ),
                "maximum_parameter_ts": (
                    row["maximum_parameter_ts"].isoformat()
                    if row["maximum_parameter_ts"]
                    else None
                ),
            }
            for row in rows
        ],
        "selection_seal": {
            "optimization_run_id": seal["optimization_run_id"],
            "run_digest": seal["run_digest"],
            "sealed_at": seal["sealed_at"].isoformat(),
        }
        if seal
        else None,
    }


def configured_access_stage() -> str | None:
    """Return the optional test-only MCP access-audit stage."""
    value = os.environ.get(ACCESS_STAGE_ENV, "").strip()
    return value or None
