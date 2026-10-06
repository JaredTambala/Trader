"""Qualification tests for the retained UJ-09 session evidence graph.

Subject: Redacted session-to-artifact evidence graph and verifier.
Level: Deterministic local qualification with atomic JSON persistence.
Collaborators: Public agent evidence contracts only; no model, MCP, Postgres,
or canonical artifact payloads.
Guarantees: Exact artifact revisions and URIs, stable Console projection,
fresh-process reopen, and explicit complete/partial/blocked states.
Non-goals: Independent statistical review, browser layout, or deployment
authorization.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from trader_agents import (
    EvidenceEdge,
    EvidenceGraphStore,
    EvidenceNode,
    EvidenceStatus,
    SessionEvidenceGraph,
    verify_session_evidence_graph,
)


SESSION_ID = "uj09-session"
SESSION_DIGEST = "a" * 64


def test_complete_graph_preserves_exact_revisions_and_stable_console_shape() -> None:
    """A complete graph joins exact immutable revisions into stable output."""
    graph = _graph()

    result = verify_session_evidence_graph(
        graph,
        expected_branch_ids=("branch-data", "branch-strategy", "branch-root"),
        required_node_keys=("dataset_manifest:manifest-1:r2", "backtest_run:run-1:r3"),
    )

    assert result["verdict"] == "complete"
    assert all(result["checks"].values())
    rendered = graph.to_console_dict()
    assert [node["key"] for node in rendered["nodes"]] == sorted(
        node["key"] for node in rendered["nodes"]
    )
    assert next(
        node["revision"]
        for node in rendered["nodes"]
        if node["artifact_id"] == "manifest-1"
    ) == 2
    assert rendered["verification"] == result


@pytest.mark.parametrize(
    ("status", "expected_verdict"),
    [
        (EvidenceStatus.PARTIAL, "partial"),
        (EvidenceStatus.NEGATIVE, "partial"),
        (EvidenceStatus.MISSING, "blocked"),
        (EvidenceStatus.INCOMPATIBLE, "blocked"),
        (EvidenceStatus.STALE, "blocked"),
        (EvidenceStatus.REDACTED, "blocked"),
    ],
)
def test_graph_preserves_non_positive_evidence_states(
    status: EvidenceStatus,
    expected_verdict: str,
) -> None:
    """Partial, negative, missing, and incompatible evidence stays explicit."""
    nodes = list(_graph().nodes)
    nodes[-1] = EvidenceNode(
        artifact_type=nodes[-1].artifact_type,
        artifact_id=nodes[-1].artifact_id,
        revision=nodes[-1].revision,
        status=status,
        uri=nodes[-1].uri,
        domain_owner=nodes[-1].domain_owner,
        branch_id=nodes[-1].branch_id,
        claim_scope=nodes[-1].claim_scope,
        limitations=("Producer did not establish the complete claim.",),
        blockers=("review evidence is unavailable",) if status in {EvidenceStatus.MISSING, EvidenceStatus.INCOMPATIBLE, EvidenceStatus.STALE, EvidenceStatus.REDACTED} else (),
    )
    graph = SessionEvidenceGraph(
        session_id=SESSION_ID,
        session_digest=SESSION_DIGEST,
        branch_ids=("branch-data", "branch-strategy", "branch-root"),
        nodes=tuple(nodes),
        edges=_graph().edges,
        run_id="run-1",
    )

    result = verify_session_evidence_graph(graph)

    assert result["verdict"] == expected_verdict
    assert result["statuses"][status.value] == 1
    assert "review evidence is unavailable" in result["blockers"] if status in {EvidenceStatus.MISSING, EvidenceStatus.INCOMPATIBLE, EvidenceStatus.STALE, EvidenceStatus.REDACTED} else True


def test_graph_reopens_in_a_fresh_process_with_identical_verifier_output(tmp_path: Path) -> None:
    """A new process reloads the retained graph and reproduces its output."""
    storage_path = tmp_path / "uj09-evidence-graph.json"
    graph = _graph()
    EvidenceGraphStore(storage_path).save(graph)
    source_root = Path(__file__).resolve().parents[3] / "src"
    python_path = str(source_root)
    existing_python_path = os.environ.get("PYTHONPATH")
    if existing_python_path:
        python_path += os.pathsep + existing_python_path
    script = """
import json
import sys
from trader_agents import EvidenceGraphStore
print(json.dumps(EvidenceGraphStore(sys.argv[1]).load().to_console_dict(), sort_keys=True))
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(storage_path)],
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": python_path},
    )

    assert json.loads(result.stdout) == graph.to_console_dict()


def test_graph_rejects_revision_or_edge_identity_drift() -> None:
    """A changed revision or unresolved edge cannot be rendered as evidence."""
    node = _graph().nodes[0]
    with pytest.raises(ValueError, match="URI does not match"):
        EvidenceNode(
            artifact_type=node.artifact_type,
            artifact_id=node.artifact_id,
            revision=node.revision,
            status=node.status,
            uri="research://postgres/dataset_manifest/other",
            domain_owner=node.domain_owner,
        )
    with pytest.raises(ValueError, match="unknown node"):
        SessionEvidenceGraph(
            session_id=SESSION_ID,
            session_digest=SESSION_DIGEST,
            branch_ids=("branch-root",),
            nodes=(node,),
            edges=(EvidenceEdge(source=node.key, target="missing:r1", relation="supports"),),
        )


def _graph() -> SessionEvidenceGraph:
    """Build one deterministic complete graph with two immutable revisions."""
    nodes = (
        EvidenceNode(
            artifact_type="dataset_manifest",
            artifact_id="manifest-1",
            revision=2,
            status=EvidenceStatus.AVAILABLE,
            uri="research://postgres/dataset_manifest/manifest-1",
            domain_owner="Data",
            branch_id="branch-data",
            source_hash="b" * 64,
            claim_scope={"symbols": ["AAA"], "timeframe": "1d"},
        ),
        EvidenceNode(
            artifact_type="backtest_run",
            artifact_id="run-1",
            revision=3,
            status=EvidenceStatus.AVAILABLE,
            uri="research://postgres/backtest_run/run-1",
            domain_owner="Experiments",
            branch_id="branch-root",
            claim_scope={"run_id": "run-1"},
        ),
        EvidenceNode(
            artifact_type="evaluation_report",
            artifact_id="evaluation-1",
            revision=1,
            status=EvidenceStatus.AVAILABLE,
            uri="research://postgres/evaluation_report/evaluation-1",
            domain_owner="Review",
            branch_id="branch-root",
            claim_scope={"run_id": "run-1", "claim": "bounded"},
        ),
    )
    return SessionEvidenceGraph(
        session_id=SESSION_ID,
        session_digest=SESSION_DIGEST,
        branch_ids=("branch-strategy", "branch-data", "branch-root"),
        nodes=nodes,
        edges=(
            EvidenceEdge(source=nodes[0].key, target=nodes[1].key, relation="used_by"),
            EvidenceEdge(source=nodes[1].key, target=nodes[2].key, relation="reviewed_by"),
        ),
        run_id="run-1",
    )
