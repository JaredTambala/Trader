"""Fresh-process reader for the retained UJ-09 human decision qualification."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from trader_agents import (
    EvidenceGraphStore,
    EvidenceStatus,
    ResolvedReviewArtifact,
    ReviewAssessmentStatus,
    SessionEvidenceGraph,
    SessionReviewResolution,
    resolve_session_review_evidence,
)
from trader_research.foundation import ResearchArtifactNotFound, json_payload_hash
from trader_research.governance import SessionReviewLink, get_next_research_decision
from trader_research.infrastructure.postgres import PostgresResearchArtifactStore


def resolve_reviewed_graph(
    store: PostgresResearchArtifactStore,
    graph: SessionEvidenceGraph,
    link: SessionReviewLink,
) -> SessionReviewResolution:
    """Verify exact retained graph identity and canonical named review facts."""
    if (
        link.session_id != graph.session_id
        or link.session_digest != graph.session_digest
        or link.graph_digest != json_payload_hash(graph.to_dict())
    ):
        raise ValueError("recovered decision graph identity changed")

    def lookup(artifact_type: str, artifact_id: str) -> ResolvedReviewArtifact | None:
        """Read actual public identity and review facts from canonical Postgres."""
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
            source_hash=record.source_hash,
            limitations=tuple(metadata["limitations"]),
            uncertainty=tuple(metadata["uncertainty"]),
            comparison_exclusions=tuple(metadata["comparison_exclusions"]),
            statistical_status=ReviewAssessmentStatus(str(metadata["statistical_status"])),
            robustness_status=ReviewAssessmentStatus(str(metadata["robustness_status"])),
        )

    return resolve_session_review_evidence(
        graph, scope_id="scope-1", strategy_version_id="strategy-v1",
        required_node_keys=link.review_node_keys, lookup=lookup,
    )


def main() -> None:
    """Reopen canonical decision and graph from a separate Python process."""
    dsn, graph_path, decision_id = sys.argv[1:4]
    store = PostgresResearchArtifactStore(dsn=dsn, ensure_schema=False)
    try:
        graph = EvidenceGraphStore(Path(graph_path)).load()
        result = get_next_research_decision(decision_id, artifact_store=store)
        if not result.ok:
            raise RuntimeError(result.errors[0]["message"])
        decision = result.data["research_next_decision"]
        link = SessionReviewLink.from_dict(decision["session_review"])
        resolution = resolve_reviewed_graph(store, graph, link)
        print(json.dumps({"decision": decision, "resolution": resolution.to_dict()}, sort_keys=True))
    finally:
        store.close()


if __name__ == "__main__":
    main()
