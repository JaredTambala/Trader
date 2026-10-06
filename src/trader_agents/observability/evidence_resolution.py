"""Qualify exact canonical artifact reads for a bounded session review.

This pure boundary consumes normalized, public artifact facts supplied by a
trusted reader. It never opens the research store from agent runtime code or
retains canonical payloads, prompts, or tool responses.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from .evidence_graph import EvidenceNode, EvidenceStatus, SessionEvidenceGraph


class ReviewAssessmentStatus(StrEnum):
    """Explicit independent-test conclusion, including absence of a test."""

    NOT_ASSESSED = "not_assessed"
    PASS = "pass"
    FAIL = "fail"
    INCONCLUSIVE = "inconclusive"


@dataclass(frozen=True)
class ResolvedReviewArtifact:
    """Public facts from one canonical artifact read, excluding its payload.

    All identity fields must come from the record that was read, rather than
    from the graph's claim. A reader must return its actual revision even when
    a newer revision occupies the same artifact ID.
    """

    artifact_type: str
    artifact_id: str
    revision: int
    uri: str
    domain_owner: str
    session_id: str
    branch_id: str
    run_id: str
    scope_id: str
    strategy_version_id: str
    status: EvidenceStatus
    source_hash: str | None = None
    limitations: tuple[str, ...] = ()
    uncertainty: tuple[str, ...] = ()
    comparison_exclusions: tuple[str, ...] = ()
    statistical_status: ReviewAssessmentStatus = ReviewAssessmentStatus.NOT_ASSESSED
    robustness_status: ReviewAssessmentStatus = ReviewAssessmentStatus.NOT_ASSESSED
    blockers: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Reject ambiguous or unbounded public artifact facts."""
        text_values = (
            self.artifact_type, self.artifact_id, self.uri, self.domain_owner,
            self.session_id, self.branch_id, self.run_id, self.scope_id,
            self.strategy_version_id,
        )
        if any(not isinstance(value, str) or not value.strip() for value in text_values):
            raise ValueError("resolved review artifact requires complete identity")
        if isinstance(self.revision, bool) or not isinstance(self.revision, int) or self.revision < 1:
            raise ValueError("resolved review artifact revision must be positive")
        if not isinstance(self.status, EvidenceStatus):
            raise ValueError("resolved review artifact status is unsupported")
        if not isinstance(self.statistical_status, ReviewAssessmentStatus) or not isinstance(
            self.robustness_status, ReviewAssessmentStatus
        ):
            raise ValueError("resolved review assessment status is unsupported")
        if self.source_hash is not None and (
            len(self.source_hash) != 64
            or any(char not in "0123456789abcdef" for char in self.source_hash)
        ):
            raise ValueError("resolved review source hash must be lowercase SHA-256")
        for values in (self.limitations, self.uncertainty, self.comparison_exclusions, self.blockers):
            if len(values) > 32 or any(not isinstance(value, str) or not value.strip() for value in values):
                raise ValueError("resolved review details must contain bounded text")


@dataclass(frozen=True)
class ReviewArtifactResolution:
    """One graph reference checked against an independently read artifact."""

    key: str
    status: EvidenceStatus
    blockers: tuple[str, ...]
    limitations: tuple[str, ...] = ()
    uncertainty: tuple[str, ...] = ()
    comparison_exclusions: tuple[str, ...] = ()
    statistical_status: ReviewAssessmentStatus = ReviewAssessmentStatus.NOT_ASSESSED
    robustness_status: ReviewAssessmentStatus = ReviewAssessmentStatus.NOT_ASSESSED

    def to_dict(self) -> dict[str, Any]:
        """Return a deterministic, Console-safe resolution projection."""
        return {
            "key": self.key,
            "status": self.status.value,
            "blockers": list(self.blockers),
            "limitations": list(self.limitations),
            "uncertainty": list(self.uncertainty),
            "comparison_exclusions": list(self.comparison_exclusions),
            "statistical_status": self.statistical_status.value,
            "robustness_status": self.robustness_status.value,
        }


@dataclass(frozen=True)
class SessionReviewResolution:
    """Exact review results without any claim of approval or profitability."""

    session_id: str
    run_id: str
    scope_id: str
    strategy_version_id: str
    artifacts: tuple[ReviewArtifactResolution, ...]

    @property
    def verdict(self) -> str:
        """Classify evidence availability, never investment merit."""
        blocked = {
            EvidenceStatus.MISSING, EvidenceStatus.INCOMPATIBLE,
            EvidenceStatus.STALE, EvidenceStatus.REDACTED,
        }
        if not self.artifacts or any(item.status in blocked for item in self.artifacts):
            return "blocked"
        if any(item.status is not EvidenceStatus.AVAILABLE or item.blockers for item in self.artifacts):
            return "partial"
        return "complete"

    def to_dict(self) -> dict[str, Any]:
        """Expose explicit uncertainty, exclusions, and review status."""
        return {
            "session_id": self.session_id,
            "run_id": self.run_id,
            "scope_id": self.scope_id,
            "strategy_version_id": self.strategy_version_id,
            "verdict": self.verdict,
            "artifacts": [item.to_dict() for item in self.artifacts],
        }


def resolve_session_review_evidence(
    graph: SessionEvidenceGraph,
    *,
    scope_id: str,
    strategy_version_id: str,
    required_node_keys: Sequence[str],
    lookup: Callable[[str, str], ResolvedReviewArtifact | None],
) -> SessionReviewResolution:
    """Resolve named graph revisions against an independent canonical reader.

    A missing read stays missing; a newer revision at the same ID is stale.
    Other identity drift is incompatible. The reader must normalize canonical
    records to ``ResolvedReviewArtifact`` and must not substitute latest-by-type
    searches for exact type/ID reads. Operational reader failures propagate.
    """
    if (
        not graph.run_id
        or not isinstance(scope_id, str) or not scope_id.strip()
        or not isinstance(strategy_version_id, str) or not strategy_version_id.strip()
    ):
        raise ValueError("review resolution requires run, scope, and strategy identities")
    if isinstance(required_node_keys, str) or any(
        not isinstance(key, str) or not key.strip() for key in required_node_keys
    ):
        raise ValueError("review resolution requires named artifact revisions")
    requested = tuple(required_node_keys)
    if not requested or len(set(requested)) != len(requested):
        raise ValueError("review resolution requires unique named artifact revisions")
    nodes = {node.key: node for node in graph.nodes}
    results: list[ReviewArtifactResolution] = []
    for key in sorted(requested):
        node = nodes.get(key)
        if node is None:
            results.append(ReviewArtifactResolution(key, EvidenceStatus.MISSING, ("named graph revision is absent",)))
            continue
        if node.branch_id not in graph.branch_ids:
            results.append(ReviewArtifactResolution(key, EvidenceStatus.INCOMPATIBLE, ("branch is outside session graph",)))
            continue
        artifact = lookup(node.artifact_type, node.artifact_id)
        results.append(_resolve_node(node, artifact, graph, scope_id, strategy_version_id))
    return SessionReviewResolution(
        session_id=graph.session_id,
        run_id=graph.run_id,
        scope_id=scope_id,
        strategy_version_id=strategy_version_id,
        artifacts=tuple(results),
    )


def _resolve_node(
    node: EvidenceNode,
    artifact: ResolvedReviewArtifact | None,
    graph: SessionEvidenceGraph,
    scope_id: str,
    strategy_version_id: str,
) -> ReviewArtifactResolution:
    if artifact is None:
        return ReviewArtifactResolution(node.key, EvidenceStatus.MISSING, ("canonical artifact is absent",))
    if artifact.revision != node.revision:
        return ReviewArtifactResolution(node.key, EvidenceStatus.STALE, ("named revision differs from canonical revision",))
    expected = (
        node.artifact_type, node.artifact_id, node.uri, node.domain_owner,
        graph.session_id, node.branch_id, graph.run_id, scope_id,
        strategy_version_id,
    )
    actual = (
        artifact.artifact_type, artifact.artifact_id, artifact.uri, artifact.domain_owner,
        artifact.session_id, artifact.branch_id, artifact.run_id, artifact.scope_id,
        artifact.strategy_version_id,
    )
    if actual != expected or (node.source_hash and artifact.source_hash != node.source_hash):
        return ReviewArtifactResolution(node.key, EvidenceStatus.INCOMPATIBLE, ("canonical artifact identity or scope differs",))
    if node.status is EvidenceStatus.REDACTED or artifact.status is EvidenceStatus.REDACTED:
        status = EvidenceStatus.REDACTED
    elif node.status is EvidenceStatus.NEGATIVE or artifact.status is EvidenceStatus.NEGATIVE:
        status = EvidenceStatus.NEGATIVE
    elif node.status is EvidenceStatus.AVAILABLE:
        status = artifact.status
    else:
        status = node.status
    return ReviewArtifactResolution(
        key=node.key,
        status=status,
        blockers=tuple(sorted(set((*node.blockers, *artifact.blockers)))),
        limitations=tuple(sorted(set((*node.limitations, *artifact.limitations)))),
        uncertainty=artifact.uncertainty,
        comparison_exclusions=artifact.comparison_exclusions,
        statistical_status=artifact.statistical_status,
        robustness_status=artifact.robustness_status,
    )


__all__ = [
    "ResolvedReviewArtifact", "ReviewArtifactResolution", "ReviewAssessmentStatus",
    "SessionReviewResolution", "resolve_session_review_evidence",
]
