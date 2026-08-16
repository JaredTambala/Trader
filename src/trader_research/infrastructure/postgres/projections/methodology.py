"""Write typed Postgres projections for Methodology-owned artifacts.

Writers flatten candidate, evidence-packet, extraction, and validation fields
from canonical records for bounded queries. They run inside the artifact-store
transaction and do not create or revise methodology evidence themselves.
"""

from __future__ import annotations

from typing import Any

from trader_research.foundation.artifacts import ResearchArtifactRecord
from trader_research.governance.artifacts import (
    METHODOLOGY_CANDIDATE,
    METHODOLOGY_FIELD_EXTRACTION_REPORT,
    METHODOLOGY_EVIDENCE_PACKET,
    METHODOLOGY_CANDIDATE_VALIDATION_REPORT,
)


def write_methodology_candidate(
    connection: Any, record: ResearchArtifactRecord, json_value: Any
) -> None:
    """Upsert query fields for one methodology candidate.

    Candidate status, normalized families, source and chunk lineage, and the
    complete payload are written through the caller's active artifact transaction.
    The writer performs no discovery or candidate validation.
    """
    payload = dict(record.payload)
    connection.execute(
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
            json_value(payload),
        ],
    )


def write_methodology_field_extraction_report(
    connection: Any, record: ResearchArtifactRecord, json_value: Any
) -> None:
    """Upsert one methodology field-extraction projection.

    Extraction and candidate identity, status, populated-field count, and the
    complete canonical report are projected. Database errors propagate so the
    base artifact and query row roll back together.
    """
    payload = dict(record.payload)
    connection.execute(
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
            json_value(payload),
        ],
    )


def write_methodology_evidence_packet(
    connection: Any, record: ResearchArtifactRecord, json_value: Any
) -> None:
    """Upsert query fields for one methodology evidence packet.

    Candidate lineage, family, readiness goal, status, sources, chunks, missing
    roles, and the complete payload are stored for bounded queries. The caller
    retains transaction ownership.
    """
    payload = dict(record.payload)
    connection.execute(
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
            json_value(payload),
        ],
    )


def write_methodology_candidate_validation_report(
    connection: Any, record: ResearchArtifactRecord, json_value: Any
) -> None:
    """Upsert one methodology-candidate validation projection.

    Validation and candidate identity, status, and the complete report payload
    are derived from the canonical record. The writer neither revises the
    candidate nor determines validation status.
    """
    payload = dict(record.payload)
    connection.execute(
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
            json_value(payload),
        ],
    )


PROJECTION_WRITERS = {
    METHODOLOGY_CANDIDATE: write_methodology_candidate,
    METHODOLOGY_FIELD_EXTRACTION_REPORT: write_methodology_field_extraction_report,
    METHODOLOGY_EVIDENCE_PACKET: write_methodology_evidence_packet,
    METHODOLOGY_CANDIDATE_VALIDATION_REPORT: write_methodology_candidate_validation_report,
}
