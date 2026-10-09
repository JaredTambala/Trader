"""Contracts for Console resource service normalization.

Subject: Mapping producer run projections into public summary contracts.
Level: In-process service boundary.
Collaborators: Pydantic response model; no database or HTTP transport.
Guarantees: Producer-only columns do not break the closed summary contract.
Non-goals: SQL selection, persistence, or frontend rendering.
"""

from datetime import datetime, timezone

import pytest

from trader_console_api.services.resources import _review_evidence, _run_summary


def test_run_summary_discards_producer_only_run_columns() -> None:
    """Allow ``runs.*`` repository rows to reach the typed summary safely."""
    summary = _run_summary(
        {
            "experiment_run_id": "er-1",
            "experiment_id": "exp-1",
            "run_id": "run-1",
            "status": "completed",
            "created_at": datetime(2026, 9, 28, tzinfo=timezone.utc),
            "symbols": ["BTC/USD"],
            "error_message": None,
            "artifact_dir": "/tmp/backtest",
        }
    )

    assert summary.run_id == "run-1"
    assert summary.symbols == ("BTC/USD",)


def test_review_evidence_preserves_claim_scope_and_blocks_optimization_promotion() -> None:
    """Expose producer status and limitations without upgrading optimisation output."""
    evidence = _review_evidence(
        [
            {
                "artifact_type": "parameter_optimization_evaluation_report",
                "artifact_id": "eval-1",
                "artifact_status": "passed",
                "domain_owner": "Evaluation Agent",
                "producer_tool": "evaluation_generate_parameter_optimization_report",
                "claim_scope": {"holdout_run_id": "run-1"},
                "data_roles": ["sealed_holdout"],
                "limitations": ["selection remains exploratory"],
                "blockers": [],
                "independent_confirmation": True,
                "origin_kind": "optimization",
            },
            {
                "artifact_type": "robustness_report",
                "artifact_id": "robust-1",
                "artifact_status": "blocked",
                "claim_scope": {"run_id": "run-1"},
                "data_roles": [],
                "limitations": [],
                "blockers": ["stress variants are missing"],
                "independent_confirmation": True,
                "origin_kind": "independent_review",
            },
        ]
    )

    assert evidence[0].status == "complete"
    assert evidence[0].independent_confirmation is False
    assert "not independent confirmation" in evidence[0].limitations[-1]
    adversarial = next(item for item in evidence if item.evidence_kind == "adversarial")
    assert adversarial.status == "blocked"
    assert adversarial.reason == "stress variants are missing"
    assert next(item for item in evidence if item.evidence_kind == "multiple_testing").status == "missing"


@pytest.mark.parametrize("state", ("partial", "negative", "missing", "incompatible", "stale"))
def test_review_evidence_preserves_fail_closed_qualification_states_and_graph_identity(state: str) -> None:
    """Expose every producer qualification state with exact retained identity."""
    row = {
        "artifact_type": "evaluation_report",
        "artifact_id": "eval-1",
        "artifact_status": state,
        "session_id": "session-1",
        "session_digest": "a" * 64,
        "graph_digest": "b" * 64,
        "branch_id": "branch-review",
        "revision": 2,
        "node_key": "evaluation_report:eval-1:r2",
    }
    evidence = _review_evidence([row])
    assert evidence[0].status == state
    assert evidence[0].node_key == "evaluation_report:eval-1:r2"
    assert evidence[0].session_id == "session-1"


def test_review_evidence_drops_partial_graph_identity_without_breaking_projection() -> None:
    """An incomplete producer graph receipt remains visible but cannot be cited."""
    evidence = _review_evidence([{
        "artifact_type": "evaluation_report", "artifact_id": "eval-1", "artifact_status": "complete",
        "revision": 2, "node_key": "evaluation_report:eval-1:r2",
    }])
    assert evidence[0].status == "complete"
    assert evidence[0].revision is None
    assert any("graph identity is incomplete" in item for item in evidence[0].limitations)
