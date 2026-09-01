"""Canonical services for agent sessions, receipts, and bounded reads."""

from __future__ import annotations

import json
from typing import Any, Mapping

from trader_research.foundation import (
    ApplicationResult,
    ORCHESTRATION_DOMAIN_OWNER,
    ResearchArtifactNotFound,
    ResearchArtifactRecord,
    ResearchArtifactStore,
    ResearchArtifactStoreError,
    error_result,
    json_payload_hash,
    parse_research_artifact_uri,
    success_result,
)
from trader_research.governance.artifacts import (
    AGENT_DECISION_RECEIPT,
    DOMAIN_OWNER_BY_ARTIFACT_TYPE,
    RESEARCH_SESSION,
    SUPPORTED_ARTIFACT_TYPES,
)

from .domain import AgentDecisionReceipt, AgentDecisionStatus, ResearchSession


RESEARCH_CREATE_AGENT_SESSION = "research_create_agent_session"
RESEARCH_GET_AGENT_SESSION = "research_get_agent_session"
RESEARCH_RECORD_AGENT_DECISION = "research_record_agent_decision"
RESEARCH_GET_AGENT_DECISION = "research_get_agent_decision"
RESEARCH_READ_ARTIFACT = "research_read_artifact"


def create_agent_session(
    session_payload: Mapping[str, Any],
    *,
    artifact_store: ResearchArtifactStore | None,
) -> ApplicationResult:
    """Validate and idempotently persist one immutable research session.

    Args:
        session_payload: Complete operator-approved session payload.
        artifact_store: Canonical evidence store.

    Returns:
        Session payload and canonical ref, or a structured validation failure.
    """
    command = RESEARCH_CREATE_AGENT_SESSION
    if artifact_store is None:
        return _store_required(command)
    try:
        session = ResearchSession.from_dict(session_payload)
        record = _save_immutable(
            artifact_store,
            artifact_type=RESEARCH_SESSION,
            artifact_id=session.session_id,
            producer_tool=command,
            payload=session.to_dict(),
            requested_by=session.operator_id,
            actor="Research Coordinator",
            status="active",
            source_hash=session.session_digest,
        )
    except (ValueError, ResearchArtifactStoreError) as exc:
        return error_result(
            command=command,
            code="agent_session_creation_failed",
            message=str(exc),
        )
    return success_result(
        command=command,
        data={"research_session": session.to_dict()},
        artifacts={"research_session": record.reference().to_dict()},
    )


def get_agent_session(
    session_ref: str,
    *,
    artifact_store: ResearchArtifactStore | None,
) -> ApplicationResult:
    """Resolve one exact immutable research session.

    Args:
        session_ref: Session ID or canonical URI.
        artifact_store: Canonical evidence store.

    Returns:
        Validated session payload and bounded canonical record metadata.
    """
    command = RESEARCH_GET_AGENT_SESSION
    if artifact_store is None:
        return _store_required(command)
    try:
        record = _load_record(artifact_store, RESEARCH_SESSION, session_ref)
        session = ResearchSession.from_dict(record.payload)
    except (ValueError, ResearchArtifactStoreError) as exc:
        return error_result(
            command=command,
            code="agent_session_resolution_failed",
            message=str(exc),
        )
    return success_result(
        command=command,
        data={"research_session": session.to_dict()},
        artifacts={"research_session": record.reference().to_dict()},
    )


def record_agent_decision(
    receipt_payload: Mapping[str, Any],
    *,
    artifact_store: ResearchArtifactStore | None,
) -> ApplicationResult:
    """Validate evidence and persist one immutable coordinator receipt.

    The owning session, program and model identities are revalidated. Branch
    sequences are append-only, cumulative budget use cannot decrease or exceed
    the session limits, terminal branches cannot accept later decisions, and
    every cited canonical ref is resolved before persistence.

    Args:
        receipt_payload: Complete content-addressed public receipt.
        artifact_store: Canonical evidence store.

    Returns:
        Receipt payload and canonical ref, or a structured fail-closed result.
    """
    command = RESEARCH_RECORD_AGENT_DECISION
    if artifact_store is None:
        return _store_required(command)
    try:
        receipt = AgentDecisionReceipt.from_dict(receipt_payload)
        session_record = artifact_store.load_artifact_record(
            RESEARCH_SESSION,
            receipt.session_id,
        )
        session = ResearchSession.from_dict(session_record.payload)
        _validate_receipt_against_session(receipt, session)
        _validate_receipt_sequence(receipt, artifact_store)
        for evidence_ref in receipt.evidence_refs:
            _resolve_evidence_ref(artifact_store, evidence_ref.to_dict())
        record = _save_immutable(
            artifact_store,
            artifact_type=AGENT_DECISION_RECEIPT,
            artifact_id=receipt.receipt_id,
            producer_tool=command,
            payload=receipt.to_dict(),
            requested_by=receipt.session_id,
            actor=receipt.actor,
            status=receipt.status.value,
            source_hash=receipt.decision_digest,
        )
    except (ValueError, ResearchArtifactStoreError) as exc:
        return error_result(
            command=command,
            code="agent_decision_recording_failed",
            message=str(exc),
        )
    return success_result(
        command=command,
        data={"agent_decision_receipt": receipt.to_dict()},
        artifacts={"agent_decision_receipt": record.reference().to_dict()},
    )


def get_agent_decision(
    receipt_ref: str,
    *,
    artifact_store: ResearchArtifactStore | None,
) -> ApplicationResult:
    """Resolve one exact canonical agent decision receipt."""
    command = RESEARCH_GET_AGENT_DECISION
    if artifact_store is None:
        return _store_required(command)
    try:
        record = _load_record(
            artifact_store,
            AGENT_DECISION_RECEIPT,
            receipt_ref,
        )
        receipt = AgentDecisionReceipt.from_dict(record.payload)
    except (ValueError, ResearchArtifactStoreError) as exc:
        return error_result(
            command=command,
            code="agent_decision_resolution_failed",
            message=str(exc),
        )
    return success_result(
        command=command,
        data={"agent_decision_receipt": receipt.to_dict()},
        artifacts={"agent_decision_receipt": record.reference().to_dict()},
    )


def read_canonical_artifact(
    artifact_ref: str,
    expected_artifact_type: str,
    *,
    artifact_store: ResearchArtifactStore | None,
    max_payload_bytes: int = 64_000,
    include_payload: bool = True,
) -> ApplicationResult:
    """Read one exact bounded canonical artifact with governance metadata.

    Args:
        artifact_ref: Exact artifact ID or canonical URI.
        expected_artifact_type: Required registered artifact type.
        artifact_store: Canonical evidence store.
        max_payload_bytes: Maximum compact JSON payload bytes returned.
        include_payload: Whether to return the complete bounded payload. Set
            false when exact identity, lineage, and hashes are sufficient.

    Returns:
        Exact record metadata, payload hash, and bounded payload.
    """
    command = RESEARCH_READ_ARTIFACT
    if artifact_store is None:
        return _store_required(command)
    try:
        if expected_artifact_type not in SUPPORTED_ARTIFACT_TYPES:
            raise ValueError(
                f"unsupported expected_artifact_type: {expected_artifact_type}"
            )
        if not 1 <= max_payload_bytes <= 256_000:
            raise ValueError("max_payload_bytes must be between 1 and 256000")
        record = _load_record(
            artifact_store,
            expected_artifact_type,
            artifact_ref,
        )
        expected_owner = DOMAIN_OWNER_BY_ARTIFACT_TYPE[expected_artifact_type]
        if record.domain_owner != expected_owner:
            raise ValueError(
                f"artifact domain owner {record.domain_owner} does not match "
                f"registered owner {expected_owner}"
            )
        encoded = json.dumps(
            record.payload,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
        if len(encoded) > max_payload_bytes:
            raise ValueError(
                f"artifact payload is {len(encoded)} bytes; limit is {max_payload_bytes}"
            )
    except (ValueError, ResearchArtifactStoreError) as exc:
        return error_result(
            command=command,
            code="canonical_artifact_read_failed",
            message=str(exc),
        )
    public_record = {
        "artifact_type": record.artifact_type,
        "artifact_id": record.artifact_id,
        "domain_owner": record.domain_owner,
        "producer_tool": record.producer_tool,
        "requested_by": record.requested_by,
        "actor": record.actor,
        "status": record.status,
        "schema_version": record.schema_version,
        "source_hash": record.source_hash,
        "payload_hash": json_payload_hash(record.payload),
        "payload_bytes": len(encoded),
        "metadata": dict(record.metadata),
    }
    if include_payload:
        public_record["payload"] = dict(record.payload)
    return success_result(
        command=command,
        data={"record": public_record},
        artifacts={"artifact": record.reference().to_dict()},
    )


def _validate_receipt_against_session(
    receipt: AgentDecisionReceipt,
    session: ResearchSession,
) -> None:
    """Validate program, model, and cumulative budget session pins."""
    if receipt.program_id not in session.agent_program_ids:
        raise ValueError("decision program_id is not admitted by the session")
    if receipt.model_profile_id != session.model_profile_id:
        raise ValueError("decision model_profile_id does not match the session")
    receipt.budget_used.validate_within(session.budget)


def _validate_receipt_sequence(
    receipt: AgentDecisionReceipt,
    artifact_store: ResearchArtifactStore,
) -> None:
    """Enforce branch append-only ordering and cumulative counters."""
    branch_receipts = []
    for record in artifact_store.list_artifacts(
        artifact_type=AGENT_DECISION_RECEIPT
    ):
        candidate = AgentDecisionReceipt.from_dict(record.payload)
        if (
            candidate.session_id == receipt.session_id
            and candidate.branch_id == receipt.branch_id
        ):
            branch_receipts.append(candidate)
    if not branch_receipts:
        if receipt.sequence != 1:
            raise ValueError("the first branch decision must have sequence 1")
        return
    latest = max(branch_receipts, key=lambda item: item.sequence)
    if latest.status in {
        AgentDecisionStatus.CANCELLED,
        AgentDecisionStatus.TERMINAL,
    }:
        raise ValueError("a terminal research branch cannot accept another decision")
    if receipt.sequence != latest.sequence + 1:
        raise ValueError("decision sequence must append exactly after the latest receipt")
    previous_usage = latest.budget_used.to_dict()
    current_usage = receipt.budget_used.to_dict()
    decreased = [
        key for key, previous in previous_usage.items() if current_usage[key] < previous
    ]
    if decreased:
        raise ValueError(f"cumulative budget usage decreased: {', '.join(decreased)}")


def _resolve_evidence_ref(
    artifact_store: ResearchArtifactStore,
    reference: Mapping[str, Any],
) -> ResearchArtifactRecord:
    """Resolve and verify one typed canonical evidence reference."""
    artifact_type = str(reference.get("artifact_type") or "")
    artifact_id = str(reference.get("artifact_id") or "")
    record = artifact_store.load_artifact_record(artifact_type, artifact_id)
    if record.uri != reference.get("uri"):
        raise ValueError("decision evidence URI does not match canonical identity")
    if record.domain_owner != reference.get("domain_owner"):
        raise ValueError("decision evidence domain owner does not match canonical record")
    metadata = reference.get("metadata")
    if isinstance(metadata, Mapping):
        expected_hash = metadata.get("source_hash")
        if expected_hash is not None and expected_hash != record.source_hash:
            raise ValueError("decision evidence source hash does not match canonical record")
    return record


def _save_immutable(
    artifact_store: ResearchArtifactStore,
    *,
    artifact_type: str,
    artifact_id: str,
    producer_tool: str,
    payload: Mapping[str, Any],
    requested_by: str,
    actor: str,
    status: str,
    source_hash: str,
) -> ResearchArtifactRecord:
    """Return exact replay or save without overwriting conflicting evidence."""
    try:
        existing = artifact_store.load_artifact_record(artifact_type, artifact_id)
    except ResearchArtifactNotFound:
        return artifact_store.save_artifact(
            artifact_type=artifact_type,
            artifact_id=artifact_id,
            domain_owner=ORCHESTRATION_DOMAIN_OWNER,
            producer_tool=producer_tool,
            payload=payload,
            requested_by=requested_by,
            actor=actor,
            status=status,
            source_hash=source_hash,
        )
    if dict(existing.payload) != dict(payload):
        raise ResearchArtifactStoreError(
            f"conflicting immutable {artifact_type}: {artifact_id}"
        )
    if (
        existing.domain_owner != ORCHESTRATION_DOMAIN_OWNER
        or existing.producer_tool != producer_tool
        or existing.requested_by != requested_by
        or existing.actor != actor
        or existing.status != status
        or existing.source_hash != source_hash
    ):
        raise ResearchArtifactStoreError(
            f"immutable {artifact_type} governance metadata drift: {artifact_id}"
        )
    return existing


def _load_record(
    artifact_store: ResearchArtifactStore,
    artifact_type: str,
    artifact_ref: str,
) -> ResearchArtifactRecord:
    """Resolve an exact ID or URI into a full canonical record."""
    value = str(artifact_ref or "").strip()
    if not value:
        raise ValueError("artifact reference is required")
    artifact_id = value
    if value.startswith("research://"):
        parsed_type, artifact_id = parse_research_artifact_uri(value)
        if parsed_type != artifact_type:
            raise ValueError(
                f"artifact URI type {parsed_type} does not match expected {artifact_type}"
            )
    return artifact_store.load_artifact_record(artifact_type, artifact_id)


def _store_required(command: str) -> ApplicationResult:
    """Return the shared fail-closed missing-store result."""
    return error_result(
        command=command,
        code="research_artifact_store_required",
        message="A configured ResearchArtifactStore is required.",
    )
