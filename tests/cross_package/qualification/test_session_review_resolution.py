"""Qualification of the UJ-09 graph-to-canonical-artifact seam.

Subject: Exact graph revision re-read through the research artifact contract.
Level: Deterministic cross-package qualification with retained graph storage.
Collaborators: Agent public graph and real in-memory research artifact store;
no Postgres, browser, model, or broker.
Guarantees: Canonical lookup, stale-revision rejection, and stable reopen.
Non-goals: Product event persistence or independent scientific validation.
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess

from trader_agents import (
    EvidenceGraphStore,
    EvidenceNode,
    EvidenceStatus,
    ResolvedReviewArtifact,
    ReviewAssessmentStatus,
    SessionEvidenceGraph,
    resolve_session_review_evidence,
)
from trader_research.foundation import InMemoryResearchArtifactStore, ResearchArtifactNotFound


def _lookup(store: InMemoryResearchArtifactStore, artifact_type: str, artifact_id: str) -> ResolvedReviewArtifact | None:
    """Read exact canonical type/ID and normalize only public review facts."""
    try:
        record = store.load_artifact_record(artifact_type, artifact_id)
    except ResearchArtifactNotFound:
        return None
    metadata = record.metadata
    return ResolvedReviewArtifact(
        artifact_type=record.artifact_type,
        artifact_id=record.artifact_id,
        revision=int(metadata["revision"]),
        uri=record.uri,
        domain_owner=record.domain_owner,
        session_id=str(metadata["session_id"]),
        branch_id=str(metadata["branch_id"]),
        run_id=str(metadata["run_id"]),
        scope_id=str(metadata["scope_id"]),
        strategy_version_id=str(metadata["strategy_version_id"]),
        status=EvidenceStatus(str(record.status)),
        uncertainty=tuple(metadata["uncertainty"]),
        comparison_exclusions=tuple(metadata["comparison_exclusions"]),
        statistical_status=ReviewAssessmentStatus(str(metadata["statistical_status"])),
        robustness_status=ReviewAssessmentStatus(str(metadata["robustness_status"])),
    )


def test_retained_graph_resolves_exact_canonical_revision_after_reopen(tmp_path: Path) -> None:
    """Reopening a retained graph cannot turn a newer record into revision one."""
    store = InMemoryResearchArtifactStore()
    node = EvidenceNode(
        artifact_type="evaluation_report",
        artifact_id="evaluation-1",
        revision=1,
        status=EvidenceStatus.AVAILABLE,
        uri="research://postgres/evaluation_report/evaluation-1",
        domain_owner="Review",
        branch_id="branch-review",
        claim_scope={"run_id": "run-1", "scope_id": "scope-1"},
    )
    graph = SessionEvidenceGraph(
        session_id="session-1", session_digest="a" * 64,
        branch_ids=("branch-review",), run_id="run-1", nodes=(node,),
    )
    path = tmp_path / "uj09-review-graph.json"
    EvidenceGraphStore(path).save(graph)
    reopened = EvidenceGraphStore(path).load()
    metadata = {
        "revision": 1, "session_id": "session-1", "branch_id": "branch-review",
        "run_id": "run-1", "scope_id": "scope-1",
        "strategy_version_id": "strategy-v1",
        "uncertainty": ["Small sample"],
        "comparison_exclusions": ["Different cost assumptions"],
        "statistical_status": "inconclusive", "robustness_status": "not_assessed",
    }
    store.save_artifact(
        artifact_type=node.artifact_type, artifact_id=node.artifact_id,
        domain_owner="Review", producer_tool="evaluate_backtest",
        payload={"schema_version": "1", "claim": "bounded"},
        status="available", metadata=metadata,
    )

    def resolve() -> dict[str, object]:
        """Read the exact graph reference through the canonical store."""
        return resolve_session_review_evidence(
            reopened, scope_id="scope-1", strategy_version_id="strategy-v1",
            required_node_keys=(node.key,),
            lookup=lambda kind, identity: _lookup(store, kind, identity),
        ).to_dict()

    first = resolve()
    assert first["verdict"] == "complete"
    assert first["artifacts"][0]["statistical_status"] == "inconclusive"
    assert first["artifacts"][0]["comparison_exclusions"] == ["Different cost assumptions"]

    store.save_artifact(
        artifact_type=node.artifact_type, artifact_id=node.artifact_id,
        domain_owner="Review", producer_tool="evaluate_backtest",
        payload={"schema_version": "1", "claim": "revised"},
        status="available", metadata={**metadata, "revision": 2},
    )
    second = resolve()
    assert second["verdict"] == "blocked"
    assert second["artifacts"][0]["status"] == "stale"
    assert second["artifacts"][0]["key"] == node.key

    checkout_root = Path(__file__).resolve().parents[3]
    checkout_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=checkout_root, check=True, capture_output=True, text=True,
    ).stdout.strip()
    verifier_report = {
        "fixture_id": "uj09-exact-review-resolution-v1",
        "contract": "SessionReviewResolution",
        "contract_version": "1",
        "checkout_commit": checkout_commit,
        "evidence_revision": node.revision,
        "named_artifact_key": node.key,
        "initial_resolution": first,
        "after_canonical_revision_change": second,
    }
    report_path = tmp_path / "uj09-review-resolution-verifier.json"
    report_path.write_text(
        json.dumps(verifier_report, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    retained = json.loads(report_path.read_text(encoding="utf-8"))
    assert retained["fixture_id"] == "uj09-exact-review-resolution-v1"
    assert retained["contract"] == "SessionReviewResolution"
    assert retained["contract_version"] == "1"
    assert retained["checkout_commit"] == checkout_commit
    assert retained["evidence_revision"] == 1
    assert retained["initial_resolution"]["verdict"] == "complete"
    assert retained["after_canonical_revision_change"]["artifacts"][0]["status"] == "stale"
