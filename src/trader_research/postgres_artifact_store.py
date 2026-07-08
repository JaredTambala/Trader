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
    BACKTEST_RUN_REF,
    EVALUATION_REPORT,
    PORTFOLIO_BACKTEST_RUN_REF,
    RISK_MANAGER_CANDIDATE,
    RISK_MANAGER_CANDIDATE_VALIDATION_REPORT,
    STRATEGY_CANDIDATE,
    STRATEGY_CANDIDATE_VALIDATION_REPORT,
    STRATEGY_RISK_STACK,
    STRATEGY_RISK_STACK_VALIDATION_REPORT,
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
    CREATE TABLE IF NOT EXISTS research_strategy_candidates (
        candidate_id TEXT PRIMARY KEY,
        template_family TEXT NOT NULL,
        status TEXT,
        source_hash TEXT,
        payload JSONB NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS research_strategy_validations (
        validation_id TEXT PRIMARY KEY,
        candidate_id TEXT NOT NULL,
        status TEXT NOT NULL,
        payload JSONB NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS research_risk_manager_candidates (
        candidate_id TEXT PRIMARY KEY,
        template_family TEXT NOT NULL,
        status TEXT,
        source_hash TEXT,
        payload JSONB NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS research_risk_manager_validations (
        validation_id TEXT PRIMARY KEY,
        candidate_id TEXT NOT NULL,
        status TEXT NOT NULL,
        payload JSONB NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS research_strategy_risk_stacks (
        stack_id TEXT PRIMARY KEY,
        status TEXT,
        strategy_candidate_id TEXT,
        risk_manager_ids TEXT[] NOT NULL DEFAULT '{}',
        payload JSONB NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS research_stack_validations (
        validation_id TEXT PRIMARY KEY,
        stack_id TEXT NOT NULL,
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
        candidate_id TEXT,
        strategy_risk_stack_id TEXT,
        strategy_risk_stack_validation_id TEXT,
        summary JSONB NOT NULL DEFAULT '{}'::jsonb,
        payload JSONB NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS research_backtest_sidecars (
        run_id TEXT NOT NULL,
        artifact_type TEXT NOT NULL,
        payload JSONB NOT NULL,
        PRIMARY KEY (run_id, artifact_type)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS research_evaluation_reports (
        report_id TEXT PRIMARY KEY,
        run_id TEXT,
        status TEXT NOT NULL,
        report_kind TEXT,
        payload JSONB NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS research_artifacts_type_status_idx ON research_artifacts(artifact_type, status)",
    "CREATE INDEX IF NOT EXISTS research_backtest_runs_kind_status_idx ON research_backtest_runs(backtest_kind, status)",
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
        if artifact_type == STRATEGY_CANDIDATE:
            self._connection.execute(
                """
                INSERT INTO research_strategy_candidates (candidate_id, template_family, status, source_hash, payload)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (candidate_id) DO UPDATE SET
                    template_family = EXCLUDED.template_family,
                    status = EXCLUDED.status,
                    source_hash = EXCLUDED.source_hash,
                    payload = EXCLUDED.payload
                """,
                [
                    record.artifact_id,
                    payload.get("template_family"),
                    payload.get("status") or record.status,
                    record.source_hash,
                    Jsonb(payload),
                ],
            )
        elif artifact_type == STRATEGY_CANDIDATE_VALIDATION_REPORT:
            self._connection.execute(
                """
                INSERT INTO research_strategy_validations (validation_id, candidate_id, status, payload)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (validation_id) DO UPDATE SET
                    candidate_id = EXCLUDED.candidate_id,
                    status = EXCLUDED.status,
                    payload = EXCLUDED.payload
                """,
                [record.artifact_id, payload.get("candidate_id"), payload.get("status"), Jsonb(payload)],
            )
        elif artifact_type == RISK_MANAGER_CANDIDATE:
            self._connection.execute(
                """
                INSERT INTO research_risk_manager_candidates (candidate_id, template_family, status, source_hash, payload)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (candidate_id) DO UPDATE SET
                    template_family = EXCLUDED.template_family,
                    status = EXCLUDED.status,
                    source_hash = EXCLUDED.source_hash,
                    payload = EXCLUDED.payload
                """,
                [
                    record.artifact_id,
                    payload.get("template_family"),
                    payload.get("status") or record.status,
                    record.source_hash,
                    Jsonb(payload),
                ],
            )
        elif artifact_type == RISK_MANAGER_CANDIDATE_VALIDATION_REPORT:
            self._connection.execute(
                """
                INSERT INTO research_risk_manager_validations (validation_id, candidate_id, status, payload)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (validation_id) DO UPDATE SET
                    candidate_id = EXCLUDED.candidate_id,
                    status = EXCLUDED.status,
                    payload = EXCLUDED.payload
                """,
                [record.artifact_id, payload.get("candidate_id"), payload.get("status"), Jsonb(payload)],
            )
        elif artifact_type == STRATEGY_RISK_STACK:
            risk_ids = [
                str(ref.get("artifact_id"))
                for ref in payload.get("risk_manager_refs", [])
                if isinstance(ref, MappingABC)
            ]
            strategy_ref = payload.get("strategy_candidate_ref") or {}
            self._connection.execute(
                """
                INSERT INTO research_strategy_risk_stacks (
                    stack_id, status, strategy_candidate_id, risk_manager_ids, payload
                )
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (stack_id) DO UPDATE SET
                    status = EXCLUDED.status,
                    strategy_candidate_id = EXCLUDED.strategy_candidate_id,
                    risk_manager_ids = EXCLUDED.risk_manager_ids,
                    payload = EXCLUDED.payload
                """,
                [
                    record.artifact_id,
                    payload.get("status") or record.status,
                    strategy_ref.get("artifact_id") if isinstance(strategy_ref, MappingABC) else None,
                    risk_ids,
                    Jsonb(payload),
                ],
            )
        elif artifact_type == STRATEGY_RISK_STACK_VALIDATION_REPORT:
            self._connection.execute(
                """
                INSERT INTO research_stack_validations (validation_id, stack_id, status, payload)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (validation_id) DO UPDATE SET
                    stack_id = EXCLUDED.stack_id,
                    status = EXCLUDED.status,
                    payload = EXCLUDED.payload
                """,
                [record.artifact_id, payload.get("stack_id"), payload.get("status"), Jsonb(payload)],
            )
        elif artifact_type in {BACKTEST_RUN_REF, PORTFOLIO_BACKTEST_RUN_REF}:
            self._connection.execute(
                """
                INSERT INTO research_backtest_runs (
                    run_id, backtest_kind, status, dataset_id, candidate_id,
                    strategy_risk_stack_id, strategy_risk_stack_validation_id, summary, payload
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (run_id) DO UPDATE SET
                    backtest_kind = EXCLUDED.backtest_kind,
                    status = EXCLUDED.status,
                    dataset_id = EXCLUDED.dataset_id,
                    candidate_id = EXCLUDED.candidate_id,
                    strategy_risk_stack_id = EXCLUDED.strategy_risk_stack_id,
                    strategy_risk_stack_validation_id = EXCLUDED.strategy_risk_stack_validation_id,
                    summary = EXCLUDED.summary,
                    payload = EXCLUDED.payload
                """,
                [
                    record.artifact_id,
                    "portfolio" if artifact_type == PORTFOLIO_BACKTEST_RUN_REF else "baseline",
                    payload.get("status") or record.status,
                    payload.get("dataset_id"),
                    payload.get("candidate_id"),
                    payload.get("strategy_risk_stack_id"),
                    payload.get("strategy_risk_stack_validation_id"),
                    Jsonb(dict(payload.get("summary") or {})),
                    Jsonb(payload),
                ],
            )
        elif artifact_type == EVALUATION_REPORT:
            self._connection.execute(
                """
                INSERT INTO research_evaluation_reports (report_id, run_id, status, report_kind, payload)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (report_id) DO UPDATE SET
                    run_id = EXCLUDED.run_id,
                    status = EXCLUDED.status,
                    report_kind = EXCLUDED.report_kind,
                    payload = EXCLUDED.payload
                """,
                [
                    record.artifact_id,
                    payload.get("run_id"),
                    payload.get("status"),
                    payload.get("report_kind"),
                    Jsonb(payload),
                ],
            )
