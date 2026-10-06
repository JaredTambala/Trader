"""Retained, redacted evidence graphs for agent-session review.

The graph is a small projection over the public trajectory and canonical
artifact identities.  It deliberately stores references, revisions, claim
scope, and bounded limitations only; prompts, model messages, and raw tool
payloads are not valid graph values.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
import json
import os
from pathlib import Path
import tempfile
from typing import Any

from trader_research.foundation import jsonable


class EvidenceStatus(StrEnum):
    """Public availability state for one evidence node."""

    AVAILABLE = "available"
    PARTIAL = "partial"
    MISSING = "missing"
    INCOMPATIBLE = "incompatible"
    STALE = "stale"
    REDACTED = "redacted"
    NEGATIVE = "negative"


class EvidenceGraphUnavailable(RuntimeError):
    """Raised when a retained graph cannot be read or written."""


@dataclass(frozen=True)
class EvidenceNode:
    """One exact artifact identity and its bounded review qualification."""

    artifact_type: str
    artifact_id: str
    revision: int
    status: EvidenceStatus
    uri: str
    domain_owner: str
    branch_id: str | None = None
    source_hash: str | None = None
    claim_scope: Mapping[str, Any] = field(default_factory=dict)
    limitations: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Validate identity, revision, and bounded public fields."""
        if not isinstance(self.artifact_type, str) or not isinstance(self.artifact_id, str):
            raise ValueError("evidence node type and identity must be text")
        if not self.artifact_type.strip() or not self.artifact_id.strip():
            raise ValueError("evidence node type and identity are required")
        if isinstance(self.revision, bool) or self.revision < 1:
            raise ValueError("evidence node revision must be positive")
        if not isinstance(self.status, EvidenceStatus):
            raise ValueError("evidence node status is unsupported")
        expected_uri = f"research://postgres/{self.artifact_type}/{self.artifact_id}"
        if self.uri != expected_uri:
            raise ValueError("evidence node URI does not match type and identity")
        if not isinstance(self.domain_owner, str) or not self.domain_owner.strip():
            raise ValueError("evidence node domain owner is required")
        if self.source_hash is not None and (
            len(self.source_hash) != 64
            or any(char not in "0123456789abcdef" for char in self.source_hash)
        ):
            raise ValueError("evidence node source hash must be lowercase SHA-256")
        if not isinstance(self.claim_scope, Mapping):
            raise ValueError("evidence node claim scope must be an object")
        _validate_public_mapping(self.claim_scope)
        for label, values in (("limitations", self.limitations), ("blockers", self.blockers)):
            if len(values) > 32 or any(not isinstance(value, str) or not value.strip() for value in values):
                raise ValueError(f"evidence node {label} must contain bounded text")

    @property
    def key(self) -> str:
        """Return a stable identity including the exact immutable revision."""
        return f"{self.artifact_type}:{self.artifact_id}:r{self.revision}"

    def to_dict(self) -> dict[str, Any]:
        """Return the stable Console-safe node projection."""
        return {
            "key": self.key,
            "artifact_type": self.artifact_type,
            "artifact_id": self.artifact_id,
            "revision": self.revision,
            "status": self.status.value,
            "uri": self.uri,
            "domain_owner": self.domain_owner,
            "branch_id": self.branch_id,
            "source_hash": self.source_hash,
            "claim_scope": _stable_json(self.claim_scope),
            "limitations": list(self.limitations),
            "blockers": list(self.blockers),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "EvidenceNode":
        """Parse one strict persisted node projection."""
        allowed = {
            "key", "artifact_type", "artifact_id", "revision", "status", "uri",
            "domain_owner", "branch_id", "source_hash", "claim_scope", "limitations", "blockers",
        }
        unknown = set(payload) - allowed
        if unknown:
            raise ValueError("evidence node contains unknown fields: " + ", ".join(sorted(unknown)))
        node = cls(
            artifact_type=str(payload.get("artifact_type") or ""),
            artifact_id=str(payload.get("artifact_id") or ""),
            revision=_positive_int(payload.get("revision"), "revision"),
            status=EvidenceStatus(str(payload.get("status") or "")),
            uri=str(payload.get("uri") or ""),
            domain_owner=str(payload.get("domain_owner") or ""),
            branch_id=(str(payload["branch_id"]) if payload.get("branch_id") else None),
            source_hash=(str(payload["source_hash"]) if payload.get("source_hash") else None),
            claim_scope=_mapping(payload.get("claim_scope")),
            limitations=_text_tuple(payload.get("limitations")),
            blockers=_text_tuple(payload.get("blockers")),
        )
        if payload.get("key") not in (None, node.key):
            raise ValueError("evidence node key does not match its exact identity")
        return node


@dataclass(frozen=True)
class EvidenceEdge:
    """A typed relationship between two exact evidence-node revisions."""

    source: str
    target: str
    relation: str

    def __post_init__(self) -> None:
        """Require bounded, non-empty relationship identities."""
        if not all(isinstance(value, str) for value in (self.source, self.target, self.relation)):
            raise ValueError("evidence edge identities must be text")
        if not self.source.strip() or not self.target.strip() or not self.relation.strip():
            raise ValueError("evidence edge source, target, and relation are required")

    def to_dict(self) -> dict[str, str]:
        """Return the stable edge projection."""
        return {"source": self.source, "target": self.target, "relation": self.relation}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "EvidenceEdge":
        """Parse one persisted edge."""
        if set(payload) != {"source", "target", "relation"}:
            raise ValueError("evidence edge has an incompatible shape")
        return cls(
            source=str(payload["source"]),
            target=str(payload["target"]),
            relation=str(payload["relation"]),
        )


@dataclass(frozen=True)
class SessionEvidenceGraph:
    """Redacted, queryable evidence graph for one recovered session."""

    session_id: str
    session_digest: str
    branch_ids: tuple[str, ...]
    nodes: tuple[EvidenceNode, ...]
    edges: tuple[EvidenceEdge, ...] = ()
    run_id: str | None = None

    def __post_init__(self) -> None:
        """Validate session identity and reject ambiguous duplicate revisions."""
        if not isinstance(self.session_id, str) or not isinstance(self.session_digest, str):
            raise ValueError("evidence graph session identity must be text")
        if not self.session_id.strip() or not self.session_digest.strip():
            raise ValueError("evidence graph session identity is required")
        if len(self.session_digest) != 64 or any(
            char not in "0123456789abcdef" for char in self.session_digest
        ):
            raise ValueError("evidence graph session digest must be lowercase SHA-256")
        if not self.branch_ids or any(not isinstance(branch, str) or not branch.strip() for branch in self.branch_ids):
            raise ValueError("evidence graph requires branch identities")
        if len(set(self.branch_ids)) != len(self.branch_ids):
            raise ValueError("evidence graph branch identities must be unique")
        keys = [node.key for node in self.nodes]
        if len(set(keys)) != len(keys):
            raise ValueError("evidence graph cannot contain duplicate node revisions")
        node_keys = set(keys)
        if any(edge.source not in node_keys or edge.target not in node_keys for edge in self.edges):
            raise ValueError("evidence graph edge refers to an unknown node")

    def to_console_dict(self) -> dict[str, Any]:
        """Return stable ordering and shape for Console rendering."""
        verification = verify_session_evidence_graph(self)
        return {
            "schema_version": "1",
            "session_id": self.session_id,
            "session_digest": self.session_digest,
            "run_id": self.run_id,
            "branches": list(sorted(self.branch_ids)),
            "nodes": [node.to_dict() for node in sorted(self.nodes, key=lambda item: item.key)],
            "edges": [
                edge.to_dict()
                for edge in sorted(self.edges, key=lambda item: (item.source, item.target, item.relation))
            ],
            "verification": verification,
        }

    def to_dict(self) -> dict[str, Any]:
        """Return the persisted graph document."""
        return self.to_console_dict()

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SessionEvidenceGraph":
        """Parse a persisted graph and revalidate every identity and edge."""
        allowed = {
            "schema_version", "session_id", "session_digest", "run_id", "branches",
            "nodes", "edges", "verification",
        }
        unknown = set(payload) - allowed
        if unknown:
            raise ValueError("evidence graph contains unknown fields: " + ", ".join(sorted(unknown)))
        if payload.get("schema_version") != "1":
            raise ValueError("evidence graph schema version is unsupported")
        raw_nodes = payload.get("nodes")
        raw_edges = payload.get("edges")
        if not isinstance(raw_nodes, list) or not isinstance(raw_edges, list):
            raise ValueError("evidence graph nodes and edges must be lists")
        return cls(
            session_id=str(payload.get("session_id") or ""),
            session_digest=str(payload.get("session_digest") or ""),
            branch_ids=_text_tuple(payload.get("branches")),
            run_id=(str(payload["run_id"]) if payload.get("run_id") else None),
            nodes=tuple(
                EvidenceNode.from_dict(_require_mapping(item, "evidence node"))
                for item in raw_nodes
            ),
            edges=tuple(
                EvidenceEdge.from_dict(_require_mapping(item, "evidence edge"))
                for item in raw_edges
            ),
        )


def verify_session_evidence_graph(
    graph: SessionEvidenceGraph,
    *,
    expected_branch_ids: Sequence[str] = (),
    required_node_keys: Sequence[str] = (),
) -> dict[str, Any]:
    """Return a stable, non-throwing qualification result for one graph.

    Malformed graph identities are rejected during graph construction. Missing,
    incompatible, negative, or partial producer evidence remains an explicit
    result so the Console can explain why a claim is not complete.
    """
    expected_branches = {str(item).strip() for item in expected_branch_ids if str(item).strip()}
    node_keys = {node.key for node in graph.nodes}
    required = {str(item).strip() for item in required_node_keys if str(item).strip()}
    missing_required = sorted(required - node_keys)
    branch_ok = expected_branches.issubset(set(graph.branch_ids))
    references_ok = all(node.uri == f"research://postgres/{node.artifact_type}/{node.artifact_id}" for node in graph.nodes)
    edge_ok = all(edge.source in node_keys and edge.target in node_keys for edge in graph.edges)
    statuses = {node.status for node in graph.nodes}
    blockers = list(missing_required)
    for node in sorted(graph.nodes, key=lambda item: item.key):
        blockers.extend(node.blockers)
    if not branch_ok:
        blockers.append("expected branch identity is missing")
    if not references_ok:
        blockers.append("artifact URI identity is unresolved")
    if not edge_ok:
        blockers.append("evidence edge identity is unresolved")
    if not graph.nodes:
        blockers.append("no evidence nodes are retained")
        verdict = "blocked"
    elif statuses & {
        EvidenceStatus.MISSING, EvidenceStatus.INCOMPATIBLE,
        EvidenceStatus.STALE, EvidenceStatus.REDACTED,
    }:
        verdict = "blocked"
    elif statuses & {EvidenceStatus.PARTIAL, EvidenceStatus.NEGATIVE} or blockers:
        verdict = "partial"
    else:
        verdict = "complete"
    return {
        "verdict": verdict,
        "checks": {
            "session_identity": bool(graph.session_id and graph.session_digest),
            "evidence_presence": bool(graph.nodes),
            "branch_coverage": branch_ok,
            "exact_artifact_revisions": len(node_keys) == len(graph.nodes),
            "artifact_identity": references_ok,
            "edge_resolution": edge_ok,
            "required_evidence": not missing_required,
            "redacted_projection": True,
        },
        "missing_node_keys": missing_required,
        "statuses": {status.value: sum(node.status is status for node in graph.nodes) for status in EvidenceStatus},
        "blockers": sorted(set(str(item) for item in blockers if str(item).strip())),
    }


@dataclass
class EvidenceGraphStore:
    """Atomic JSON store used by the deterministic qualification fixture."""

    storage_path: Path | str

    def save(self, graph: SessionEvidenceGraph) -> None:
        """Atomically persist one redacted graph document."""
        path = Path(self.storage_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=path.parent,
                prefix=f".{path.name}.", suffix=".tmp", delete=False,
            ) as temporary:
                temporary.write(json.dumps(graph.to_dict(), sort_keys=True, separators=(",", ":"), allow_nan=False))
                temporary.flush()
                os.fsync(temporary.fileno())
                temporary_path = Path(temporary.name)
            os.replace(temporary_path, path)
        except OSError as exc:
            raise EvidenceGraphUnavailable("evidence graph storage is unavailable") from exc
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink(missing_ok=True)

    def load(self) -> SessionEvidenceGraph:
        """Load and validate one persisted graph document."""
        try:
            payload = json.loads(Path(self.storage_path).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise EvidenceGraphUnavailable("evidence graph storage is unreadable") from exc
        if not isinstance(payload, Mapping):
            raise EvidenceGraphUnavailable("evidence graph storage must contain an object")
        return SessionEvidenceGraph.from_dict(payload)


def _positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"evidence node {label} must be a positive integer")
    return value


def _mapping(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("evidence node claim scope must be an object")
    return value


def _require_mapping(value: Any, label: str) -> Mapping[str, Any]:
    """Require one object while decoding a persisted list."""
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _text_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if not isinstance(value, Sequence):
        raise ValueError("evidence graph text values must be lists")
    return tuple(str(item) for item in value)


def _validate_public_mapping(value: Mapping[str, Any]) -> None:
    """Reject private/raw payload fields at the graph boundary."""
    forbidden = ("prompt", "completion", "raw", "secret", "credential", "scratchpad", "reasoning")
    for key, item in value.items():
        name = str(key).lower()
        if any(part in name for part in forbidden):
            raise ValueError("evidence graph claim scope contains a private field")
        if isinstance(item, Mapping):
            _validate_public_mapping(item)
        elif isinstance(item, Sequence) and not isinstance(item, (str, bytes, bytearray)):
            for nested in item:
                if isinstance(nested, Mapping):
                    _validate_public_mapping(nested)
    try:
        json.dumps(jsonable(value), sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError("evidence graph claim scope must be JSON-native") from exc


def _stable_json(value: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize a public mapping into deterministic JSON key order."""
    result = json.loads(
        json.dumps(jsonable(value), sort_keys=True, separators=(",", ":"), allow_nan=False)
    )
    if not isinstance(result, dict):  # pragma: no cover - mapping input is an object
        raise ValueError("evidence graph claim scope must be an object")
    return result


__all__ = [
    "EvidenceEdge",
    "EvidenceGraphStore",
    "EvidenceGraphUnavailable",
    "EvidenceNode",
    "EvidenceStatus",
    "SessionEvidenceGraph",
    "verify_session_evidence_graph",
]
