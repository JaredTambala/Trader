"""Transport contracts for human next-decision recording and review.

Subject: Strict request/response shapes for immutable decision revisions.
Level: Pydantic contract unit tests.
Collaborators: Real Console contracts only; no database, service, or HTTP server.
Guarantees: reject/refine/continue and bounded successor requirements are explicit.
Non-goals: Evidence resolution, authorization, persistence, and browser rendering.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from trader_console_api.contracts import (
    BoundedNextExperimentContract,
    NextDecisionArtifactReference,
    NextResearchDecisionRequest,
)


def _ref(artifact_id: str, artifact_type: str) -> NextDecisionArtifactReference:
    """Build a canonical transport reference fixture."""
    return NextDecisionArtifactReference(
        artifact_id=artifact_id,
        artifact_type=artifact_type,
        domain_owner="Experiments" if artifact_type in {"backtest_run", "implementation_version"} else "Review",
        uri=f"research://postgres/{artifact_type}/{artifact_id}",
    )


def _request(**overrides: object) -> NextResearchDecisionRequest:
    """Build one minimally complete request."""
    values: dict[str, object] = {
        "decision_id": "decision-1",
        "outcome": "reject",
        "rationale": "No robust edge.",
        "source_run_ref": _ref("run-1", "backtest_run"),
        "data_ref": _ref("data-1", "dataset_manifest"),
        "implementation_refs": (_ref("impl-1", "implementation_version"),),
        "review_refs": (_ref("review-1", "evaluation_report"),),
        "limitations": ("Single holdout",),
    }
    values.update(overrides)
    return NextResearchDecisionRequest.model_validate(values)


def _experiment() -> BoundedNextExperimentContract:
    """Build one bounded successor experiment."""
    return BoundedNextExperimentContract(
        question="Does it persist?",
        data_ref=_ref("data-1", "dataset_manifest"),
        implementation_refs=(_ref("impl-1", "implementation_version"),),
        evaluation_start=datetime(2026, 11, 1, tzinfo=timezone.utc),
        evaluation_end=datetime(2026, 12, 1, tzinfo=timezone.utc),
        max_runs=3,
        success_criteria=("No material degradation",),
    )


def test_reject_has_no_successor_and_refine_requires_one() -> None:
    """Keep decision outcome and bounded successor semantics in the API schema."""
    assert _request().next_experiment is None
    with pytest.raises(ValidationError, match="require next_experiment"):
        _request(outcome="refine")
    assert _request(outcome="continue", next_experiment=_experiment()).outcome == "continue"
    with pytest.raises(ValidationError, match="cannot include next_experiment"):
        _request(next_experiment=_experiment())


def test_revision_requires_explicit_predecessor() -> None:
    """A later revision cannot silently fork the immutable decision stream."""
    with pytest.raises(ValidationError, match="must supersede"):
        _request(revision=2)
    assert _request(revision=2, supersedes_artifact_id="research_next_decision_old").revision == 2

