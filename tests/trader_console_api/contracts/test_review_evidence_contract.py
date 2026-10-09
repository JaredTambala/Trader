"""Transport contract tests for fail-closed Console review evidence.

Subject: Exact status and retained graph identity in ``ReviewEvidence``.
Level: Pydantic contract unit test.
Collaborators: Real Console response model only; no database or browser.
Guarantees: Every qualification state is representable and graph references are exact.
Non-goals: Producer scoring, persistence, and visual styling.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from trader_console_api.contracts import ReviewEvidence


@pytest.mark.parametrize("status", ("complete", "partial", "negative", "missing", "incompatible", "stale", "blocked"))
def test_review_evidence_preserves_explicit_qualification_states(status: str) -> None:
    """Keep negative and unavailable evidence visible instead of collapsing it."""
    evidence = ReviewEvidence(evidence_kind="evaluation", status=status, reason="fixture")
    assert evidence.status == status


def test_review_evidence_requires_exact_graph_identity_as_one_unit() -> None:
    """A revision cannot be cited without its session, graph, and node identity."""
    with pytest.raises(ValidationError, match="graph identity"):
        ReviewEvidence(
            evidence_kind="evaluation", artifact_type="evaluation_report", artifact_id="eval-1",
            status="complete", reason="fixture", revision=2,
        )

    evidence = ReviewEvidence(
        evidence_kind="evaluation", artifact_type="evaluation_report", artifact_id="eval-1",
        status="complete", reason="fixture", session_id="session-1", session_digest="a" * 64,
        graph_digest="b" * 64, branch_id="branch-review", revision=2,
        node_key="evaluation_report:eval-1:r2",
    )
    assert evidence.node_key == "evaluation_report:eval-1:r2"
