"""Qualify the UJ-09 human decision against retained session evidence.

Subject: Human-owned decisions over an exact review graph and canonical records.
Level: Cross-package multi-process PostgreSQL qualification.
Collaborators: Test-owned Docker PostgreSQL, public graph store, research
artifact store, and a fresh reader process; no model, browser, or broker.
Guarantees: Immutable revisions retain actor, rationale, exact graph/review
lineage, and bounded successor; stale and unauthorized writes fail closed.
Non-goals: Independent scientific judgment or product graph persistence.
Cohesion: One isolated campaign creates, rejects, and recovers the same decision stream.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
import psycopg
from psycopg.types.json import Jsonb

from examples.console_demo.runtime import demo_dsn
from tests.cross_package.qualification.support.session_review_decision_reader import resolve_reviewed_graph
from tests.cross_package.workflows.console_stack import REPO_ROOT, database
from trader_agents import EvidenceGraphStore, EvidenceNode, EvidenceStatus, SessionEvidenceGraph
from trader_research.foundation import json_payload_hash, research_artifact_uri
from trader_research.governance import (
    BoundedNextExperiment,
    NextDecisionOutcome,
    SessionReviewLink,
    build_next_research_decision,
    create_next_research_decision,
)
from trader_research.governance.handoffs import ArtifactReportRef
from trader_research.infrastructure.postgres import PostgresResearchArtifactStore


pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        os.environ.get("TRD326_DECISION_TESTS") != "1",
        reason="Set TRD326_DECISION_TESTS=1 to provision an isolated Docker database",
    ),
]


def _seed(dsn: str) -> dict[str, ArtifactReportRef]:
    """Create complete canonical references with immutable payload hashes."""
    definitions = (
        ("backtest_run", "run-1", "Experiments", {"run_id": "run-1", "status": "completed"}, {}),
        ("dataset_manifest", "data-1", "Data", {"scope_fingerprint": "scope-v1"}, {}),
        ("implementation_version", "impl-1", "Experiments", {"version": "strategy-v1"}, {}),
        (
            "evaluation_report", "review-1", "Review",
            {"run_id": "run-1", "claim": "inconclusive"},
            {
                "revision": 1, "session_id": "session-1", "branch_id": "branch-review",
                "run_id": "run-1", "scope_id": "scope-1", "strategy_version_id": "strategy-v1",
                "limitations": ["One market regime"], "uncertainty": ["Wide interval"],
                "comparison_exclusions": ["Different fees"],
                "statistical_status": "inconclusive", "robustness_status": "not_assessed",
            },
        ),
    )
    refs: dict[str, ArtifactReportRef] = {}
    with psycopg.connect(dsn) as connection:
        for artifact_type, artifact_id, owner, payload, metadata in definitions:
            digest = json_payload_hash(payload)
            connection.execute(
                "INSERT INTO research_artifacts (artifact_type, artifact_id, domain_owner, "
                "producer_tool, status, schema_version, source_hash, metadata, payload) "
                "VALUES (%s, %s, %s, 'uj09_decision_fixture', 'available', '1', %s, %s, %s)",
                [artifact_type, artifact_id, owner, digest, Jsonb(metadata), Jsonb(payload)],
            )
            refs[artifact_id] = ArtifactReportRef(
                artifact_type=artifact_type, artifact_id=artifact_id,
                domain_owner=owner, uri=research_artifact_uri(artifact_type, artifact_id),
                metadata={"payload_sha256": digest},
            )
    return refs


def _decision(
    refs: dict[str, ArtifactReportRef], link: SessionReviewLink, *,
    outcome: NextDecisionOutcome = NextDecisionOutcome.REJECT,
    revision: int = 1,
    supersedes_artifact_id: str | None = None,
    next_experiment: BoundedNextExperiment | None = None,
):
    """Build one human-authored revision against exact graph and review refs."""
    return build_next_research_decision(
        decision_id="uj09-decision-1", revision=revision, outcome=outcome,
        rationale="Review evidence is inconclusive; the next step is bounded.",
        operator="human:jared", decided_at="2026-10-06T12:00:00Z",
        source_run_ref=refs["run-1"], data_ref=refs["data-1"],
        implementation_refs=(refs["impl-1"],), assumptions={"fill_model": "next_bar"},
        review_refs=(refs["review-1"],), limitations=("One market regime",),
        session_review=link, next_experiment=next_experiment,
        supersedes_artifact_id=supersedes_artifact_id,
    )


def test_human_decision_reopens_exact_graph_and_revisions_after_process_restart(tmp_path: Path) -> None:
    """A new process reconstructs the same two immutable choices and review context."""
    with database() as (port, _compose, _environment):
        dsn = demo_dsn(port)
        store = PostgresResearchArtifactStore(dsn=dsn, ensure_schema=False)
        try:
            refs = _seed(dsn)
            node = EvidenceNode(
                artifact_type="evaluation_report", artifact_id="review-1", revision=1,
                status=EvidenceStatus.AVAILABLE, uri=refs["review-1"].uri,
                domain_owner="Review", branch_id="branch-review",
                source_hash=json_payload_hash({"run_id": "run-1", "claim": "inconclusive"}),
                claim_scope={"run_id": "run-1", "scope_id": "scope-1"},
            )
            graph = SessionEvidenceGraph(
                session_id="session-1", session_digest="a" * 64,
                branch_ids=("branch-review",), run_id="run-1", nodes=(node,),
            )
            graph_path = tmp_path / "uj09-session-graph.json"
            EvidenceGraphStore(graph_path).save(graph)
            link = SessionReviewLink(
                session_id=graph.session_id, session_digest=graph.session_digest,
                graph_digest=json_payload_hash(graph.to_dict()),
                review_node_keys=(node.key,),
            )
            assert resolve_reviewed_graph(store, EvidenceGraphStore(graph_path).load(), link).verdict == "complete"
            first = _decision(refs, link)
            created = create_next_research_decision(
                first.to_dict(), artifact_store=store,
                requested_by="human:jared", actor="human:jared",
            )
            assert created.ok, created.errors
            retry = create_next_research_decision(
                first.to_dict(), artifact_store=store,
                requested_by="human:jared", actor="human:jared",
            )
            assert retry.ok
            assert len(store.list_artifacts(artifact_type="research_next_decision")) == 1

            successor = BoundedNextExperiment(
                question="Does the result survive another holdout?",
                data_ref=refs["data-1"], implementation_refs=(refs["impl-1"],),
                assumptions={"fill_model": "next_bar"},
                evaluation_start="2026-11-01T00:00:00Z",
                evaluation_end="2026-12-01T00:00:00Z", max_runs=3,
                success_criteria=("No material degradation",),
            )
            second = _decision(
                refs, link, outcome=NextDecisionOutcome.REFINE, revision=2,
                supersedes_artifact_id=first.artifact_id, next_experiment=successor,
            )
            appended = create_next_research_decision(
                second.to_dict(), artifact_store=store,
                requested_by="human:jared", actor="human:jared",
            )
            assert appended.ok, appended.errors
            assert len(store.list_artifacts(artifact_type="research_next_decision")) == 2

            agent = create_next_research_decision(
                first.to_dict(), artifact_store=store,
                requested_by="agent:research", actor="agent:research",
            )
            assert not agent.ok and "human principal" in agent.errors[0]["message"]
            with pytest.raises(ValueError, match="rationale"):
                build_next_research_decision(
                    decision_id="missing-rationale", revision=1,
                    outcome=NextDecisionOutcome.REJECT, rationale=" ",
                    operator="human:jared", decided_at="2026-10-06T12:00:00Z",
                    source_run_ref=refs["run-1"], data_ref=refs["data-1"],
                    implementation_refs=(refs["impl-1"],), assumptions={},
                    review_refs=(refs["review-1"],), limitations=("One market regime",),
                    session_review=link,
                )
            with pytest.raises(ValueError, match="max_runs"):
                BoundedNextExperiment(
                    question="Unbounded follow-up", data_ref=refs["data-1"],
                    implementation_refs=(refs["impl-1"],), assumptions={},
                    evaluation_start="2026-11-01T00:00:00Z",
                    evaluation_end="2026-12-01T00:00:00Z", max_runs=101,
                    success_criteria=("Any result",),
                )
            changed_impl = ArtifactReportRef(
                artifact_type="implementation_version", artifact_id="impl-1",
                domain_owner="Experiments", uri=refs["impl-1"].uri,
                metadata={"payload_sha256": "0" * 64},
            )
            changed_version = build_next_research_decision(
                decision_id="changed-version", revision=1,
                outcome=NextDecisionOutcome.REJECT, rationale="Changed version must block.",
                operator="human:jared", decided_at="2026-10-06T12:00:00Z",
                source_run_ref=refs["run-1"], data_ref=refs["data-1"],
                implementation_refs=(changed_impl,), assumptions={},
                review_refs=(refs["review-1"],), limitations=("One market regime",),
                session_review=link,
            )
            changed_result = create_next_research_decision(
                changed_version.to_dict(), artifact_store=store,
                requested_by="human:jared", actor="human:jared",
            )
            assert not changed_result.ok and "payload has changed" in changed_result.errors[0]["message"]
            stale_link = SessionReviewLink(
                session_id=link.session_id, session_digest=link.session_digest,
                graph_digest=link.graph_digest,
                review_node_keys=("evaluation_report:review-1:r2",),
            )
            stale = create_next_research_decision(
                _decision(refs, stale_link, revision=3, supersedes_artifact_id=second.artifact_id).to_dict(),
                artifact_store=store, requested_by="human:jared", actor="human:jared",
            )
            assert not stale.ok and "identity changed" in stale.errors[0]["message"]
        finally:
            store.close()

        recovered: list[dict[str, object]] = []
        for decision in (first, second):
            process = subprocess.run(
                [
                    sys.executable, "-m",
                    "tests.cross_package.qualification.support.session_review_decision_reader",
                    dsn, str(graph_path), decision.artifact_id,
                ],
                cwd=REPO_ROOT, capture_output=True, text=True, timeout=30, check=True,
            )
            reopened = json.loads(process.stdout)
            assert reopened["decision"] == decision.to_dict()
            assert reopened["resolution"]["verdict"] == "complete"
            recovered.append(reopened)

        checkout_commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT,
            check=True, capture_output=True, text=True,
        ).stdout.strip()
        report = {
            "fixture_id": "uj09-human-next-decision-v1",
            "contract": "NextResearchDecision/SessionReviewLink",
            "contract_version": "1",
            "checkout_commit": checkout_commit,
            "evidence_revision": node.revision,
            "graph_digest": link.graph_digest,
            "decision_artifact_ids": [first.artifact_id, second.artifact_id],
            "fresh_process_recovered": recovered,
        }
        report_path = tmp_path / "uj09-human-next-decision-verifier.json"
        report_path.write_text(json.dumps(report, sort_keys=True), encoding="utf-8")
        assert json.loads(report_path.read_text(encoding="utf-8")) == report

        changed_graph_path = tmp_path / "uj09-changed-graph.json"
        EvidenceGraphStore(changed_graph_path).save(SessionEvidenceGraph(
            session_id=graph.session_id, session_digest="b" * 64,
            branch_ids=graph.branch_ids, run_id=graph.run_id, nodes=graph.nodes,
        ))
        changed_graph = subprocess.run(
            [
                sys.executable, "-m",
                "tests.cross_package.qualification.support.session_review_decision_reader",
                dsn, str(changed_graph_path), first.artifact_id,
            ],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=30,
        )
        assert changed_graph.returncode != 0
        assert "graph identity changed" in changed_graph.stderr
