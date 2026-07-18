"""Postgres-backed research artifact store."""

from __future__ import annotations

from collections.abc import Mapping as MappingABC
from typing import Any, Mapping, Sequence

from trader_research.artifact_store import (
    ResearchArtifactNotFound,
    ResearchArtifactRecord,
    ResearchArtifactStoreError,
    build_artifact_record,
)
from trader_research.domain import (
    BACKTEST_RUN,
    BACKTEST_SPECIFICATION,
    BACKTEST_SPECIFICATION_VALIDATION_REPORT,
    EXPERIMENT_TRACKING_PROJECTION_REPORT,
    IMPLEMENTATION_VALIDATION_REPORT,
    IMPLEMENTATION_VERSION,
    METHODOLOGY_CANDIDATE,
    METHODOLOGY_CANDIDATE_VALIDATION_REPORT,
    METHODOLOGY_EVIDENCE_PACKET,
    METHODOLOGY_FIELD_EXTRACTION_REPORT,
    PARAMETER_OPTIMIZATION_AUDIT_PLAN,
    PARAMETER_OPTIMIZATION_EVALUATION_REPORT,
    PARAMETER_OPTIMIZATION_PLAN,
    PARAMETER_OPTIMIZATION_ROBUSTNESS_REPORT,
    PARAMETER_OPTIMIZATION_RUN,
    PARAMETER_OPTIMIZATION_TRIAL,
    RISK_STACK_SPECIFICATION,
    RISK_STACK_SPECIFICATION_VALIDATION_REPORT,
    STRATEGY_SPECIFICATION,
    STRATEGY_SPECIFICATION_VALIDATION_REPORT,
)

try:  # pragma: no cover - exercised by postgres integration tests
    import psycopg
    from psycopg.rows import dict_row
    from psycopg.types.json import Jsonb
except ImportError:  # pragma: no cover - optional dependency
    psycopg = None
    dict_row = None
    Jsonb = None


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
    ) -> None:
        if psycopg is None:
            raise ImportError("psycopg is required to use PostgresResearchArtifactStore")
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
        if ensure_schema:
            self.ensure_schema()

    def ensure_schema(self) -> None:
        """Create and migrate research-artifact tables."""
        try:
            with self._connection.cursor() as cursor:
                for statement in RESEARCH_ARTIFACT_SCHEMA_STATEMENTS:
                    cursor.execute(statement)
        except Exception as exc:  # pragma: no cover - driver-specific details
            raise ResearchArtifactStoreError(f"failed to initialize research artifact schema: {exc}") from exc

    def runtime_summary(self) -> Mapping[str, Any]:
        """Return non-secret store runtime metadata."""
        return {"backend": self.backend, "configured": True, "schema": "public"}

    def save_artifact(
        self,
        *,
        artifact_type: str,
        artifact_id: str,
        payload: Mapping[str, Any],
        status: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        source_hash: str | None = None,
    ) -> ResearchArtifactRecord:
        """Persist one artifact payload and typed projection rows."""
        record = build_artifact_record(
            artifact_type=artifact_type,
            artifact_id=artifact_id,
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
            self._save_projection(record)
        return record

    def load_artifact(self, artifact_type: str, artifact_id: str) -> Mapping[str, Any]:
        """Load one artifact payload by type and ID."""
        return self.load_artifact_record(artifact_type, artifact_id).payload

    def load_artifact_record(self, artifact_type: str, artifact_id: str) -> ResearchArtifactRecord:
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
            raise ResearchArtifactNotFound(f"unknown research artifact: {artifact_type}/{artifact_id}")
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

    def _save_projection(self, record: ResearchArtifactRecord) -> None:
        payload = dict(record.payload)
        artifact_type = record.artifact_type
        if artifact_type == IMPLEMENTATION_VERSION:
            self._connection.execute(
                """
                INSERT INTO research_implementation_versions (
                    implementation_version_id, implementation_kind, name, version,
                    status, source_hash, authoring_origin, payload
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (implementation_version_id) DO UPDATE SET
                    status = EXCLUDED.status,
                    payload = EXCLUDED.payload
                """,
                [
                    record.artifact_id,
                    payload.get("implementation_kind"),
                    payload.get("name"),
                    payload.get("version"),
                    payload.get("status") or record.status,
                    payload.get("source_hash") or record.source_hash,
                    payload.get("authoring_origin"),
                    Jsonb(payload),
                ],
            )
        elif artifact_type == IMPLEMENTATION_VALIDATION_REPORT:
            self._connection.execute(
                """
                INSERT INTO research_implementation_validations (
                    validation_id, implementation_version_id, implementation_kind,
                    status, valid, source_hash, payload
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (validation_id) DO UPDATE SET
                    status = EXCLUDED.status,
                    valid = EXCLUDED.valid,
                    payload = EXCLUDED.payload
                """,
                [
                    record.artifact_id,
                    payload.get("implementation_version_id"),
                    payload.get("implementation_kind"),
                    payload.get("status") or record.status,
                    bool(payload.get("valid")),
                    payload.get("source_hash") or record.source_hash,
                    Jsonb(payload),
                ],
            )
        elif artifact_type == STRATEGY_SPECIFICATION:
            self._connection.execute(
                """
                INSERT INTO research_strategy_specifications (
                    strategy_specification_id, implementation_version_id, status,
                    source_hash, tunable_fields, payload
                ) VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (strategy_specification_id) DO UPDATE SET
                    status = EXCLUDED.status,
                    tunable_fields = EXCLUDED.tunable_fields,
                    payload = EXCLUDED.payload
                """,
                [
                    record.artifact_id,
                    payload.get("implementation_version_id"),
                    payload.get("status") or record.status,
                    payload.get("source_hash") or record.source_hash,
                    [str(item) for item in payload.get("tunable_fields", [])],
                    Jsonb(payload),
                ],
            )
        elif artifact_type == STRATEGY_SPECIFICATION_VALIDATION_REPORT:
            self._connection.execute(
                """
                INSERT INTO research_strategy_specification_validations (
                    validation_id, strategy_specification_id, status, valid, payload
                ) VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (validation_id) DO UPDATE SET
                    status = EXCLUDED.status,
                    valid = EXCLUDED.valid,
                    payload = EXCLUDED.payload
                """,
                [
                    record.artifact_id,
                    payload.get("strategy_specification_id"),
                    payload.get("status") or record.status,
                    bool(payload.get("valid")),
                    Jsonb(payload),
                ],
            )
        elif artifact_type == RISK_STACK_SPECIFICATION:
            manager_ids = [
                str(item.get("implementation_version_id"))
                for item in payload.get("risk_managers", [])
                if isinstance(item, MappingABC)
            ]
            self._connection.execute(
                """
                INSERT INTO research_risk_stack_specifications (
                    risk_stack_specification_id, implementation_version_ids, status, payload
                ) VALUES (%s, %s, %s, %s)
                ON CONFLICT (risk_stack_specification_id) DO UPDATE SET
                    status = EXCLUDED.status,
                    implementation_version_ids = EXCLUDED.implementation_version_ids,
                    payload = EXCLUDED.payload
                """,
                [record.artifact_id, manager_ids, payload.get("status") or record.status, Jsonb(payload)],
            )
        elif artifact_type == RISK_STACK_SPECIFICATION_VALIDATION_REPORT:
            self._connection.execute(
                """
                INSERT INTO research_risk_stack_specification_validations (
                    validation_id, risk_stack_specification_id, status, valid, payload
                ) VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (validation_id) DO UPDATE SET
                    status = EXCLUDED.status,
                    valid = EXCLUDED.valid,
                    payload = EXCLUDED.payload
                """,
                [
                    record.artifact_id,
                    payload.get("risk_stack_specification_id"),
                    payload.get("status") or record.status,
                    bool(payload.get("valid")),
                    Jsonb(payload),
                ],
            )
        elif artifact_type == BACKTEST_SPECIFICATION:
            dataset = payload.get("dataset") or {}
            dataset_payload = dataset.get("payload") if isinstance(dataset, MappingABC) else {}
            self._connection.execute(
                """
                INSERT INTO research_backtest_specifications (
                    backtest_specification_id, strategy_specification_id,
                    risk_stack_specification_id, dataset_id, status,
                    parent_specification_ref, selection_origin_ref, variant_reason, payload
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (backtest_specification_id) DO UPDATE SET
                    status = EXCLUDED.status,
                    parent_specification_ref = EXCLUDED.parent_specification_ref,
                    selection_origin_ref = EXCLUDED.selection_origin_ref,
                    variant_reason = EXCLUDED.variant_reason,
                    payload = EXCLUDED.payload
                """,
                [
                    record.artifact_id,
                    payload.get("strategy_specification_id"),
                    payload.get("risk_stack_specification_id"),
                    dataset_payload.get("dataset_id") if isinstance(dataset_payload, MappingABC) else None,
                    payload.get("status") or record.status,
                    payload.get("parent_specification_ref"),
                    payload.get("selection_origin_ref"),
                    payload.get("variant_reason"),
                    Jsonb(payload),
                ],
            )
        elif artifact_type == BACKTEST_SPECIFICATION_VALIDATION_REPORT:
            self._connection.execute(
                """
                INSERT INTO research_backtest_specification_validations (
                    validation_id, backtest_specification_id, status, valid, dataset_hash, payload
                ) VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (validation_id) DO UPDATE SET
                    status = EXCLUDED.status,
                    valid = EXCLUDED.valid,
                    payload = EXCLUDED.payload
                """,
                [
                    record.artifact_id,
                    payload.get("backtest_specification_id"),
                    payload.get("status") or record.status,
                    bool(payload.get("valid")),
                    payload.get("dataset_hash"),
                    Jsonb(payload),
                ],
            )
        elif artifact_type == PARAMETER_OPTIMIZATION_PLAN:
            self._connection.execute(
                """
                INSERT INTO research_parameter_optimization_plans (
                    optimization_plan_id, base_backtest_specification_id,
                    objective_implementation_version_id, direction, seed, max_trials,
                    status, parent_plan_ref, variant_reason, payload
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (optimization_plan_id) DO UPDATE SET
                    status = EXCLUDED.status,
                    payload = EXCLUDED.payload
                """,
                [
                    record.artifact_id,
                    payload.get("base_backtest_specification_id"),
                    payload.get("objective_implementation_version_id"),
                    payload.get("direction"),
                    payload.get("seed"),
                    payload.get("max_trials"),
                    payload.get("status") or record.status,
                    payload.get("parent_plan_ref"),
                    payload.get("variant_reason"),
                    Jsonb(payload),
                ],
            )
        elif artifact_type == PARAMETER_OPTIMIZATION_RUN:
            profile = payload.get("engine_profile") or {}
            selected_refs = payload.get("selected_child_refs") or {}
            self._connection.execute(
                """
                INSERT INTO research_parameter_optimization_runs (
                    optimization_run_id, optimization_plan_id, engine_name, engine_version,
                    engine_configuration_digest, seed, status, selected_trial_id,
                    selected_backtest_specification_id, payload
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (optimization_run_id) DO UPDATE SET
                    status = EXCLUDED.status,
                    selected_trial_id = EXCLUDED.selected_trial_id,
                    selected_backtest_specification_id = EXCLUDED.selected_backtest_specification_id,
                    payload = EXCLUDED.payload
                """,
                [
                    record.artifact_id,
                    payload.get("optimization_plan_id"),
                    profile.get("profile_name"),
                    profile.get("provider_version"),
                    profile.get("configuration_digest"),
                    payload.get("seed"),
                    payload.get("status") or record.status,
                    payload.get("selected_trial_id"),
                    selected_refs.get("backtest_specification_id"),
                    Jsonb(payload),
                ],
            )
        elif artifact_type == PARAMETER_OPTIMIZATION_TRIAL:
            child_refs = payload.get("child_refs") or {}
            self._connection.execute(
                """
                INSERT INTO research_parameter_optimization_trials (
                    trial_id, optimization_run_id, optimization_plan_id, sequence,
                    status, objective_value, parameters, child_backtest_specification_id,
                    child_backtest_run_id, payload
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (trial_id) DO UPDATE SET
                    status = EXCLUDED.status,
                    objective_value = EXCLUDED.objective_value,
                    payload = EXCLUDED.payload
                """,
                [
                    record.artifact_id,
                    payload.get("optimization_run_id"),
                    payload.get("optimization_plan_id"),
                    payload.get("sequence"),
                    payload.get("status") or record.status,
                    payload.get("objective_value"),
                    Jsonb(dict(payload.get("parameters") or {})),
                    child_refs.get("backtest_specification_id"),
                    child_refs.get("backtest_run_id"),
                    Jsonb(payload),
                ],
            )
        elif artifact_type == EXPERIMENT_TRACKING_PROJECTION_REPORT:
            profile = payload.get("tracking_profile") or {}
            self._connection.execute(
                """
                INSERT INTO research_experiment_tracking_projections (
                    projection_id, canonical_run_id, tracking_profile, status, authoritative, payload
                ) VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (projection_id) DO UPDATE SET
                    status = EXCLUDED.status,
                    payload = EXCLUDED.payload
                """,
                [
                    record.artifact_id,
                    payload.get("canonical_run_id"),
                    profile.get("profile_name"),
                    payload.get("status") or record.status,
                    bool(payload.get("authoritative")),
                    Jsonb(payload),
                ],
            )
        elif artifact_type == PARAMETER_OPTIMIZATION_EVALUATION_REPORT:
            self._connection.execute(
                """
                INSERT INTO research_parameter_optimization_evaluations (
                    report_id, optimization_run_id, holdout_backtest_run_id, status, payload
                ) VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (report_id) DO UPDATE SET status = EXCLUDED.status, payload = EXCLUDED.payload
                """,
                [
                    record.artifact_id,
                    payload.get("optimization_run_id"),
                    payload.get("holdout_backtest_run_id"),
                    payload.get("status") or record.status,
                    Jsonb(payload),
                ],
            )
        elif artifact_type == PARAMETER_OPTIMIZATION_AUDIT_PLAN:
            self._connection.execute(
                """
                INSERT INTO research_parameter_optimization_audit_plans (
                    audit_plan_id, baseline_optimization_run_id, status, payload
                ) VALUES (%s, %s, %s, %s)
                ON CONFLICT (audit_plan_id) DO UPDATE SET status = EXCLUDED.status, payload = EXCLUDED.payload
                """,
                [
                    record.artifact_id,
                    payload.get("baseline_optimization_run_id"),
                    payload.get("status") or record.status,
                    Jsonb(payload),
                ],
            )
        elif artifact_type == PARAMETER_OPTIMIZATION_ROBUSTNESS_REPORT:
            self._connection.execute(
                """
                INSERT INTO research_parameter_optimization_robustness_reports (
                    report_id, audit_plan_id, baseline_optimization_run_id, status, payload
                ) VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (report_id) DO UPDATE SET status = EXCLUDED.status, payload = EXCLUDED.payload
                """,
                [
                    record.artifact_id,
                    payload.get("audit_plan_id"),
                    payload.get("baseline_optimization_run_id"),
                    payload.get("status") or record.status,
                    Jsonb(payload),
                ],
            )
        elif artifact_type == METHODOLOGY_CANDIDATE:
            self._connection.execute(
                """
                INSERT INTO research_methodology_candidates (candidate_id, status, families, source_ids, chunk_ids, payload)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (candidate_id) DO UPDATE SET
                    status = EXCLUDED.status,
                    families = EXCLUDED.families,
                    source_ids = EXCLUDED.source_ids,
                    chunk_ids = EXCLUDED.chunk_ids,
                    payload = EXCLUDED.payload
                """,
                [
                    record.artifact_id,
                    payload.get("status") or record.status,
                    [str(item) for item in payload.get("families", [])],
                    [str(item) for item in payload.get("source_ids", [])],
                    [str(item) for item in payload.get("chunk_ids", [])],
                    Jsonb(payload),
                ],
            )
        elif artifact_type == METHODOLOGY_FIELD_EXTRACTION_REPORT:
            self._connection.execute(
                """
                INSERT INTO research_methodology_field_extractions (
                    extraction_id, candidate_id, status, populated_field_count, payload
                )
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (extraction_id) DO UPDATE SET
                    candidate_id = EXCLUDED.candidate_id,
                    status = EXCLUDED.status,
                    populated_field_count = EXCLUDED.populated_field_count,
                    payload = EXCLUDED.payload
                """,
                [
                    record.artifact_id,
                    payload.get("methodology_candidate_id"),
                    payload.get("status") or record.status,
                    int(payload.get("populated_field_count") or 0),
                    Jsonb(payload),
                ],
            )
        elif artifact_type == METHODOLOGY_EVIDENCE_PACKET:
            self._connection.execute(
                """
                INSERT INTO research_methodology_evidence_packets (
                    evidence_packet_id, candidate_id, family, readiness_goal, status,
                    source_ids, chunk_ids, missing_roles, payload
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (evidence_packet_id) DO UPDATE SET
                    candidate_id = EXCLUDED.candidate_id,
                    family = EXCLUDED.family,
                    readiness_goal = EXCLUDED.readiness_goal,
                    status = EXCLUDED.status,
                    source_ids = EXCLUDED.source_ids,
                    chunk_ids = EXCLUDED.chunk_ids,
                    missing_roles = EXCLUDED.missing_roles,
                    payload = EXCLUDED.payload
                """,
                [
                    record.artifact_id,
                    payload.get("methodology_candidate_id"),
                    payload.get("family"),
                    payload.get("readiness_goal"),
                    payload.get("status") or record.status,
                    [str(item) for item in payload.get("source_ids", [])],
                    [str(item) for item in payload.get("chunk_ids", [])],
                    [str(item) for item in payload.get("missing_roles", [])],
                    Jsonb(payload),
                ],
            )
        elif artifact_type == METHODOLOGY_CANDIDATE_VALIDATION_REPORT:
            self._connection.execute(
                """
                INSERT INTO research_methodology_validations (validation_id, candidate_id, status, payload)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (validation_id) DO UPDATE SET
                    candidate_id = EXCLUDED.candidate_id,
                    status = EXCLUDED.status,
                    payload = EXCLUDED.payload
                """,
                [
                    record.artifact_id,
                    payload.get("methodology_candidate_id"),
                    payload.get("status") or record.status,
                    Jsonb(payload),
                ],
            )
        elif artifact_type == BACKTEST_RUN:
            self._connection.execute(
                """
                INSERT INTO research_backtest_runs (
                    run_id, backtest_kind, status, dataset_id,
                    backtest_specification_id, strategy_specification_id,
                    risk_stack_specification_id, selection_origin_ref,
                    parent_specification_ref, variant_reason, summary, payload
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (run_id) DO UPDATE SET
                    backtest_kind = EXCLUDED.backtest_kind,
                    status = EXCLUDED.status,
                    dataset_id = EXCLUDED.dataset_id,
                    backtest_specification_id = EXCLUDED.backtest_specification_id,
                    strategy_specification_id = EXCLUDED.strategy_specification_id,
                    risk_stack_specification_id = EXCLUDED.risk_stack_specification_id,
                    selection_origin_ref = EXCLUDED.selection_origin_ref,
                    parent_specification_ref = EXCLUDED.parent_specification_ref,
                    variant_reason = EXCLUDED.variant_reason,
                    summary = EXCLUDED.summary,
                    payload = EXCLUDED.payload
                """,
                [
                    record.artifact_id,
                    payload.get("backtest_kind"),
                    payload.get("status") or record.status,
                    payload.get("dataset_id"),
                    payload.get("backtest_specification_id"),
                    payload.get("strategy_specification_id"),
                    payload.get("risk_stack_specification_id"),
                    payload.get("selection_origin_ref"),
                    payload.get("parent_specification_ref"),
                    payload.get("variant_reason"),
                    Jsonb(dict(payload.get("summary") or {})),
                    Jsonb(payload),
                ],
            )
