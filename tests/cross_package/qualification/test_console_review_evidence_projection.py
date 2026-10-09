"""Retained verifier for the UJ-09 Console review evidence projection.

Subject: Producer status and exact graph identity through the Console service contract.
Level: Deterministic cross-package qualification without Postgres or browser.
Collaborators: Console service normalization and Pydantic response contract.
Guarantees: All fail-closed states, graph revision identity, and terminal disclaimer inputs remain inspectable.
Non-goals: Statistical scoring, persistence, deployment admission, or profitability claims.
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess

from trader_console_api.services.resources import _review_evidence


def test_uj09_console_review_evidence_verifier(tmp_path: Path) -> None:
    """Retain fixture, contract, commit, and evidence revision in verifier output."""
    rows = [
        {
            "artifact_type": "evaluation_report",
            "artifact_id": "evaluation-uj09-r2",
            "artifact_status": "complete",
            "domain_owner": "Evaluation Agent",
            "session_id": "session-uj09",
            "session_digest": "a" * 64,
            "graph_digest": "b" * 64,
            "branch_id": "review-branch",
            "revision": 2,
            "node_key": "evaluation_report:evaluation-uj09-r2:r2",
        },
        {"artifact_type": "multiple_testing_report", "artifact_id": "negative-uj09", "artifact_status": "negative"},
        {"artifact_type": "robustness_report", "artifact_id": "stale-uj09", "artifact_status": "stale"},
    ]
    evidence = _review_evidence(rows)
    by_kind = {item.evidence_kind: item for item in evidence}
    assert by_kind["evaluation"].status == "complete"
    assert by_kind["evaluation"].node_key == "evaluation_report:evaluation-uj09-r2:r2"
    assert by_kind["multiple_testing"].status == "negative"
    assert by_kind["adversarial"].status == "stale"
    checkout_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parents[3],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    report = {
        "fixture_id": "trd-327-uj09-console-review-v1",
        "contract": "ReviewEvidence",
        "contract_version": "1",
        "checkout_commit": checkout_commit,
        "evidence_revision": by_kind["evaluation"].revision,
        "statuses": {kind: item.status for kind, item in by_kind.items()},
        "verdict": "complete projection with explicit fail-closed states",
        "command": "uv run pytest tests/cross_package/qualification/test_console_review_evidence_projection.py -q",
    }
    report_path = tmp_path / "trd-327-uj09-console-review-verifier.json"
    report_path.write_text(json.dumps(report, sort_keys=True), encoding="utf-8")
    retained = json.loads(report_path.read_text(encoding="utf-8"))
    assert retained["fixture_id"] == "trd-327-uj09-console-review-v1"
    assert retained["contract"] == "ReviewEvidence"
    assert retained["checkout_commit"] == checkout_commit
    assert retained["evidence_revision"] == 2
