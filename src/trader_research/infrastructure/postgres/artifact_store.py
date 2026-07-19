"""Postgres-backed research artifact store."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from trader_research.foundation.artifacts import (
    ResearchArtifactNotFound,
    ResearchArtifactRecord,
    ResearchArtifactStoreError,
    build_artifact_record,
)
from .projections import ProjectionRegistry, default_projection_registry

try:  # pragma: no cover - exercised by postgres integration tests
    import psycopg
    from psycopg.rows import dict_row
    from psycopg.types.json import Jsonb
except ImportError:  # pragma: no cover - optional dependency
    psycopg = None  # type: ignore[assignment]
    dict_row = None  # type: ignore[assignment]
    Jsonb = None  # type: ignore[misc,assignment]


RESEARCH_ARTIFACT_SCHEMA_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS research_artifacts (
        artifact_type TEXT NOT NULL,
        artifact_id TEXT NOT NULL,
        agent_owner TEXT NOT NULL,
        status TEXT,
        schema_version TEXT NOT NULL,
        source_hash TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
        payload JSONB NOT NULL,
        PRIMARY KEY (artifact_type, artifact_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS research_implementation_versions (
        implementation_version_id TEXT PRIMARY KEY,
        implementation_kind TEXT NOT NULL,
        name TEXT NOT NULL,
        version TEXT NOT NULL,
        status TEXT NOT NULL,
        source_hash TEXT NOT NULL,
        authoring_origin TEXT NOT NULL,
        payload JSONB NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS research_implementation_validations (
        validation_id TEXT PRIMARY KEY,
        implementation_version_id TEXT NOT NULL,
        implementation_kind TEXT NOT NULL,
        status TEXT NOT NULL,
        valid BOOLEAN NOT NULL,
        source_hash TEXT NOT NULL,
        payload JSONB NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS research_strategy_specifications (
        strategy_specification_id TEXT PRIMARY KEY,
        implementation_version_id TEXT NOT NULL,
        status TEXT NOT NULL,
        source_hash TEXT NOT NULL,
        tunable_fields TEXT[] NOT NULL DEFAULT '{}',
        payload JSONB NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS research_strategy_specification_validations (
        validation_id TEXT PRIMARY KEY,
        strategy_specification_id TEXT NOT NULL,
        status TEXT NOT NULL,
        valid BOOLEAN NOT NULL,
        payload JSONB NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS research_risk_stack_specifications (
        risk_stack_specification_id TEXT PRIMARY KEY,
        implementation_version_ids TEXT[] NOT NULL DEFAULT '{}',
        status TEXT NOT NULL,
        payload JSONB NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS research_risk_stack_specification_validations (
        validation_id TEXT PRIMARY KEY,
        risk_stack_specification_id TEXT NOT NULL,
        status TEXT NOT NULL,
        valid BOOLEAN NOT NULL,
        payload JSONB NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS research_backtest_specifications (
        backtest_specification_id TEXT PRIMARY KEY,
        strategy_specification_id TEXT NOT NULL,
        risk_stack_specification_id TEXT,
        dataset_id TEXT NOT NULL,
        status TEXT NOT NULL,
        parent_specification_ref TEXT,
        selection_origin_ref TEXT,
        variant_reason TEXT,
        payload JSONB NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS research_backtest_specification_validations (
        validation_id TEXT PRIMARY KEY,
        backtest_specification_id TEXT NOT NULL,
        status TEXT NOT NULL,
        valid BOOLEAN NOT NULL,
        dataset_hash TEXT NOT NULL,
        payload JSONB NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS research_parameter_optimization_plans (
        optimization_plan_id TEXT PRIMARY KEY,
        base_backtest_specification_id TEXT NOT NULL,
        objective_implementation_version_id TEXT NOT NULL,
        direction TEXT NOT NULL,
        seed BIGINT NOT NULL,
        max_trials INTEGER NOT NULL,
        status TEXT NOT NULL,
        parent_plan_ref TEXT,
        variant_reason TEXT,
        payload JSONB NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS research_parameter_optimization_runs (
        optimization_run_id TEXT PRIMARY KEY,
        optimization_plan_id TEXT NOT NULL,
        engine_name TEXT NOT NULL,
        engine_version TEXT NOT NULL,
        engine_configuration_digest TEXT NOT NULL,
        seed BIGINT NOT NULL,
        status TEXT NOT NULL,
        selected_trial_id TEXT,
        selected_backtest_specification_id TEXT,
        payload JSONB NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS research_parameter_optimization_trials (
        trial_id TEXT PRIMARY KEY,
        optimization_run_id TEXT NOT NULL,
        optimization_plan_id TEXT NOT NULL,
        sequence INTEGER NOT NULL,
        status TEXT NOT NULL,
        objective_value DOUBLE PRECISION,
        parameters JSONB NOT NULL,
        child_backtest_specification_id TEXT,
        child_backtest_run_id TEXT,
        payload JSONB NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS research_experiment_tracking_projections (
        projection_id TEXT PRIMARY KEY,
        canonical_run_id TEXT NOT NULL,
        tracking_profile TEXT NOT NULL,
        status TEXT NOT NULL,
        authoritative BOOLEAN NOT NULL,
        payload JSONB NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS research_parameter_optimization_evaluations (
        report_id TEXT PRIMARY KEY,
        optimization_run_id TEXT NOT NULL,
        holdout_backtest_run_id TEXT,
        status TEXT NOT NULL,
        payload JSONB NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS research_parameter_optimization_audit_plans (
        audit_plan_id TEXT PRIMARY KEY,
        baseline_optimization_run_id TEXT NOT NULL,
        status TEXT NOT NULL,
        payload JSONB NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS research_parameter_optimization_robustness_reports (
        report_id TEXT PRIMARY KEY,
        audit_plan_id TEXT NOT NULL,
        baseline_optimization_run_id TEXT NOT NULL,
        status TEXT NOT NULL,
        payload JSONB NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS research_methodology_candidates (
        candidate_id TEXT PRIMARY KEY,
        status TEXT,
        families TEXT[] NOT NULL DEFAULT '{}',
        source_ids TEXT[] NOT NULL DEFAULT '{}',
        chunk_ids TEXT[] NOT NULL DEFAULT '{}',
        payload JSONB NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS research_methodology_field_extractions (
        extraction_id TEXT PRIMARY KEY,
        candidate_id TEXT NOT NULL,
        status TEXT NOT NULL,
        populated_field_count INTEGER NOT NULL DEFAULT 0,
        payload JSONB NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS research_methodology_evidence_packets (
        evidence_packet_id TEXT PRIMARY KEY,
        candidate_id TEXT NOT NULL,
        family TEXT NOT NULL,
        readiness_goal TEXT NOT NULL,
        status TEXT NOT NULL,
        source_ids TEXT[] NOT NULL DEFAULT '{}',
        chunk_ids TEXT[] NOT NULL DEFAULT '{}',
        missing_roles TEXT[] NOT NULL DEFAULT '{}',
        payload JSONB NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS research_methodology_validations (
        validation_id TEXT PRIMARY KEY,
        candidate_id TEXT NOT NULL,
        status TEXT NOT NULL,
        payload JSONB NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS research_backtest_runs (
        run_id TEXT PRIMARY KEY,
        backtest_kind TEXT NOT NULL,
        status TEXT,
        dataset_id TEXT,
        backtest_specification_id TEXT NOT NULL,
        strategy_specification_id TEXT NOT NULL,
        risk_stack_specification_id TEXT,
        selection_origin_ref TEXT,
        parent_specification_ref TEXT,
        variant_reason TEXT,
        summary JSONB NOT NULL DEFAULT '{}'::jsonb,
        payload JSONB NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS research_artifacts_type_status_idx ON research_artifacts(artifact_type, status)",
    (
        "CREATE INDEX IF NOT EXISTS research_methodology_candidates_status_idx "
        "ON research_methodology_candidates(status)"
    ),
    "CREATE INDEX IF NOT EXISTS research_backtest_runs_kind_status_idx ON research_backtest_runs(backtest_kind, status)",
    (
        "CREATE INDEX IF NOT EXISTS research_optimization_trials_run_sequence_idx "
        "ON research_parameter_optimization_trials(optimization_run_id, sequence)"
    ),
    (
        "CREATE INDEX IF NOT EXISTS research_optimization_runs_plan_status_idx "
        "ON research_parameter_optimization_runs(optimization_plan_id, status)"
    ),
)


class PostgresResearchArtifactStore:
    """Structured Postgres store for research artifacts and evidence bundles."""

    backend = "postgres"

    def __init__(
        self,
        *,
        dsn: str | None = None,
        host: str | None = None,
        port: int | None = None,
        dbname: str | None = None,
        user: str | None = None,
        password: str | None = None,
        ensure_schema: bool = True,
        projection_registry: ProjectionRegistry | None = None,
    ) -> None:
        if psycopg is None:
            raise ImportError(
                "psycopg is required to use PostgresResearchArtifactStore"
            )
        if dsn:
            self._connection = psycopg.connect(dsn, row_factory=dict_row)
        else:
            self._connection = psycopg.connect(
                host=host,
                port=port,
                dbname=dbname,
                user=user,
                password=password,
                row_factory=dict_row,
            )
        self._connection.autocommit = True
        self._projection_registry = projection_registry or default_projection_registry()
        if ensure_schema:
            self.ensure_schema()

    def ensure_schema(self) -> None:
        """Create and migrate research-artifact tables."""
        try:
            with self._connection.cursor() as cursor:
                for statement in RESEARCH_ARTIFACT_SCHEMA_STATEMENTS:
                    cursor.execute(statement)
        except Exception as exc:  # pragma: no cover - driver-specific details
            raise ResearchArtifactStoreError(
                f"failed to initialize research artifact schema: {exc}"
            ) from exc

    def runtime_summary(self) -> Mapping[str, Any]:
        """Return non-secret store runtime metadata."""
        return {"backend": self.backend, "configured": True, "schema": "public"}

    def save_artifact(
        self,
        *,
        artifact_type: str,
        artifact_id: str,
        agent_owner: str,
        payload: Mapping[str, Any],
        status: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        source_hash: str | None = None,
    ) -> ResearchArtifactRecord:
        """Persist one artifact payload and typed projection rows."""
        record = build_artifact_record(
            artifact_type=artifact_type,
            artifact_id=artifact_id,
            agent_owner=agent_owner,
            payload=payload,
            status=status,
            metadata=metadata,
            source_hash=source_hash,
        )
        with self._connection.transaction():
            self._connection.execute(
                """
                INSERT INTO research_artifacts (
                    artifact_type, artifact_id, agent_owner, status, schema_version,
                    source_hash, metadata, payload
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (artifact_type, artifact_id) DO UPDATE SET
                    agent_owner = EXCLUDED.agent_owner,
                    status = EXCLUDED.status,
                    schema_version = EXCLUDED.schema_version,
                    source_hash = EXCLUDED.source_hash,
                    metadata = EXCLUDED.metadata,
                    payload = EXCLUDED.payload,
                    updated_at = now()
                """,
                [
                    record.artifact_type,
                    record.artifact_id,
                    record.agent_owner,
                    record.status,
                    record.schema_version,
                    record.source_hash,
                    Jsonb(dict(record.metadata)),
                    Jsonb(dict(record.payload)),
                ],
            )
            self._projection_registry.write(
                self._connection,
                record,
                json_value=Jsonb,
            )
        return record

    def load_artifact(self, artifact_type: str, artifact_id: str) -> Mapping[str, Any]:
        """Load one artifact payload by type and ID."""
        return self.load_artifact_record(artifact_type, artifact_id).payload

    def load_artifact_record(
        self, artifact_type: str, artifact_id: str
    ) -> ResearchArtifactRecord:
        """Load one full artifact record by type and ID."""
        row = self._connection.execute(
            """
            SELECT artifact_type, artifact_id, agent_owner, status, schema_version,
                   source_hash, created_at, updated_at, metadata, payload
            FROM research_artifacts
            WHERE artifact_type = %s AND artifact_id = %s
            """,
            [artifact_type, artifact_id],
        ).fetchone()
        if row is None:
            raise ResearchArtifactNotFound(
                f"unknown research artifact: {artifact_type}/{artifact_id}"
            )
        return ResearchArtifactRecord(
            artifact_type=str(row["artifact_type"]),
            artifact_id=str(row["artifact_id"]),
            agent_owner=str(row["agent_owner"]),
            status=row["status"],
            schema_version=str(row["schema_version"]),
            source_hash=row["source_hash"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            metadata=dict(row["metadata"] or {}),
            payload=dict(row["payload"] or {}),
        )

    def list_artifacts(
        self,
        *,
        artifact_type: str | None = None,
        artifact_ids: Sequence[str] | None = None,
    ) -> tuple[ResearchArtifactRecord, ...]:
        """List artifact records for diagnostics and tests."""
        where: list[str] = []
        params: list[Any] = []
        if artifact_type:
            where.append("artifact_type = %s")
            params.append(artifact_type)
        if artifact_ids:
            where.append("artifact_id = ANY(%s)")
            params.append(list(artifact_ids))
        query = """
            SELECT artifact_type, artifact_id, agent_owner, status, schema_version,
                   source_hash, created_at, updated_at, metadata, payload
            FROM research_artifacts
        """
        if where:
            query += " WHERE " + " AND ".join(where)
        query += " ORDER BY artifact_type, artifact_id"
        rows = self._connection.execute(query, params).fetchall()
        return tuple(
            ResearchArtifactRecord(
                artifact_type=str(row["artifact_type"]),
                artifact_id=str(row["artifact_id"]),
                agent_owner=str(row["agent_owner"]),
                status=row["status"],
                schema_version=str(row["schema_version"]),
                source_hash=row["source_hash"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                metadata=dict(row["metadata"] or {}),
                payload=dict(row["payload"] or {}),
            )
            for row in rows
        )

    def connection(self) -> Any:
        """Return the underlying psycopg connection for integration tests."""
        return self._connection

    def close(self) -> None:
        """Close the Postgres connection."""
        self._connection.close()
