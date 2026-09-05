"""Contracts for bounded multiple-testing correction reports.

Subject: Benjamini-Hochberg correction over one explicitly declared candidate family.
Level: In-process computational contract.
Collaborators: Candidate-family manifests, metric rows, method contracts, and approved-card evidence.
Guarantees: Adjusted values are deterministic and malformed families or observations fail closed.
Non-goals: Generating candidates, selecting experiment scope, backtesting, or coordinator judgment.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from trader_research.methodology import math_run_multiple_testing_report
from tests.trader_research.methodology.support.method_cards import (
    approved_method_card_reader,
)


def test_multiple_testing_applies_benjamini_hochberg_to_declared_family(
    tmp_path: Path,
) -> None:
    """Benjamini-Hochberg correction deterministically accepts only candidates below the adjusted threshold."""
    artifact_root = tmp_path / "artifacts"
    result = math_run_multiple_testing_report(
        artifact_root=artifact_root,
        candidate_family_manifest=_candidate_family(),
        metric_matrix=[
            {
                "candidate_id": "c1",
                "p_value": 0.01,
                "metric_name": "rank_ic_p_value",
                "metric_value": 0.8,
            },
            {
                "candidate_id": "c2",
                "p_value": 0.04,
                "metric_name": "rank_ic_p_value",
                "metric_value": 0.5,
            },
            {
                "candidate_id": "c3",
                "p_value": 0.03,
                "metric_name": "rank_ic_p_value",
                "metric_value": 0.6,
            },
            {
                "candidate_id": "c4",
                "p_value": 0.20,
                "metric_name": "rank_ic_p_value",
                "metric_value": 0.1,
            },
        ],
        method_contract=_bh_contract(),
        approved_card_reader=approved_method_card_reader(
            artifact_root,
            method_id="benjamini_hochberg",
            method_card_id="method_card_benjamini_hochberg_validated_v1",
            family="multiple_testing",
        ),
    )

    assert result.ok is True, result.to_dict()
    report = result.data["multiple_testing_report"]
    rows = {row["candidate_id"]: row for row in report["results"]}

    assert report["artifact_type"] == "multiple_testing_report"
    assert report["candidate_count"] == 4
    assert report["correction_method"] == "benjamini_hochberg"
    assert rows["c1"]["adjusted_p_value"] == pytest.approx(0.04)
    assert rows["c2"]["adjusted_p_value"] == pytest.approx(0.05333333333333334)
    assert rows["c3"]["adjusted_p_value"] == pytest.approx(0.05333333333333334)
    assert rows["c4"]["adjusted_p_value"] == pytest.approx(0.20)
    assert report["accepted_candidate_ids"] == ["c1"]
    assert set(report["rejected_candidate_ids"]) == {"c2", "c3", "c4"}
    assert result.artifacts["multiple_testing_report"]["path"]


def test_multiple_testing_requires_candidate_family_manifest(tmp_path: Path) -> None:
    """Correction requires an identified candidate family with an explicit candidate set."""
    result = math_run_multiple_testing_report(
        artifact_root=tmp_path / "artifacts",
        candidate_family_manifest={},
        metric_matrix=[],
        method_contract=_bh_contract(),
    )

    assert result.ok is False
    report = result.data["multiple_testing_report"]
    assert (
        "candidate_family_manifest.candidate_family_id is required"
        in report["blockers"]
    )
    assert "candidate_family_manifest.candidates is required" in report["blockers"]


def test_multiple_testing_fails_on_invalid_candidates_and_p_values(
    tmp_path: Path,
) -> None:
    """Correction rejects duplicates, unknown candidates, and probabilities outside valid bounds."""
    result = math_run_multiple_testing_report(
        artifact_root=tmp_path / "artifacts",
        candidate_family_manifest=_candidate_family(),
        metric_matrix=[
            {"candidate_id": "c1", "p_value": 0.01},
            {"candidate_id": "c1", "p_value": 0.02},
            {"candidate_id": "unknown", "p_value": 0.03},
            {"candidate_id": "c2", "p_value": 1.2},
        ],
        method_contract=_bh_contract(),
    )

    assert result.ok is False
    report = result.data["multiple_testing_report"]
    assert "duplicate metric row candidate_id: c1" in report["blockers"]
    assert "metric row references unknown candidate_id: unknown" in report["blockers"]
    assert "invalid p-value for candidate_id: c2" in report["blockers"]


def test_multiple_testing_requires_bh_method_card_evidence(tmp_path: Path) -> None:
    """Benjamini-Hochberg execution requires approved source evidence for its method contract."""
    result = math_run_multiple_testing_report(
        artifact_root=tmp_path / "artifacts",
        candidate_family_manifest={
            "candidate_family_id": "family",
            "candidates": [{"candidate_id": "c1"}],
        },
        metric_matrix=[{"candidate_id": "c1", "p_value": 0.01}],
        method_contract={
            "method_id": "benjamini_hochberg",
            "parameters": {"alpha": 0.05},
        },
    )

    assert result.ok is False
    report = result.data["multiple_testing_report"]
    assert (
        "approved method-card evidence is required for benjamini_hochberg"
        in report["blockers"]
    )


def _candidate_family() -> dict[str, object]:
    return {
        "candidate_family_id": "family_bh_demo",
        "candidates": [{"candidate_id": f"c{idx}"} for idx in range(1, 5)],
        "tested_grid": {"period": [10, 20], "threshold": [0.0, 1.0]},
    }


def _bh_contract() -> dict[str, object]:
    return {
        "method_id": "benjamini_hochberg",
        "parameters": {"alpha": 0.05},
        "knowledge_evidence_refs": [
            {"method_card_id": "method_card_benjamini_hochberg_validated_v1"}
        ],
    }
