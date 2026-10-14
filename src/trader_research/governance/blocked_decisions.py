"""Canonical blocked evidence for human decisions without scientific reviews.

The basis records a terminal outcome and its unresolved issues. It grants no
scientific or execution authority; validation resolves the exact protocol chain.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Mapping

from trader_research.foundation import ResearchArtifactRecord, json_payload_hash

from .handoffs import ArtifactReportRef, ResearchIssue
from .orchestration.workflows import WorkflowOutcome

if TYPE_CHECKING:
    from .next_decisions import NextResearchDecision


@dataclass(frozen=True)
class BlockedEvidenceBasis:
    """Unassessed scientific evidence pinned to a canonical blocked outcome.

    Attributes:
        outcome_ref: Exact workflow outcome with its canonical payload hash.
        blockers: Complete unresolved blocker list, including structured details.
        session_ref: Exact canonical session when the outcome explicitly links it.
        scientific_review_status: Always unassessed; this is not a review report.
    """

    outcome_ref: ArtifactReportRef
    blockers: tuple[ResearchIssue, ...]
    session_ref: ArtifactReportRef | None = None
    scientific_review_status: str = "not_assessed"

    def __post_init__(self) -> None:
        """Reject ambiguous outcome identity or promoted scientific authority."""
        if self.outcome_ref.artifact_type != "workflow_outcome":
            raise ValueError("blocked_evidence.outcome_ref must be a workflow_outcome")
        self.require_pinned(self.outcome_ref)
        if not self.blockers or len(self.blockers) > 32:
            raise ValueError("blocked_evidence requires 1 to 32 canonical blockers")
        if self.scientific_review_status != "not_assessed":
            raise ValueError("blocked evidence scientific reviews must remain not_assessed")
        if self.session_ref is not None:
            if self.session_ref.artifact_type != "research_session":
                raise ValueError("blocked_evidence.session_ref must be a research_session")
            self.require_pinned(self.session_ref)

    @staticmethod
    def require_pinned(reference: ArtifactReportRef) -> None:
        """Require a full payload digest rather than a caller's partial identity."""
        digest = reference.metadata.get("payload_sha256")
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError(f"blocked evidence requires payload_sha256: {reference.artifact_id}")

    def to_dict(self) -> dict[str, Any]:
        """Serialize the complete basis inside the immutable decision digest."""
        return {
            "outcome_ref": self.outcome_ref.to_dict(),
            "blockers": [item.to_dict() for item in self.blockers],
            "session_ref": self.session_ref.to_dict() if self.session_ref is not None else None,
            "scientific_review_status": self.scientific_review_status,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> BlockedEvidenceBasis:
        """Parse only the declared basis shape; never invent review evidence."""
        if set(payload) != {"outcome_ref", "blockers", "session_ref", "scientific_review_status"}:
            raise ValueError("blocked_evidence has an incompatible shape")
        if not isinstance(payload["blockers"], (list, tuple)):
            raise ValueError("blocked_evidence.blockers must be a list")
        return cls(
            outcome_ref=ArtifactReportRef.from_dict(payload["outcome_ref"]),
            blockers=tuple(ResearchIssue.from_dict(item) for item in payload["blockers"]),
            session_ref=ArtifactReportRef.from_dict(payload["session_ref"]) if payload["session_ref"] is not None else None,
            scientific_review_status=str(payload["scientific_review_status"]),
        )


def blocked_protocol_references(protocol: Mapping[str, Any]) -> tuple[ArtifactReportRef, ...]:
    """Return exact data, quality, strategy and risk refs from the protocol.

    Adapters may preload these references before invoking the pure validator.
    Missing structure fails closed rather than substituting latest evidence.
    """
    try:
        raw_refs = [protocol["strategy"]["implementation_ref"]]
        raw_refs.extend(item["implementation_ref"] for item in protocol["risk_managers"])
        for dataset in protocol["datasets"]:
            raw_refs.extend((dataset["dataset_manifest_ref"], dataset["data_quality_report_ref"]))
        return tuple(ArtifactReportRef.from_dict(item) for item in raw_refs)
    except (KeyError, TypeError) as exc:
        raise ValueError("blocked outcome protocol evidence is incomplete") from exc


def validate_blocked_evidence(
    decision: NextResearchDecision,
    load: Callable[[str, str], ResearchArtifactRecord],
) -> None:
    """Validate an exact blocked basis against canonical records without writes.

    Args:
        decision: Human decision with a typed blocked basis.
        load: Canonical record resolver; adapters can supply a preloaded mapping.

    Raises:
        ValueError: Evidence drift, unrelated lineage, or changed blocker claims.
    """
    basis = decision.blocked_evidence
    if basis is None:
        raise ValueError("blocked_evidence is required")

    def resolve(reference: ArtifactReportRef) -> ResearchArtifactRecord:
        BlockedEvidenceBasis.require_pinned(reference)
        record = load(reference.artifact_type, reference.artifact_id)
        if record.uri != reference.uri or record.domain_owner != reference.domain_owner:
            raise ValueError(f"blocked evidence identity changed: {reference.artifact_id}")
        if json_payload_hash(record.payload) != reference.metadata["payload_sha256"]:
            raise ValueError(f"blocked evidence payload has changed: {reference.artifact_id}")
        if "source_hash" in reference.metadata and record.source_hash != reference.metadata["source_hash"]:
            raise ValueError(f"blocked evidence source hash has changed: {reference.artifact_id}")
        return record

    terminal = resolve(basis.outcome_ref)
    outcome = WorkflowOutcome.from_dict(terminal.payload)
    if outcome.outcome_id != terminal.artifact_id or outcome.status.value != "blocked" or terminal.status != "blocked":
        raise ValueError("blocked evidence requires a canonical blocked terminal outcome")
    if outcome.review_verdict_refs:
        raise ValueError("blocked evidence cannot replace existing scientific reviews")
    if [item.to_dict() for item in outcome.blockers] != [item.to_dict() for item in basis.blockers]:
        raise ValueError("blocked evidence blockers differ from the canonical outcome")
    run = resolve(decision.source_run_ref)
    matching_runs = [ref for ref in outcome.produced_artifact_refs if ref.artifact_type == "backtest_run" and ref.artifact_id == run.artifact_id]
    if len(matching_runs) != 1:
        raise ValueError("blocked outcome does not identify the cited source run")
    resolve(matching_runs[0])
    protocol = resolve(outcome.protocol_ref)
    if protocol.status != "approved":
        raise ValueError("blocked outcome protocol is not approved")
    resolve(outcome.objective_ref)
    if protocol.payload.get("protocol_id") != protocol.artifact_id or protocol.payload.get("objective_id") != outcome.objective_ref.artifact_id:
        raise ValueError("blocked outcome protocol/objective identity does not match")
    for reference in blocked_protocol_references(protocol.payload):
        input_record = resolve(reference)
        if (input_record.status or "").lower() in {"stale", "missing", "incompatible", "failed", "blocked", "error", "rejected"}:
            raise ValueError(f"blocked outcome input is not actionable: {reference.artifact_id}")
    data = resolve(decision.data_ref)
    datasets = protocol.payload["datasets"]
    data_identity = (data.artifact_type, data.artifact_id)
    if not any(
        (item["dataset_manifest_ref"]["artifact_type"], item["dataset_manifest_ref"]["artifact_id"]) == data_identity
        for item in datasets
    ):
        raise ValueError("data evidence is not part of the blocked outcome protocol")
    if run.payload.get("dataset_id") != data.payload.get("dataset_id") or not data.payload.get("dataset_id"):
        raise ValueError("data evidence does not match the canonical source run")
    strategy_id = protocol.payload["strategy"]["implementation_ref"]["artifact_id"]
    if run.payload.get("strategy_implementation_version_id") != strategy_id:
        raise ValueError("implementation evidence does not match the canonical source run")
    risk_ids = [item["implementation_ref"]["artifact_id"] for item in protocol.payload["risk_managers"]]
    if [item.get("implementation_version_id") for item in run.payload.get("risk_lineage", [])] != risk_ids:
        raise ValueError("risk implementation evidence does not match the canonical source run")
    expected = {("implementation_version", strategy_id)} | {
        (item["implementation_ref"]["artifact_type"], item["implementation_ref"]["artifact_id"])
        for item in protocol.payload["risk_managers"]
    }
    actual = {(ref.artifact_type, ref.artifact_id) for ref in decision.implementation_refs}
    if actual != expected or len(actual) != len(decision.implementation_refs):
        raise ValueError("implementation evidence must match every admitted protocol implementation")
    for reference in decision.implementation_refs:
        resolve(reference)
    linked_session = terminal.metadata.get("session_id")
    if linked_session is not None and basis.session_ref is None:
        raise ValueError("blocked outcome requires its canonical session reference")
    if basis.session_ref is not None:
        session = resolve(basis.session_ref)
        if session.artifact_id != linked_session or session.payload.get("session_id") != linked_session:
            raise ValueError("blocked outcome session identity does not match")
        from .agentic.domain import ResearchSession
        ResearchSession.from_dict(session.payload)
    if decision.next_experiment is not None:
        for reference in (decision.next_experiment.data_ref, *decision.next_experiment.implementation_refs):
            successor = resolve(reference)
            if (successor.status or "").lower() in {"stale", "missing", "incompatible", "failed", "blocked", "error", "rejected"}:
                raise ValueError(f"successor evidence is not actionable: {reference.artifact_id}")
