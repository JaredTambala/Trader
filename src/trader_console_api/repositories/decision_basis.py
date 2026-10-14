"""Read canonical run decision inputs through enforced read-only database transactions."""

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from typing import Any

from psycopg.types.json import Jsonb

from trader_research.foundation import json_payload_hash, research_artifact_uri
from trader_research.governance.handoffs import ArtifactReportRef

from .database import ConsoleDatabase
from .next_research_decisions import (
    NextResearchDecisionEvidenceUnavailable,
    NextResearchDecisionSession,
)
from .resources import _row_dicts


class DecisionBasisSession(NextResearchDecisionSession):
    """Resolve only exact published identities, rejecting ambiguous discoveries."""

    async def artifact(self, kind: str, identity: str) -> dict[str, Any] | None:
        """Read one canonical record without guessing an owner or source hash."""
        cursor = await self._connection.execute(
            "SELECT * FROM research_artifacts WHERE artifact_type = %s AND artifact_id = %s",
            [kind, identity],
        )
        rows = _row_dicts(cursor, await cursor.fetchall())
        return rows[0] if rows else None

    async def resolve(self, reference: dict[str, Any]) -> dict[str, Any]:
        """Check producer-pinned references before deriving a browser reference."""
        return await self._canonical(ArtifactReportRef.from_dict(reference))

    async def outcomes(self, run_id: str) -> list[dict[str, Any]]:
        """Find terminal records that explicitly cite this exact run artifact."""
        cursor = await self._connection.execute(
            "SELECT * FROM research_artifacts WHERE artifact_type = 'workflow_outcome' "
            "AND payload->'produced_artifact_refs' @> %s ORDER BY artifact_id LIMIT 2",
            [Jsonb([{"artifact_type": "backtest_run", "artifact_id": run_id}])],
        )
        return _row_dicts(cursor, await cursor.fetchall())

    async def linked(self, run_id: str, kinds: tuple[str, ...]) -> list[dict[str, Any]]:
        """Read bounded artifacts whose published payload explicitly names the run."""
        cursor = await self._connection.execute(
            "SELECT * FROM research_artifacts WHERE artifact_type = ANY(%s) "
            "AND payload->>'run_id' = %s ORDER BY artifact_type, artifact_id LIMIT 33",
            [list(kinds), run_id],
        )
        rows = _row_dicts(cursor, await cursor.fetchall())
        if len(rows) > 32:
            raise NextResearchDecisionEvidenceUnavailable("Run evidence exceeds the bounded decision projection")
        return rows


def pinned_reference(record: dict[str, Any]) -> dict[str, Any]:
    """Publish actual canonical identity and a hash of the retained payload."""
    kind, identity = record["artifact_type"], record["artifact_id"]
    metadata = {key: value for key, value in dict(record.get("metadata") or {}).items()
                if key in {"scope_fingerprint", "session_id", "session_digest", "graph_digest", "branch_id", "revision", "node_key"}}
    metadata["payload_sha256"] = json_payload_hash(record["payload"])
    if record.get("source_hash"):
        metadata["source_hash"] = record["source_hash"]
    return {
        "artifact_type": kind, "artifact_id": identity,
        "domain_owner": record["domain_owner"],
        "uri": research_artifact_uri(kind, identity), "metadata": metadata,
    }


class DecisionBasisRepository:
    """Read canonical evidence without installing or mutating storage."""

    def __init__(self, database: ConsoleDatabase, scope_id: str) -> None:
        """Bind the configured database and server-owned scope."""
        self._database = database
        self._scope_id = scope_id

    @asynccontextmanager
    async def session(self) -> AsyncIterator[DecisionBasisSession]:
        """Yield a read-only resolver sharing the command's canonical validator."""
        async with self._database.transaction() as connection:
            yield DecisionBasisSession(connection, self._scope_id)
