"""Persistence adapter for the research-owned next-decision projection."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from trader_research.foundation import json_payload_hash, research_artifact_uri
from trader_research.governance import NextResearchDecision
from trader_research.governance.handoffs import ArtifactReportRef

from .database import ConsoleDatabase, ConsoleDatabaseUnavailable
from .next_research_decisions_schema import (
    CATALOG_SQL,
    COLUMNS,
    NextResearchDecisionStorageUnavailable,
)
from .resources import _row_dicts


class NextResearchDecisionConflict(RuntimeError):
    """A decision identity or revision conflicts with an immutable record."""


class NextResearchDecisionNotFound(RuntimeError):
    """A requested decision is absent from the configured scope."""


class NextResearchDecisionEvidenceUnavailable(RuntimeError):
    """A cited run or evidence artifact is missing, stale, or incompatible."""


def _timestamp(value: Any) -> datetime:
    """Normalize a database timestamp for typed artifact metadata."""
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc)


def _artifact_row(cursor: Any, rows: list[Any]) -> dict[str, Any] | None:
    """Normalize one canonical artifact row at the adapter boundary."""
    values = _row_dicts(cursor, rows)
    return values[0] if values else None


class NextResearchDecisionSession:
    """One read or command transaction bound to a Console scope."""

    def __init__(self, connection: Any, scope_id: str) -> None:
        """Bind trusted scope identity to every query and write."""
        self._connection = connection
        self._scope_id = scope_id

    async def require_storage(self) -> None:
        """Refuse absent or incompatible research projection storage."""
        cursor = await self._connection.execute(CATALOG_SQL)
        if dict(await cursor.fetchall()) != COLUMNS:
            raise NextResearchDecisionStorageUnavailable(
                "Install research next-decision projection storage explicitly"
            )

    async def _canonical(self, reference: ArtifactReportRef) -> dict[str, Any]:
        """Resolve and verify one exact canonical artifact reference."""
        cursor = await self._connection.execute(
            "SELECT artifact_type, artifact_id, domain_owner, producer_tool, "
            "requested_by, actor, status, schema_version, source_hash, "
            "metadata, payload, created_at, updated_at "
            "FROM research_artifacts WHERE artifact_type = %s AND artifact_id = %s",
            [reference.artifact_type, reference.artifact_id],
        )
        row = _artifact_row(cursor, await cursor.fetchall())
        if row is None:
            raise NextResearchDecisionEvidenceUnavailable(
                f"missing evidence artifact: {reference.artifact_id}"
            )
        if row.get("domain_owner") != reference.domain_owner:
            raise NextResearchDecisionEvidenceUnavailable(
                f"evidence owner changed: {reference.artifact_id}"
            )
        if research_artifact_uri(reference.artifact_type, reference.artifact_id) != reference.uri:
            raise NextResearchDecisionEvidenceUnavailable(
                f"evidence URI changed: {reference.artifact_id}"
            )
        metadata = reference.metadata
        expected_source_hash = metadata.get("source_hash")
        if expected_source_hash is not None and expected_source_hash != row.get("source_hash"):
            raise NextResearchDecisionEvidenceUnavailable(
                f"evidence source hash changed: {reference.artifact_id}"
            )
        expected_payload_hash = metadata.get("payload_sha256")
        if expected_payload_hash is not None and expected_payload_hash != json_payload_hash(row["payload"]):
            raise NextResearchDecisionEvidenceUnavailable(
                f"evidence payload changed: {reference.artifact_id}"
            )
        return row

    async def validate_evidence(
        self,
        decision: NextResearchDecision,
        *,
        run_id: str,
    ) -> None:
        """Resolve every cited artifact and verify it belongs to this reviewed run."""
        if decision.source_run_ref.artifact_id != run_id:
            raise NextResearchDecisionEvidenceUnavailable(
                "source_run_ref must identify the reviewed run in the route"
            )
        source = await self._canonical(decision.source_run_ref)
        source_payload = dict(source.get("payload") or {})
        if str(source_payload.get("run_id") or decision.source_run_ref.artifact_id) != run_id:
            raise NextResearchDecisionEvidenceUnavailable("source run identity is incompatible")
        run_cursor = await self._connection.execute(
            "SELECT runs.run_id, scope.scope_fingerprint "
            "FROM console_read.backtest_runs AS runs "
            "LEFT JOIN console_read.backtest_scope AS scope ON scope.run_id = runs.run_id "
            "WHERE runs.run_id = %s LIMIT 1",
            [run_id],
        )
        run_row = _artifact_row(run_cursor, await run_cursor.fetchall())
        if run_row is None:
            raise NextResearchDecisionEvidenceUnavailable("reviewed run is not published")
        data = await self._canonical(decision.data_ref)
        data_payload = dict(data.get("payload") or {})
        scope_fingerprint = run_row.get("scope_fingerprint")
        data_fingerprint = data_payload.get("scope_fingerprint") or decision.data_ref.metadata.get(
            "scope_fingerprint"
        )
        if scope_fingerprint and data_fingerprint and scope_fingerprint != data_fingerprint:
            raise NextResearchDecisionEvidenceUnavailable("data evidence does not match run scope")
        for reference in decision.implementation_refs:
            await self._canonical(reference)
        for reference in decision.review_refs:
            review = await self._canonical(reference)
            status = str(review.get("status") or "").lower()
            if status in {"missing", "incompatible", "blocked", "failed", "error"}:
                raise NextResearchDecisionEvidenceUnavailable(
                    f"review evidence is not actionable: {reference.artifact_id}"
                )
            review_payload = dict(review.get("payload") or {})
            cited_run = review_payload.get("run_id")
            if cited_run is not None and str(cited_run) != run_id:
                raise NextResearchDecisionEvidenceUnavailable(
                    f"review evidence does not belong to run: {reference.artifact_id}"
                )
            if decision.session_review is not None:
                if not ({"source_hash", "payload_sha256"} & set(reference.metadata)):
                    raise NextResearchDecisionEvidenceUnavailable(
                        f"session review evidence requires a pinned hash: {reference.artifact_id}"
                    )
                prefix = f"{reference.artifact_type}:{reference.artifact_id}:r"
                revision = next(
                    int(key.removeprefix(prefix))
                    for key in decision.session_review.review_node_keys if key.startswith(prefix)
                )
                review_metadata = dict(review.get("metadata") or {})
                if (
                    review_metadata.get("session_id") != decision.session_review.session_id
                    or review_metadata.get("revision") != revision
                ):
                    raise NextResearchDecisionEvidenceUnavailable(
                        f"session review evidence identity changed: {reference.artifact_id}"
                    )
        if decision.next_experiment is not None:
            await self._canonical(decision.next_experiment.data_ref)
            for reference in decision.next_experiment.implementation_refs:
                await self._canonical(reference)

    async def latest(self, decision_id: str) -> tuple[int, str] | None:
        """Return the latest revision and artifact identity for one stream."""
        cursor = await self._connection.execute(
            "SELECT revision, artifact_id FROM research_next_decisions "
            "WHERE decision_id = %s ORDER BY revision DESC LIMIT 1",
            [decision_id],
        )
        rows = await cursor.fetchall()
        if not rows:
            return None
        values = _row_dicts(cursor, rows)[0]
        return int(values["revision"]), str(values["artifact_id"])

    async def create(
        self,
        decision: NextResearchDecision,
        *,
        requested_by: str,
    ) -> NextResearchDecision:
        """Persist the canonical artifact and typed projection atomically."""
        payload = decision.to_dict()
        existing_cursor = await self._connection.execute(
            "SELECT payload FROM research_artifacts "
            "WHERE artifact_type = %s AND artifact_id = %s",
            [decision.artifact_type, decision.artifact_id],
        )
        existing_rows = await existing_cursor.fetchall()
        if existing_rows:
            existing_payload = _row_dicts(existing_cursor, existing_rows)[0]["payload"]
            if dict(existing_payload) != payload:
                raise NextResearchDecisionConflict("immutable decision identity has different content")
            return NextResearchDecision.from_dict(existing_payload)

        artifact_cursor = await self._connection.execute(
            "INSERT INTO research_artifacts ("
            "artifact_type, artifact_id, domain_owner, producer_tool, requested_by, actor, "
            "status, schema_version, source_hash, metadata, payload"
            ") VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
            "RETURNING artifact_id",
            [
                decision.artifact_type,
                decision.artifact_id,
                "Orchestration",
                "console_record_next_decision",
                requested_by,
                decision.operator,
                decision.outcome.value,
                decision.schema_version,
                decision.decision_digest,
                Jsonb({"scope_id": self._scope_id}),
                Jsonb(payload),
            ],
        )
        if not await artifact_cursor.fetchall():
            raise NextResearchDecisionConflict("decision could not be stored")
        projection_cursor = await self._connection.execute(
            "INSERT INTO research_next_decisions ("
            "artifact_id, decision_id, revision, outcome, source_run_id, operator, decided_at, "
            "supersedes_artifact_id, decision_digest, payload"
            ") VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING artifact_id",
            [
                decision.artifact_id,
                decision.decision_id,
                decision.revision,
                decision.outcome.value,
                decision.source_run_ref.artifact_id,
                decision.operator,
                decision.decided_at,
                decision.supersedes_artifact_id,
                decision.decision_digest,
                Jsonb(payload),
            ],
        )
        if not await projection_cursor.fetchall():
            raise NextResearchDecisionConflict("decision projection could not be stored")
        return decision

    async def get(self, run_id: str, decision_id: str, revision: int | None = None) -> NextResearchDecision | None:
        """Load one exact or latest decision revision for a reviewed run."""
        query = (
            "SELECT payload FROM research_next_decisions WHERE source_run_id = %s "
            "AND decision_id = %s "
        )
        parameters: list[Any] = [run_id, decision_id]
        if revision is None:
            query += "ORDER BY revision DESC LIMIT 1"
        else:
            query += "AND revision = %s LIMIT 1"
            parameters.append(revision)
        cursor = await self._connection.execute(query, parameters)
        rows = await cursor.fetchall()
        if not rows:
            return None
        return NextResearchDecision.from_dict(_row_dicts(cursor, rows)[0]["payload"])

    async def list(self, run_id: str, limit: int, offset: int) -> tuple[list[NextResearchDecision], int]:
        """Return latest decision revision per stream for one reviewed run."""
        count_cursor = await self._connection.execute(
            "SELECT count(DISTINCT decision_id) FROM research_next_decisions WHERE source_run_id = %s",
            [run_id],
        )
        total = int((await count_cursor.fetchone())[0])
        cursor = await self._connection.execute(
            "SELECT latest.payload FROM ("
            "SELECT DISTINCT ON (decision_id) payload FROM research_next_decisions "
            "WHERE source_run_id = %s ORDER BY decision_id, revision DESC"
            ") AS latest ORDER BY (latest.payload->>'decided_at') DESC, (latest.payload->>'decision_id') "
            "LIMIT %s OFFSET %s",
            [run_id, limit, offset],
        )
        decisions = [NextResearchDecision.from_dict(row["payload"]) for row in _row_dicts(cursor, await cursor.fetchall())]
        return decisions, total


class NextResearchDecisionRepository:
    """Keep Console decision commands separate from research artifact ownership."""

    def __init__(self, database: ConsoleDatabase, scope_id: str) -> None:
        """Bind every operation to the configured Console scope."""
        self._database = database
        self._scope_id = scope_id

    @property
    def scope_id(self) -> str:
        """Return the server-owned Console scope used by decision metadata."""
        return self._scope_id

    @asynccontextmanager
    async def session(self, *, write: bool = False) -> AsyncIterator[NextResearchDecisionSession]:
        """Yield one read or command transaction and translate database failures."""
        transaction = self._database.command_transaction if write else self._database.transaction
        try:
            async with transaction() as connection:
                yield NextResearchDecisionSession(connection, self._scope_id)
        except ConsoleDatabaseUnavailable as exc:
            if isinstance(exc.__cause__, psycopg.errors.UniqueViolation):
                raise NextResearchDecisionConflict("next-decision revision conflicts with an existing record") from exc
            raise


__all__ = [
    "NextResearchDecisionConflict",
    "NextResearchDecisionEvidenceUnavailable",
    "NextResearchDecisionNotFound",
    "NextResearchDecisionRepository",
    "NextResearchDecisionSession",
    "NextResearchDecisionStorageUnavailable",
]
