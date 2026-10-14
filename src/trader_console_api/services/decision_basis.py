"""Resolve persisted evidence into an authorized human decision basis."""

from typing import Any

from trader_research.governance import build_next_research_decision, NextDecisionOutcome, SessionReviewLink
from trader_research.governance.next_decisions import BlockedEvidenceBasis
from trader_research.governance.handoffs import ArtifactReportRef

from ..contracts import TraderPrincipal
from ..decision_basis_contracts import DecisionBasisResponse, DecisionEvidenceBasis
from ..repositories.decision_basis import DecisionBasisRepository, DecisionBasisSession, pinned_reference
from ..repositories.next_research_decisions import NextResearchDecisionEvidenceUnavailable
from .next_research_decisions import NextResearchDecisionService

_REVIEW_TYPES = (
    "evaluation_report", "multiple_testing_report", "robustness_report",
    "parameter_optimization_evaluation_report", "parameter_optimization_robustness_report",
)


def _session_review(reviews: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Retain a graph link only when every cited review names the same graph."""
    metadata = [dict(row.get("metadata") or {}) for row in reviews]
    if not any(item.get("session_id") for item in metadata):
        return None
    identities = {(item.get("session_id"), item.get("session_digest"), item.get("graph_digest")) for item in metadata}
    if len(identities) != 1 or not all(next(iter(identities))):
        raise ValueError("Review session identities are incomplete or incompatible")
    session_id, session_digest, graph_digest = next(iter(identities))
    return {
        "session_id": session_id, "session_digest": session_digest, "graph_digest": graph_digest,
        "review_node_keys": [f"{row['artifact_type']}:{row['artifact_id']}:r{meta.get('revision')}" for row, meta in zip(reviews, metadata, strict=True)],
    }


async def _workflow_inputs(session: DecisionBasisSession, outcome: dict[str, Any]) -> dict[str, Any]:
    """Follow the outcome's exact protocol and its producer-owned input refs."""
    payload = outcome["payload"]
    protocol = (await session.resolve(payload["protocol_ref"]))["payload"]
    datasets = protocol["datasets"]
    if len(datasets) != 1:
        raise ValueError("Decision basis requires one unambiguous protocol dataset")
    data = await session.resolve(datasets[0]["dataset_manifest_ref"])
    implementations = [await session.resolve(protocol["strategy"]["implementation_ref"])]
    for manager in protocol["risk_managers"]:
        record = await session.resolve(manager["implementation_ref"])
        if (record["artifact_type"], record["artifact_id"]) not in {(item["artifact_type"], item["artifact_id"]) for item in implementations}:
            implementations.append(record)
    reviews = [await session.resolve(reference) for reference in payload["review_verdict_refs"]]
    blocked = None
    if payload["status"] == "blocked" and not reviews:
        session_id = dict(outcome.get("metadata") or {}).get("session_id")
        session_record = await session.artifact("research_session", str(session_id)) if session_id else None
        blocked = {
            "outcome_ref": pinned_reference(outcome), "blockers": payload["blockers"],
            "session_ref": pinned_reference(session_record) if session_record else None,
            "scientific_review_status": "not_assessed",
        }
    return {
        "data_ref": pinned_reference(data),
        "implementation_refs": [pinned_reference(record) for record in implementations],
        "review_refs": [pinned_reference(record) for record in reviews],
        "session_review": _session_review(reviews), "blocked_evidence": blocked,
        "assumptions": {"material_assumptions": protocol["material_assumptions"], "costs": protocol["costs"]},
    }


async def _review_inputs(session: DecisionBasisSession, run_id: str) -> dict[str, Any]:
    """Resolve a genuine review chain through explicit published run identities."""
    data = await session.linked(run_id, ("dataset_manifest", "data_load_evidence"))
    implementations = await session.linked(run_id, ("implementation_version",))
    reviews = await session.linked(run_id, _REVIEW_TYPES)
    if len(data) != 1 or not implementations or not reviews:
        raise NextResearchDecisionEvidenceUnavailable("No unambiguous canonical run, Data, implementation and review chain is published")
    return {
        "data_ref": pinned_reference(data[0]),
        "implementation_refs": [pinned_reference(record) for record in implementations],
        "review_refs": [pinned_reference(record) for record in reviews],
        "session_review": _session_review(reviews), "blocked_evidence": None,
        "assumptions": {},
    }


def _candidate(basis: DecisionEvidenceBasis, principal: TraderPrincipal):
    """Build a transient reject candidate solely for canonical evidence validation."""
    return build_next_research_decision(
        decision_id="decision-basis-inspection", revision=1, outcome=NextDecisionOutcome.REJECT,
        rationale="Inspect persisted evidence", operator=principal.principal_id,
        decided_at="2000-01-01T00:00:00+00:00",
        source_run_ref=ArtifactReportRef.from_dict(basis.source_run_ref.model_dump()),
        data_ref=ArtifactReportRef.from_dict(basis.data_ref.model_dump()),
        implementation_refs=tuple(ArtifactReportRef.from_dict(item.model_dump()) for item in basis.implementation_refs),
        assumptions=basis.assumptions,
        review_refs=tuple(ArtifactReportRef.from_dict(item.model_dump()) for item in basis.review_refs),
        session_review=SessionReviewLink(**basis.session_review.model_dump()) if basis.session_review else None,
        blocked_evidence=BlockedEvidenceBasis.from_dict(basis.blocked_evidence.model_dump()) if basis.blocked_evidence else None,
        limitations=("Evidence inspection does not establish scientific acceptance or deployment approval",),
    )


class DecisionBasisService:
    """Expose verified evidence and fail closed without fabricating absent inputs."""

    def __init__(self, repository: DecisionBasisRepository) -> None:
        """Bind the read-only persistence boundary."""
        self._repository = repository

    async def get(self, run_id: str, principal: TraderPrincipal) -> DecisionBasisResponse:
        """Resolve and validate the displayed evidence through the read-only canonical validator."""
        NextResearchDecisionService._require_human(principal)
        async with self._repository.session() as session:
            await session.require_storage()
            run = await session.artifact("backtest_run", run_id)
            if run is None:
                return DecisionBasisResponse(run_id=run_id, status="unavailable", reason="Canonical run artifact is unavailable")
            try:
                outcomes = await session.outcomes(run_id)
                if len(outcomes) > 1:
                    raise ValueError("Multiple workflow outcomes cite this run; select an exact canonical outcome before recording a decision")
                if outcomes:
                    run_refs = [reference for reference in outcomes[0]["payload"]["produced_artifact_refs"]
                                if reference["artifact_type"] == "backtest_run" and reference["artifact_id"] == run_id]
                    if len(run_refs) != 1:
                        raise ValueError("Workflow outcome must identify exactly one source run reference")
                    await session.resolve(run_refs[0])
                    inputs = await _workflow_inputs(session, outcomes[0])
                else:
                    inputs = await _review_inputs(session, run_id)
                basis = DecisionEvidenceBasis.model_validate({"source_run_ref": pinned_reference(run), **inputs})
                await session.validate_evidence(_candidate(basis, principal), run_id=run_id)
            except NextResearchDecisionEvidenceUnavailable as exc:
                return DecisionBasisResponse(
                    run_id=run_id,
                    status="unavailable" if str(exc).startswith(("missing evidence artifact:", "No unambiguous", "reviewed run is not published")) else "incompatible",
                    reason=str(exc),
                )
            except (ValueError, KeyError, TypeError) as exc:
                return DecisionBasisResponse(run_id=run_id, status="incompatible", reason=f"Canonical evidence cannot be verified: {exc}")
        blocked = basis.blocked_evidence is not None
        return DecisionBasisResponse(
            run_id=run_id, status="available", reason="Verified persisted evidence",
            evidence=basis,
            permitted_outcomes=("reject", "refine") if blocked else ("reject", "refine", "continue"),
            limitations=("Independent scientific review is not assessed; unresolved blockers remain",) if blocked else ("Review evidence supports only its declared claim scope",),
        )
