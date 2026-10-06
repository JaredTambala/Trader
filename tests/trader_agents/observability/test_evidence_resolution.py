"""Qualification tests for exact UJ-09 evidence resolution.

Subject: Independent read of named review artifact revisions and context.
Level: Deterministic contract qualification.
Collaborators: Typed public graph and injected canonical reader facts; no
database, browser, model, or broker.
Guarantees: Exact identity, distinct degraded states, and bounded review facts.
Non-goals: Statistical validity or deployment approval.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from trader_agents import (
    EvidenceNode,
    EvidenceStatus,
    ResolvedReviewArtifact,
    ReviewAssessmentStatus,
    SessionEvidenceGraph,
    resolve_session_review_evidence,
)


def _graph(status: EvidenceStatus = EvidenceStatus.AVAILABLE) -> SessionEvidenceGraph:
    """Build one explicitly revisioned review graph."""
    node = EvidenceNode(
        artifact_type="evaluation_report",
        artifact_id="evaluation-1",
        revision=2,
        status=status,
        uri="research://postgres/evaluation_report/evaluation-1",
        domain_owner="Review",
        branch_id="branch-review",
        source_hash="a" * 64,
        claim_scope={"run_id": "run-1", "scope_id": "scope-1"},
        limitations=("One market regime only",),
    )
    return SessionEvidenceGraph(
        session_id="session-1",
        session_digest="b" * 64,
        branch_ids=("branch-review",),
        run_id="run-1",
        nodes=(node,),
    )


def _artifact(status: EvidenceStatus = EvidenceStatus.AVAILABLE) -> ResolvedReviewArtifact:
    """Build the independently read public facts for the same artifact."""
    return ResolvedReviewArtifact(
        artifact_type="evaluation_report",
        artifact_id="evaluation-1",
        revision=2,
        uri="research://postgres/evaluation_report/evaluation-1",
        domain_owner="Review",
        session_id="session-1",
        branch_id="branch-review",
        run_id="run-1",
        scope_id="scope-1",
        strategy_version_id="strategy-v1",
        status=status,
        source_hash="a" * 64,
        uncertainty=("Confidence interval is wide",),
        comparison_exclusions=("Different fee assumptions",),
        statistical_status=ReviewAssessmentStatus.INCONCLUSIVE,
        robustness_status=ReviewAssessmentStatus.NOT_ASSESSED,
        blockers=("Independent robustness report pending",),
    )


def _resolve(
    artifact: ResolvedReviewArtifact | None,
    *,
    graph: SessionEvidenceGraph | None = None,
    key: str = "evaluation_report:evaluation-1:r2",
) -> dict[str, object]:
    """Resolve one named revision using an injected exact type/ID reader."""
    result = resolve_session_review_evidence(
        graph or _graph(),
        scope_id="scope-1",
        strategy_version_id="strategy-v1",
        required_node_keys=(key,),
        lookup=lambda artifact_type, artifact_id: artifact,
    )
    return result.to_dict()


def test_exact_artifact_keeps_review_limitations_and_assessment_states() -> None:
    """Successful lookup retains uncertainty, exclusions, tests, and blockers."""
    result = _resolve(_artifact())
    assert result["verdict"] == "partial"
    assert result["artifacts"] == [{
        "key": "evaluation_report:evaluation-1:r2",
        "status": "available",
        "blockers": ["Independent robustness report pending"],
        "limitations": ["One market regime only"],
        "uncertainty": ["Confidence interval is wide"],
        "comparison_exclusions": ["Different fee assumptions"],
        "statistical_status": "inconclusive",
        "robustness_status": "not_assessed",
    }]


@pytest.mark.parametrize(
    ("changed", "expected"),
    [
        ({"revision": 3}, "stale"),
        ({"session_id": "session-other"}, "incompatible"),
        ({"branch_id": "branch-other"}, "incompatible"),
        ({"run_id": "run-other"}, "incompatible"),
        ({"scope_id": "scope-other"}, "incompatible"),
        ({"strategy_version_id": "strategy-v2"}, "incompatible"),
        ({"source_hash": "c" * 64}, "incompatible"),
        ({"uri": "research://postgres/evaluation_report/other"}, "incompatible"),
    ],
)
def test_named_revision_and_context_cannot_drift(
    changed: dict[str, object], expected: str,
) -> None:
    """A newer revision or changed session, branch, run, scope, or strategy fails closed."""
    result = _resolve(replace(_artifact(), **changed))
    assert result["verdict"] == "blocked"
    assert result["artifacts"][0]["status"] == expected


@pytest.mark.parametrize(
    ("artifact", "node_status", "expected"),
    [
        (None, EvidenceStatus.AVAILABLE, "missing"),
        (_artifact(EvidenceStatus.REDACTED), EvidenceStatus.AVAILABLE, "redacted"),
        (_artifact(EvidenceStatus.NEGATIVE), EvidenceStatus.AVAILABLE, "negative"),
        (_artifact(), EvidenceStatus.NEGATIVE, "negative"),
    ],
)
def test_missing_redacted_and_negative_remain_distinct(
    artifact: ResolvedReviewArtifact | None,
    node_status: EvidenceStatus,
    expected: str,
) -> None:
    """Redaction and negative findings are never converted to available evidence."""
    result = _resolve(artifact, graph=_graph(node_status))
    assert result["artifacts"][0]["status"] == expected
    assert result["verdict"] == ("partial" if expected == "negative" else "blocked")


def test_absent_named_revision_is_missing_even_if_latest_artifact_exists() -> None:
    """The reader cannot replace a missing graph revision with another node."""
    result = _resolve(_artifact(), key="evaluation_report:evaluation-1:r1")
    assert result["artifacts"][0]["status"] == "missing"


def test_reader_failure_is_not_misreported_as_missing() -> None:
    """A storage outage propagates instead of becoming a false absence."""
    def unavailable(artifact_type: str, artifact_id: str) -> ResolvedReviewArtifact | None:
        raise RuntimeError("canonical store unavailable")

    with pytest.raises(RuntimeError, match="canonical store unavailable"):
        resolve_session_review_evidence(
            _graph(), scope_id="scope-1", strategy_version_id="strategy-v1",
            required_node_keys=("evaluation_report:evaluation-1:r2",),
            lookup=unavailable,
        )


def test_resolution_requires_explicit_scope_and_named_revision() -> None:
    """An incomplete review request cannot accidentally resolve latest evidence."""
    with pytest.raises(ValueError, match="run, scope, and strategy"):
        resolve_session_review_evidence(
            _graph(), scope_id="", strategy_version_id="strategy-v1",
            required_node_keys=("evaluation_report:evaluation-1:r2",),
            lookup=lambda kind, identity: _artifact(),
        )
    with pytest.raises(ValueError, match="unique named artifact revisions"):
        resolve_session_review_evidence(
            _graph(), scope_id="scope-1", strategy_version_id="strategy-v1",
            required_node_keys=(), lookup=lambda kind, identity: _artifact(),
        )
