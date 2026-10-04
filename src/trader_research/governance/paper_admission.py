"""Human-owned admission records for Trader paper operation.

This module defines the narrow governance boundary between research evidence and
paper-runtime startup. It records exact immutable versions and evidence refs,
requires a human actor for approval or rejection, and revalidates every pinned
reference before a runtime consumer may proceed. It never creates broker orders
or changes runtime state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Mapping

from trader_research.foundation import (
    ApplicationResult,
    ResearchArtifactNotFound,
    ResearchArtifactRecord,
    ResearchArtifactStore,
    ResearchArtifactStoreError,
    error_result,
    json_payload_hash,
    parse_research_artifact_uri,
    stable_research_id,
    success_result,
)

from .artifacts import (
    DOMAIN_OWNER_BY_ARTIFACT_TYPE,
    PAPER_CANDIDATE_ADMISSION,
)
from .ownership import get_agent_definition


PAPER_ADMISSION_CREATE = "paper_create_candidate_admission"
PAPER_ADMISSION_GET = "paper_get_candidate_admission"
PAPER_ADMISSION_VALIDATE = "paper_validate_candidate_admission"
PAPER_ADMISSION_REVOKE = "paper_revoke_candidate_admission"


class PaperAdmissionDecision(StrEnum):
    """Terminal human decision captured by an admission record."""

    APPROVED = "approved"
    REJECTED = "rejected"
    REVOKED = "revoked"


@dataclass(frozen=True)
class PaperCandidateAdmission:
    """Immutable human decision over one exact paper-trading candidate.

    ``evidence_refs`` maps stable evidence names (for example ``backtest`` or
    ``evaluation``) to canonical artifact references. Each ref must include the
    artifact URI, type, ID, domain owner, and payload digest. The digest is
    checked again by :func:`validate_paper_candidate_admission`.
    """

    admission_id: str
    candidate_ref: str
    evidence_refs: Mapping[str, Mapping[str, Any]]
    strategy_version: str
    risk_version: str
    data_version: str
    risk_limits: Mapping[str, Any]
    broker_scope: Mapping[str, Any]
    monitoring_policy: Mapping[str, Any]
    decision: PaperAdmissionDecision
    approver: str
    decided_at: str
    expires_at: str | None = None
    revoked_at: str | None = None
    revocation_reason: str | None = None
    supersedes_admission_id: str | None = None
    unresolved_limitations: tuple[str, ...] = ()
    schema_version: str = "1"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    artifact_type = PAPER_CANDIDATE_ADMISSION

    def __post_init__(self) -> None:
        """Validate exact identity, authority, timestamps, and decision state."""
        for value, label in (
            (self.admission_id, "admission_id"),
            (self.candidate_ref, "candidate_ref"),
            (self.strategy_version, "strategy_version"),
            (self.risk_version, "risk_version"),
            (self.data_version, "data_version"),
            (self.approver, "approver"),
            (self.decided_at, "decided_at"),
        ):
            if not str(value or "").strip():
                raise ValueError(f"{label} is required")
        _require_human_principal(self.approver, "approver")
        if not isinstance(self.decision, PaperAdmissionDecision):
            raise ValueError("decision must be a PaperAdmissionDecision")
        if not self.evidence_refs:
            raise ValueError("evidence_refs are required")
        for name, reference in self.evidence_refs.items():
            if not str(name or "").strip():
                raise ValueError("evidence reference names are required")
            _validate_reference_shape(reference, name)
        for mapping_value, label in (
            (self.risk_limits, "risk_limits"),
            (self.broker_scope, "broker_scope"),
            (self.monitoring_policy, "monitoring_policy"),
            (self.metadata, "metadata"),
        ):
            if not isinstance(mapping_value, Mapping):
                raise ValueError(f"{label} must be a mapping")
        if not isinstance(self.unresolved_limitations, tuple):
            raise ValueError("unresolved_limitations must be a tuple")
        if any(not str(item or "").strip() for item in self.unresolved_limitations):
            raise ValueError("unresolved_limitations must contain non-empty text")
        _parse_timestamp(self.decided_at, "decided_at")
        if self.expires_at is not None:
            _parse_timestamp(self.expires_at, "expires_at")
        if self.revoked_at is not None:
            _parse_timestamp(self.revoked_at, "revoked_at")
        if self.decision is PaperAdmissionDecision.REVOKED:
            if not self.revoked_at or not str(self.revocation_reason or "").strip():
                raise ValueError("revoked admissions require revoked_at and revocation_reason")
        elif self.revoked_at is not None:
            raise ValueError("only revoked admissions may contain revoked_at")
        if self.decision is PaperAdmissionDecision.APPROVED and self.expires_at is None:
            raise ValueError("approved admissions require expires_at")
        if self.decision is PaperAdmissionDecision.REJECTED and self.expires_at is not None:
            raise ValueError("rejected admissions cannot contain expires_at")

    @property
    def digest(self) -> str:
        """Return content identity excluding the derived digest itself."""
        return json_payload_hash(self._identity_payload())

    def to_dict(self) -> dict[str, Any]:
        """Serialize the complete JSON-safe admission payload."""
        return {
            "artifact_type": self.artifact_type,
            "schema_version": self.schema_version,
            **self._identity_payload(),
            "admission_digest": self.digest,
        }

    def _identity_payload(self) -> dict[str, Any]:
        """Return fields that determine the immutable admission content."""
        return {
            "admission_id": self.admission_id,
            "candidate_ref": self.candidate_ref,
            "evidence_refs": {key: dict(value) for key, value in sorted(self.evidence_refs.items())},
            "strategy_version": self.strategy_version,
            "risk_version": self.risk_version,
            "data_version": self.data_version,
            "risk_limits": dict(self.risk_limits),
            "broker_scope": dict(self.broker_scope),
            "monitoring_policy": dict(self.monitoring_policy),
            "decision": self.decision.value,
            "approver": self.approver,
            "decided_at": self.decided_at,
            "expires_at": self.expires_at,
            "revoked_at": self.revoked_at,
            "revocation_reason": self.revocation_reason,
            "supersedes_admission_id": self.supersedes_admission_id,
            "unresolved_limitations": list(self.unresolved_limitations),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "PaperCandidateAdmission":
        """Parse and validate a serialized canonical admission."""
        decision = PaperAdmissionDecision(str(payload.get("decision") or ""))
        admission = cls(
            admission_id=str(payload.get("admission_id") or ""),
            candidate_ref=str(payload.get("candidate_ref") or ""),
            evidence_refs=_mapping_of_mappings(payload.get("evidence_refs")),
            strategy_version=str(payload.get("strategy_version") or ""),
            risk_version=str(payload.get("risk_version") or ""),
            data_version=str(payload.get("data_version") or ""),
            risk_limits=_mapping(payload.get("risk_limits")),
            broker_scope=_mapping(payload.get("broker_scope")),
            monitoring_policy=_mapping(payload.get("monitoring_policy")),
            decision=decision,
            approver=str(payload.get("approver") or ""),
            decided_at=str(payload.get("decided_at") or ""),
            expires_at=_optional_text(payload.get("expires_at")),
            revoked_at=_optional_text(payload.get("revoked_at")),
            revocation_reason=_optional_text(payload.get("revocation_reason")),
            supersedes_admission_id=_optional_text(payload.get("supersedes_admission_id")),
            unresolved_limitations=_text_sequence(payload.get("unresolved_limitations"), "unresolved_limitations"),
            schema_version=str(payload.get("schema_version") or "1"),
            metadata=_mapping(payload.get("metadata")),
        )
        supplied_digest = str(payload.get("admission_digest") or "")
        if supplied_digest and supplied_digest != admission.digest:
            raise ValueError("admission_digest does not match canonical content")
        return admission


def create_paper_candidate_admission(
    payload: Mapping[str, Any],
    *,
    artifact_store: ResearchArtifactStore | None,
    requested_by: str,
    actor: str,
) -> ApplicationResult:
    """Record one human-owned admission after revalidating evidence refs.

    Agents and MCP identities are rejected at this boundary. A successful
    record is immutable and idempotent for the same admission ID and content.
    """
    command = PAPER_ADMISSION_CREATE
    if artifact_store is None:
        return _store_required(command)
    try:
        _require_human_principal(actor, "actor")
        _require_human_principal(requested_by, "requested_by")
        admission = PaperCandidateAdmission.from_dict(payload)
        _validate_evidence_refs(artifact_store, admission)
        record = _save_immutable(
            artifact_store,
            admission=admission,
            command=command,
            requested_by=requested_by,
            actor=actor,
        )
    except (ValueError, ResearchArtifactStoreError) as exc:
        return error_result(command=command, code="paper_admission_failed", message=str(exc))
    return success_result(
        command=command,
        data={"paper_candidate_admission": admission.to_dict()},
        artifacts={"paper_candidate_admission": record.reference().to_dict()},
    )


def get_paper_candidate_admission(
    admission_ref: str,
    *,
    artifact_store: ResearchArtifactStore | None,
) -> ApplicationResult:
    """Load and parse one canonical admission without granting runtime access."""
    command = PAPER_ADMISSION_GET
    if artifact_store is None:
        return _store_required(command)
    try:
        record = _load_record(artifact_store, admission_ref)
        admission = PaperCandidateAdmission.from_dict(record.payload)
    except (ValueError, ResearchArtifactStoreError) as exc:
        return error_result(command=command, code="paper_admission_resolution_failed", message=str(exc))
    return success_result(
        command=command,
        data={"paper_candidate_admission": admission.to_dict()},
        artifacts={"paper_candidate_admission": record.reference().to_dict()},
    )


def validate_paper_candidate_admission(
    admission_ref: str,
    *,
    artifact_store: ResearchArtifactStore | None,
    now: str | datetime | None = None,
) -> ApplicationResult:
    """Re-read evidence and report whether an admission may start paper mode.

    Validation is fail-closed: rejection, revocation, expiry, missing evidence,
    URI/owner mismatch, and changed evidence payloads all block startup.
    """
    command = PAPER_ADMISSION_VALIDATE
    if artifact_store is None:
        return _store_required(command)
    try:
        record = _load_record(artifact_store, admission_ref)
        admission = PaperCandidateAdmission.from_dict(record.payload)
        blockers = _validation_blockers(artifact_store, admission, now=now)
    except (ValueError, ResearchArtifactStoreError) as exc:
        return error_result(command=command, code="paper_admission_validation_failed", message=str(exc))
    report = {
        "artifact_type": "paper_candidate_admission_validation",
        "schema_version": "1",
        "admission_id": admission.admission_id,
        "status": "eligible" if not blockers else "blocked",
        "eligible": not blockers,
        "blockers": blockers,
        "validated_at": _timestamp(now),
    }
    return success_result(command=command, data={"paper_admission_validation": report}) if not blockers else error_result(
        command=command,
        code="paper_admission_not_eligible",
        message=blockers[0],
        data={"paper_admission_validation": report},
    )


def revoke_paper_candidate_admission(
    admission_ref: str,
    *,
    reason: str,
    approver: str,
    artifact_store: ResearchArtifactStore | None,
    now: str | datetime | None = None,
) -> ApplicationResult:
    """Create an immutable revoked successor for an existing admission."""
    command = PAPER_ADMISSION_REVOKE
    if artifact_store is None:
        return _store_required(command)
    try:
        _require_human_principal(approver, "approver")
        if not str(reason or "").strip():
            raise ValueError("revocation reason is required")
        current = PaperCandidateAdmission.from_dict(_load_record(artifact_store, admission_ref).payload)
        if current.decision is not PaperAdmissionDecision.APPROVED:
            raise ValueError("only an approved admission may be revoked")
        revoked_at = _timestamp(now)
        successor_id = stable_research_id(
            "paper_candidate_admission",
            {"supersedes_admission_id": current.admission_id, "decision": "revoked", "revoked_at": revoked_at, "reason": reason},
        )
        successor = PaperCandidateAdmission(
            admission_id=successor_id,
            candidate_ref=current.candidate_ref,
            evidence_refs=current.evidence_refs,
            strategy_version=current.strategy_version,
            risk_version=current.risk_version,
            data_version=current.data_version,
            risk_limits=current.risk_limits,
            broker_scope=current.broker_scope,
            monitoring_policy=current.monitoring_policy,
            decision=PaperAdmissionDecision.REVOKED,
            approver=approver,
            decided_at=revoked_at,
            revoked_at=revoked_at,
            revocation_reason=str(reason).strip(),
            supersedes_admission_id=current.admission_id,
            unresolved_limitations=current.unresolved_limitations,
            metadata={"revocation_of": current.admission_id},
        )
        record = _save_immutable(
            artifact_store,
            admission=successor,
            command=command,
            requested_by=approver,
            actor=approver,
        )
    except (ValueError, ResearchArtifactStoreError) as exc:
        return error_result(command=command, code="paper_admission_revocation_failed", message=str(exc))
    return success_result(
        command=command,
        data={"paper_candidate_admission": successor.to_dict()},
        artifacts={"paper_candidate_admission": record.reference().to_dict()},
    )


def _validation_blockers(
    store: ResearchArtifactStore,
    admission: PaperCandidateAdmission,
    *,
    now: str | datetime | None,
) -> list[str]:
    """Collect deterministic blockers for runtime admission eligibility."""
    blockers: list[str] = []
    if admission.decision is not PaperAdmissionDecision.APPROVED:
        blockers.append(f"admission decision is {admission.decision.value}")
    if admission.expires_at is not None and _parse_timestamp(admission.expires_at, "expires_at") <= _parse_timestamp(_timestamp(now), "now"):
        blockers.append("admission has expired")
    if admission.revoked_at is not None:
        blockers.append("admission has been revoked")
    elif _has_revocation_successor(store, admission.admission_id):
        blockers.append("admission has a revocation successor")
    try:
        _validate_evidence_refs(store, admission)
    except (ValueError, ResearchArtifactStoreError) as exc:
        blockers.append(str(exc))
    return blockers


def _validate_evidence_refs(store: ResearchArtifactStore, admission: PaperCandidateAdmission) -> None:
    """Resolve every evidence ref and reject stale or mismatched records."""
    for name, reference in admission.evidence_refs.items():
        record = _resolve_reference(store, reference)
        metadata = reference.get("metadata")
        expected_payload_hash = str(metadata.get("payload_sha256") or "") if isinstance(metadata, Mapping) else ""
        if expected_payload_hash and expected_payload_hash != json_payload_hash(record.payload):
            raise ValueError(f"evidence ref {name} payload has changed")
        expected_source_hash = metadata.get("source_hash") if isinstance(metadata, Mapping) else None
        if expected_source_hash is not None and expected_source_hash != record.source_hash:
            raise ValueError(f"evidence ref {name} source hash has changed")
        expected_version = str(metadata.get("version") or "") if isinstance(metadata, Mapping) else ""
        if expected_version and not _record_contains_version(record, expected_version):
            raise ValueError(f"evidence ref {name} version has changed")


def _record_contains_version(record: ResearchArtifactRecord, version: str) -> bool:
    """Return whether an evidence record still contains its pinned version."""
    if record.artifact_id == version:
        return True
    values = dict(record.payload)
    identity_keys = {"version", "version_id", "implementation_version_id", "strategy_specification_id", "risk_stack_specification_id", "dataset_id", "run_id"}
    return any(str(values.get(key) or "") == version for key in identity_keys)


def _resolve_reference(store: ResearchArtifactStore, reference: Mapping[str, Any]) -> ResearchArtifactRecord:
    """Resolve and verify one typed canonical artifact reference."""
    artifact_type = str(reference.get("artifact_type") or "")
    artifact_id = str(reference.get("artifact_id") or "")
    if not artifact_type or not artifact_id:
        raise ValueError("evidence references require artifact_type and artifact_id")
    if DOMAIN_OWNER_BY_ARTIFACT_TYPE.get(artifact_type) != reference.get("domain_owner"):
        raise ValueError("evidence ref domain owner does not match artifact authority")
    uri = str(reference.get("uri") or "")
    if uri:
        parsed_type, parsed_id = parse_research_artifact_uri(uri)
        if parsed_type != artifact_type or parsed_id != artifact_id:
            raise ValueError("evidence ref URI does not match canonical identity")
    record = store.load_artifact_record(artifact_type, artifact_id)
    if record.uri != uri:
        raise ValueError("evidence ref URI does not match canonical record")
    if record.domain_owner != reference.get("domain_owner"):
        raise ValueError("evidence ref domain owner does not match canonical record")
    return record


def _has_revocation_successor(store: ResearchArtifactStore, admission_id: str) -> bool:
    """Return whether an immutable revoked successor supersedes this admission."""
    records = store.list_artifacts(artifact_type=PAPER_CANDIDATE_ADMISSION)
    return any(
        record.payload.get("supersedes_admission_id") == admission_id
        and record.payload.get("decision") == PaperAdmissionDecision.REVOKED.value
        for record in records
    )


def _save_immutable(
    store: ResearchArtifactStore,
    *,
    admission: PaperCandidateAdmission,
    command: str,
    requested_by: str,
    actor: str,
) -> ResearchArtifactRecord:
    """Persist an admission without overwriting conflicting evidence."""
    payload = admission.to_dict()
    try:
        existing = store.load_artifact_record(PAPER_CANDIDATE_ADMISSION, admission.admission_id)
    except ResearchArtifactNotFound:
        _validate_successor_lineage(store, admission)
        return store.save_artifact(
            artifact_type=PAPER_CANDIDATE_ADMISSION,
            artifact_id=admission.admission_id,
            domain_owner=DOMAIN_OWNER_BY_ARTIFACT_TYPE[PAPER_CANDIDATE_ADMISSION],
            producer_tool=command,
            payload=payload,
            requested_by=requested_by,
            actor=actor,
            status=admission.decision.value,
            source_hash=admission.digest,
            metadata={"decision": admission.decision.value, "approver": admission.approver},
        )
    if dict(existing.payload) != payload:
        raise ResearchArtifactStoreError(f"conflicting immutable {PAPER_CANDIDATE_ADMISSION}: {admission.admission_id}")
    if existing.requested_by != requested_by or existing.actor != actor or existing.source_hash != admission.digest:
        raise ResearchArtifactStoreError(f"immutable {PAPER_CANDIDATE_ADMISSION} governance metadata drift: {admission.admission_id}")
    return existing


def _validate_successor_lineage(
    store: ResearchArtifactStore,
    admission: PaperCandidateAdmission,
) -> None:
    """Require an explicit predecessor when a candidate is admitted again.

    Admission identities are immutable, so a material change must be represented
    by a new record linked to the prior candidate record. This check prevents an
    unlinked second decision for the same candidate from looking like an update.
    """
    prior_records = [
        record
        for record in store.list_artifacts(artifact_type=PAPER_CANDIDATE_ADMISSION)
        if record.payload.get("candidate_ref") == admission.candidate_ref
        and record.payload.get("admission_id") != admission.admission_id
    ]
    predecessor_id = admission.supersedes_admission_id
    if prior_records and not predecessor_id:
        raise ValueError(
            "material changes to a paper candidate require supersedes_admission_id"
        )
    if not predecessor_id:
        return
    try:
        predecessor = store.load_artifact_record(PAPER_CANDIDATE_ADMISSION, predecessor_id)
    except ResearchArtifactNotFound as exc:
        raise ValueError(f"successor predecessor does not exist: {predecessor_id}") from exc
    if predecessor.payload.get("candidate_ref") != admission.candidate_ref:
        raise ValueError("successor predecessor must reference the same candidate_ref")


def _load_record(store: ResearchArtifactStore, ref: str) -> ResearchArtifactRecord:
    """Resolve an admission ID or canonical URI."""
    value = str(ref or "").strip()
    if not value:
        raise ValueError("admission reference is required")
    artifact_id = value
    if value.startswith("research://"):
        artifact_type, artifact_id = parse_research_artifact_uri(value)
        if artifact_type != PAPER_CANDIDATE_ADMISSION:
            raise ValueError("admission URI has the wrong artifact type")
    return store.load_artifact_record(PAPER_CANDIDATE_ADMISSION, artifact_id)


def _validate_reference_shape(reference: Mapping[str, Any], name: str) -> None:
    """Check bounded evidence-ref fields before storage lookup."""
    if not isinstance(reference, Mapping):
        raise ValueError(f"evidence ref {name} must be a mapping")
    for key in ("artifact_type", "artifact_id", "domain_owner", "uri"):
        if not str(reference.get(key) or "").strip():
            raise ValueError(f"evidence ref {name} requires {key}")
    metadata = reference.get("metadata")
    if not isinstance(metadata, Mapping):
        raise ValueError(f"evidence ref {name} metadata must be a mapping")
    if not str(metadata.get("payload_sha256") or "").strip():
        raise ValueError(f"evidence ref {name} requires metadata.payload_sha256")


def _require_human_principal(value: str, label: str) -> None:
    """Reject registered agents and transport identities at the human gate."""
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{label} is required")
    if not text.lower().startswith("human:"):
        raise ValueError(f"{label} must be a human principal")
    try:
        get_agent_definition(text)
    except KeyError:
        lowered = text.lower()
        if "agent" in lowered or lowered.startswith("mcp:"):
            raise ValueError(f"{label} must be a human principal")
        return
    raise ValueError(f"{label} must be a human principal")


def _parse_timestamp(value: str, label: str) -> datetime:
    """Parse an ISO-8601 timestamp and normalize it to UTC."""
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{label} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _timestamp(value: str | datetime | None) -> str:
    """Normalize a supplied clock value or use the current UTC instant."""
    if value is None:
        parsed = datetime.now(timezone.utc)
    elif isinstance(value, datetime):
        parsed = value
    else:
        parsed = _parse_timestamp(str(value), "timestamp")
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _mapping_of_mappings(value: object) -> Mapping[str, Mapping[str, Any]]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): _mapping(item) for key, item in value.items()}


def _text_sequence(value: object, label: str) -> tuple[str, ...]:
    """Normalize a sequence of non-empty text values at the artifact boundary."""
    if value is None:
        return ()
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple)):
        raise ValueError(f"{label} must be a sequence")
    normalized = tuple(str(item).strip() for item in value)
    if any(not item for item in normalized):
        raise ValueError(f"{label} must contain non-empty text")
    return normalized


def _optional_text(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _store_required(command: str) -> ApplicationResult:
    return error_result(
        command=command,
        code="research_artifact_store_required",
        message="A configured ResearchArtifactStore is required.",
    )
