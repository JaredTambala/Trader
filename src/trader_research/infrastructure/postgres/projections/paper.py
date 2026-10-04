"""Write typed Postgres projections for human paper-admission records."""

from __future__ import annotations

from typing import Any

from trader_research.foundation.artifacts import ResearchArtifactRecord
from trader_research.governance.artifacts import PAPER_CANDIDATE_ADMISSION


def write_paper_candidate_admission(
    connection: Any, record: ResearchArtifactRecord, json_value: Any
) -> None:
    """Upsert query fields for one immutable human admission record."""
    payload = dict(record.payload)
    connection.execute(
        """
        INSERT INTO research_paper_candidate_admissions (
            admission_id, candidate_ref, strategy_version, risk_version,
            data_version, decision, approver, decided_at, expires_at,
            revoked_at, status, payload
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (admission_id) DO UPDATE SET
            candidate_ref = EXCLUDED.candidate_ref,
            strategy_version = EXCLUDED.strategy_version,
            risk_version = EXCLUDED.risk_version,
            data_version = EXCLUDED.data_version,
            decision = EXCLUDED.decision,
            approver = EXCLUDED.approver,
            decided_at = EXCLUDED.decided_at,
            expires_at = EXCLUDED.expires_at,
            revoked_at = EXCLUDED.revoked_at,
            status = EXCLUDED.status,
            payload = EXCLUDED.payload
        """,
        [
            record.artifact_id,
            payload["candidate_ref"],
            payload["strategy_version"],
            payload["risk_version"],
            payload["data_version"],
            payload["decision"],
            payload["approver"],
            payload["decided_at"],
            payload.get("expires_at"),
            payload.get("revoked_at"),
            payload.get("decision") or record.status,
            json_value(payload),
        ],
    )


PROJECTION_WRITERS = {PAPER_CANDIDATE_ADMISSION: write_paper_candidate_admission}
