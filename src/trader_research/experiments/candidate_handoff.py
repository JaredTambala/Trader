"""Build a deterministic, lineage-complete strategy candidate handoff.

The handoff is the research-owned boundary between a revisioned hypothesis and
an inspectable strategy/risk candidate. It never grants execution authority and
never substitutes for controlled model qualification or human admission.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from trader_research.foundation import (
    ApplicationResult,
    ResearchArtifactNotFound,
    ResearchArtifactStore,
    ResearchArtifactStoreError,
    error_result,
    json_payload_hash,
    load_artifact_ref,
    stable_research_id,
    success_result,
)
from trader_research.foundation.artifacts import SCHEMA_VERSION
from trader_research.governance import (
    DOMAIN_OWNER_BY_ARTIFACT_TYPE,
    HypothesisBriefHandoff,
    resolve_hypothesis_brief_handoff,
)
from trader_research.governance.artifacts import (
    RISK_STACK_SPECIFICATION,
    RISK_STACK_SPECIFICATION_VALIDATION_REPORT,
    STRATEGY_SPECIFICATION,
    STRATEGY_SPECIFICATION_VALIDATION_REPORT,
)


STRATEGY_CANDIDATE_HANDOFF = "strategy_candidate_handoff"
RESEARCH_CREATE_STRATEGY_CANDIDATE_HANDOFF = "research_create_strategy_candidate_handoff"
RESEARCH_RESOLVE_STRATEGY_CANDIDATE_HANDOFF = "research_resolve_strategy_candidate_handoff"


@dataclass(frozen=True)
class StrategyCandidateHandoff:
    """Immutable references and decisions for one admitted candidate."""

    candidate_id: str
    brief_ref: Mapping[str, Any]
    strategy_validation_ref: str
    risk_validation_ref: str
    catalogue_comparison: Mapping[str, Any]
    construction_decision: str
    next_decision: str
    status: str = "admitted"

    def __post_init__(self) -> None:
        """Validate the source-free handoff shape and explicit authority boundary."""
        if not self.candidate_id.strip():
            raise ValueError("candidate_id is required")
        if not self.strategy_validation_ref.strip() or not self.risk_validation_ref.strip():
            raise ValueError("strategy and risk validation references are required")
        if self.construction_decision not in {"exact_reuse", "bounded_adaptation", "new_authorship"}:
            raise ValueError("unsupported construction decision")
        if self.status != "admitted":
            raise ValueError("candidate handoff status must be admitted")
        if not self.next_decision.strip():
            raise ValueError("next decision is required")
        comparison = dict(self.catalogue_comparison)
        if not str(comparison.get("comparison_id") or "").strip():
            raise ValueError("catalogue comparison_id is required")
        if comparison.get("decision_authority") != "strategy_engineering_agent":
            raise ValueError("catalogue comparison authority is invalid")
        object.__setattr__(self, "brief_ref", dict(self.brief_ref))
        object.__setattr__(self, "catalogue_comparison", comparison)

    def to_dict(self) -> dict[str, Any]:
        """Return the source-free JSON representation."""
        return {
            "artifact_type": STRATEGY_CANDIDATE_HANDOFF,
            "schema_version": SCHEMA_VERSION,
            "candidate_id": self.candidate_id,
            "brief_ref": dict(self.brief_ref),
            "strategy_validation_ref": self.strategy_validation_ref,
            "risk_validation_ref": self.risk_validation_ref,
            "catalogue_comparison": dict(self.catalogue_comparison),
            "construction_decision": self.construction_decision,
            "next_decision": self.next_decision,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "StrategyCandidateHandoff":
        """Parse and validate one persisted handoff."""
        return cls(
            candidate_id=str(payload.get("candidate_id") or ""),
            brief_ref=_mapping(payload.get("brief_ref"), "brief_ref"),
            strategy_validation_ref=str(payload.get("strategy_validation_ref") or ""),
            risk_validation_ref=str(payload.get("risk_validation_ref") or ""),
            catalogue_comparison=_mapping(payload.get("catalogue_comparison"), "catalogue_comparison"),
            construction_decision=str(payload.get("construction_decision") or ""),
            next_decision=str(payload.get("next_decision") or ""),
            status=str(payload.get("status") or ""),
        )


def create_strategy_candidate_handoff(
    *,
    brief_handoff: HypothesisBriefHandoff | Mapping[str, Any],
    catalogue_comparison: Mapping[str, Any],
    construction_decision: str,
    strategy_validation_ref: str,
    risk_validation_ref: str,
    next_decision: str,
    artifact_store: ResearchArtifactStore | None,
) -> ApplicationResult:
    """Persist a candidate only when every upstream artifact is passed and exact."""
    command = RESEARCH_CREATE_STRATEGY_CANDIDATE_HANDOFF
    if artifact_store is None:
        return error_result(command=command, code="research_artifact_store_required", message="A ResearchArtifactStore is required.")
    try:
        parsed_handoff = brief_handoff if isinstance(brief_handoff, HypothesisBriefHandoff) else HypothesisBriefHandoff.from_dict(brief_handoff)
        brief_result = resolve_hypothesis_brief_handoff(
            handoff=parsed_handoff,
            recipient="Strategy Engineering Agent",
            artifact_store=artifact_store,
        )
        if not brief_result.ok:
            raise ValueError(str(brief_result.errors[0].get("message") or "hypothesis handoff is unavailable"))
        comparison = dict(catalogue_comparison)
        if construction_decision == "exact_reuse" and comparison.get("direct_reuse_eligible") is not True:
            raise ValueError("exact reuse requires a directly reusable catalogue comparison")
        strategy_report = _passed_validation(artifact_store, strategy_validation_ref, STRATEGY_SPECIFICATION_VALIDATION_REPORT, STRATEGY_SPECIFICATION)
        risk_report = _passed_validation(artifact_store, risk_validation_ref, RISK_STACK_SPECIFICATION_VALIDATION_REPORT, RISK_STACK_SPECIFICATION)
        candidate_id = stable_research_id("strategy_candidate_handoff", {
            "brief_ref": parsed_handoff.to_dict(),
            "catalogue_comparison": comparison,
            "construction_decision": construction_decision,
            "strategy_validation_ref": strategy_report["validation_id"],
            "risk_validation_ref": risk_report["validation_id"],
            "next_decision": next_decision,
        })
        candidate = StrategyCandidateHandoff(
            candidate_id=candidate_id,
            brief_ref=parsed_handoff.to_dict(),
            strategy_validation_ref=str(strategy_report["validation_id"]),
            risk_validation_ref=str(risk_report["validation_id"]),
            catalogue_comparison=comparison,
            construction_decision=construction_decision,
            next_decision=next_decision,
        )
        payload = candidate.to_dict()
        try:
            existing = artifact_store.load_artifact_record(STRATEGY_CANDIDATE_HANDOFF, candidate_id)
        except ResearchArtifactNotFound:
            existing = None
        if existing is not None and dict(existing.payload) != payload:
            raise ValueError("candidate handoff revision conflicts with existing identity")
        record = existing or artifact_store.save_artifact(
            artifact_type=STRATEGY_CANDIDATE_HANDOFF,
            artifact_id=candidate_id,
            domain_owner=DOMAIN_OWNER_BY_ARTIFACT_TYPE[STRATEGY_CANDIDATE_HANDOFF],
            producer_tool=command,
            payload=payload,
            status="admitted",
            source_hash=json_payload_hash(payload),
            metadata={"brief_id": parsed_handoff.brief_id, "brief_revision": parsed_handoff.revision},
        )
    except (ValueError, ResearchArtifactStoreError) as exc:
        return error_result(command=command, code="strategy_candidate_handoff_failed", message=str(exc))
    return success_result(
        command=command,
        data={"candidate": payload, "idempotent_replay": existing is not None},
        artifacts={"strategy_candidate_handoff": record.reference().to_dict()},
    )


def resolve_strategy_candidate_handoff(
    *, candidate_ref: str,
    artifact_store: ResearchArtifactStore | None,
) -> ApplicationResult:
    """Re-read and revalidate every lineage edge of one candidate handoff."""
    command = RESEARCH_RESOLVE_STRATEGY_CANDIDATE_HANDOFF
    if artifact_store is None:
        return error_result(command=command, code="research_artifact_store_required", message="A ResearchArtifactStore is required.")
    try:
        payload = load_artifact_ref(artifact_store, STRATEGY_CANDIDATE_HANDOFF, candidate_ref)
        candidate = StrategyCandidateHandoff.from_dict(payload)
        brief_result = resolve_hypothesis_brief_handoff(
            handoff=candidate.brief_ref,
            recipient="Strategy Engineering Agent",
            artifact_store=artifact_store,
        )
        if not brief_result.ok:
            raise ValueError("candidate hypothesis lineage is no longer resolvable")
        _passed_validation(artifact_store, candidate.strategy_validation_ref, STRATEGY_SPECIFICATION_VALIDATION_REPORT, STRATEGY_SPECIFICATION)
        _passed_validation(artifact_store, candidate.risk_validation_ref, RISK_STACK_SPECIFICATION_VALIDATION_REPORT, RISK_STACK_SPECIFICATION)
        record = artifact_store.load_artifact_record(STRATEGY_CANDIDATE_HANDOFF, candidate.candidate_id)
    except (ValueError, ResearchArtifactStoreError) as exc:
        return error_result(command=command, code="strategy_candidate_handoff_resolution_failed", message=str(exc))
    return success_result(command=command, data={"candidate": candidate.to_dict()}, artifacts={"strategy_candidate_handoff": record.reference().to_dict()})


def _passed_validation(
    store: ResearchArtifactStore,
    ref: str,
    report_type: str,
    specification_type: str,
) -> Mapping[str, Any]:
    report = load_artifact_ref(store, report_type, ref)
    if report.get("status") != "passed" or report.get("valid") is not True or report.get("blockers"):
        raise ValueError(f"{report_type} must be passed and blocker-free")
    specification_id = str(report.get("strategy_specification_id") or report.get("risk_stack_specification_id") or "")
    if not specification_id:
        raise ValueError(f"{report_type} has no specification lineage")
    specification = store.load_artifact(specification_type, specification_id)
    if specification.get("artifact_type") != specification_type:
        raise ValueError(f"{report_type} points to an incompatible specification")
    return report


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return dict(value)
