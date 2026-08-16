"""DB-first research artifact persistence boundary.

The MCP research toolchain stores reproducible evidence as structured records.
Filesystem exports are not the canonical artifact store.
"""

from __future__ import annotations

from collections.abc import Mapping as MappingABC
from dataclasses import dataclass, field
from datetime import datetime, timezone
import math
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence
from urllib.parse import urlparse

from .domain import ArtifactReference, SCHEMA_VERSION, SUPPORTED_DOMAIN_OWNERS


RESEARCH_ARTIFACT_URI_SCHEME = "research"
RESEARCH_ARTIFACT_URI_BACKEND = "postgres"


class ResearchArtifactStoreError(RuntimeError):
    """Raised when research artifact persistence or resolution fails."""


class ResearchArtifactNotFound(ResearchArtifactStoreError):
    """Raised when a requested research artifact is not present in the store."""


@dataclass(frozen=True)
class ResearchArtifactRecord:
    """A persisted research artifact payload plus query metadata."""

    artifact_type: str
    artifact_id: str
    payload: Mapping[str, Any]
    domain_owner: str
    producer_tool: str
    requested_by: str | None = None
    actor: str | None = None
    status: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    source_hash: str | None = None
    schema_version: str = SCHEMA_VERSION
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def uri(self) -> str:
        """Return the canonical URI for this artifact."""
        return research_artifact_uri(self.artifact_type, self.artifact_id)

    def reference(self) -> ArtifactReference:
        """Build the bounded canonical reference for this artifact record.

        The reference includes type, canonical URI, status, hash, ownership,
        producer, request attribution, and normalized metadata. It excludes the
        complete artifact payload and store-specific connection details.
        """
        return ArtifactReference(
            artifact_type=self.artifact_type,
            uri=self.uri,
            metadata={
                "id": self.artifact_id,
                "status": self.status,
                "source_hash": self.source_hash,
                "domain_owner": self.domain_owner,
                "producer_tool": self.producer_tool,
                "requested_by": self.requested_by,
                "actor": self.actor,
                **dict(self.metadata),
            },
        )


class ResearchArtifactStore(Protocol):
    """Persistence protocol used by DB-backed research services."""

    backend: str

    def runtime_summary(self) -> Mapping[str, Any]:
        """Return non-secret store runtime metadata."""

    def save_artifact(
        self,
        *,
        artifact_type: str,
        artifact_id: str,
        domain_owner: str,
        producer_tool: str,
        payload: Mapping[str, Any],
        requested_by: str | None = None,
        actor: str | None = None,
        status: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        source_hash: str | None = None,
    ) -> ResearchArtifactRecord:
        """Persist one canonical artifact through the configured store.

        Implementations normalize identity, governance metadata, payload, and
        source hash before writing and return the complete stored record. Failures
        use the typed research artifact store exception hierarchy.
        """

    def load_artifact(self, artifact_type: str, artifact_id: str) -> Mapping[str, Any]:
        """Load one artifact payload by type and ID."""

    def load_artifact_record(self, artifact_type: str, artifact_id: str) -> ResearchArtifactRecord:
        """Load one full artifact record by type and ID."""

    def list_artifacts(
        self,
        *,
        artifact_type: str | None = None,
        artifact_ids: Sequence[str] | None = None,
    ) -> tuple[ResearchArtifactRecord, ...]:
        """List artifact records for diagnostics and tests."""

    def close(self) -> None:
        """Release store resources."""


class ContextualResearchArtifactStore:
    """Store view that applies one workflow requester and actor to all writes."""

    def __init__(
        self,
        store: ResearchArtifactStore,
        *,
        requested_by: str,
        actor: str,
    ) -> None:
        self._store = store
        self.backend = store.backend
        self.requested_by = _required_context_text(
            requested_by,
            "requested_by",
        )
        self.actor = _required_context_text(actor, "actor")

    def runtime_summary(self) -> Mapping[str, Any]:
        """Return the wrapped store's non-secret runtime summary."""
        return self._store.runtime_summary()

    def save_artifact(
        self,
        *,
        artifact_type: str,
        artifact_id: str,
        domain_owner: str,
        producer_tool: str,
        payload: Mapping[str, Any],
        requested_by: str | None = None,
        actor: str | None = None,
        status: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        source_hash: str | None = None,
    ) -> ResearchArtifactRecord:
        """Persist an artifact with fixed requester and actor attribution.

        Caller overrides must be absent or exactly match the contextual values.
        The wrapper then delegates the write with its requester and actor, while
        leaving artifact ownership and producer selection unchanged.
        """
        _validate_context_override(
            requested_by,
            self.requested_by,
            "requested_by",
        )
        _validate_context_override(actor, self.actor, "actor")
        return self._store.save_artifact(
            artifact_type=artifact_type,
            artifact_id=artifact_id,
            domain_owner=domain_owner,
            producer_tool=producer_tool,
            payload=payload,
            requested_by=self.requested_by,
            actor=self.actor,
            status=status,
            metadata=metadata,
            source_hash=source_hash,
        )

    def load_artifact(
        self,
        artifact_type: str,
        artifact_id: str,
    ) -> Mapping[str, Any]:
        """Load one artifact through the wrapped store."""
        return self._store.load_artifact(artifact_type, artifact_id)

    def load_artifact_record(
        self,
        artifact_type: str,
        artifact_id: str,
    ) -> ResearchArtifactRecord:
        """Load one artifact record through the wrapped store."""
        return self._store.load_artifact_record(artifact_type, artifact_id)

    def list_artifacts(
        self,
        *,
        artifact_type: str | None = None,
        artifact_ids: Sequence[str] | None = None,
    ) -> tuple[ResearchArtifactRecord, ...]:
        """List artifacts through the wrapped store."""
        return self._store.list_artifacts(
            artifact_type=artifact_type,
            artifact_ids=artifact_ids,
        )

    def close(self) -> None:
        """Leave lifecycle ownership with the wrapped store provider."""


class InMemoryResearchArtifactStore:
    """Deterministic in-memory artifact store for direct service tests."""

    backend = "memory"

    def __init__(self) -> None:
        self._records: dict[tuple[str, str], ResearchArtifactRecord] = {}

    def runtime_summary(self) -> Mapping[str, Any]:
        """Return non-secret store runtime metadata."""
        return {"backend": self.backend, "configured": True}

    def save_artifact(
        self,
        *,
        artifact_type: str,
        artifact_id: str,
        domain_owner: str,
        producer_tool: str,
        payload: Mapping[str, Any],
        requested_by: str | None = None,
        actor: str | None = None,
        status: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        source_hash: str | None = None,
    ) -> ResearchArtifactRecord:
        """Normalize and store one artifact in process memory.

        Records are keyed by artifact type and ID; saving the same key replaces
        the prior in-memory value. This lightweight adapter is intended for direct
        deterministic service tests and provides no durable transaction boundary.
        """
        record = build_artifact_record(
            artifact_type=artifact_type,
            artifact_id=artifact_id,
            domain_owner=domain_owner,
            producer_tool=producer_tool,
            payload=payload,
            requested_by=requested_by,
            actor=actor,
            status=status,
            metadata=metadata,
            source_hash=source_hash,
        )
        self._records[(record.artifact_type, record.artifact_id)] = record
        return record

    def load_artifact(self, artifact_type: str, artifact_id: str) -> Mapping[str, Any]:
        """Load one artifact payload by type and ID."""
        return self.load_artifact_record(artifact_type, artifact_id).payload

    def load_artifact_record(self, artifact_type: str, artifact_id: str) -> ResearchArtifactRecord:
        """Load one full artifact record by type and ID."""
        try:
            return self._records[(artifact_type, artifact_id)]
        except KeyError as exc:
            raise ResearchArtifactNotFound(f"unknown research artifact: {artifact_type}/{artifact_id}") from exc

    def list_artifacts(
        self,
        *,
        artifact_type: str | None = None,
        artifact_ids: Sequence[str] | None = None,
    ) -> tuple[ResearchArtifactRecord, ...]:
        """List in-memory records after applying optional identity filters.

        Artifact type and ID filters are applied before results are sorted by type
        and ID. The returned tuple therefore does not depend on write order.
        """
        id_filter = set(artifact_ids or ())
        records = [
            record
            for record in self._records.values()
            if (artifact_type is None or record.artifact_type == artifact_type)
            and (not id_filter or record.artifact_id in id_filter)
        ]
        return tuple(sorted(records, key=lambda item: (item.artifact_type, item.artifact_id)))

    def close(self) -> None:
        """Release store resources."""


class UnavailableResearchArtifactStore:
    """Store implementation that fails closed for mutating research tools."""

    backend = "unavailable"

    def __init__(self, reason: str) -> None:
        self.reason = reason

    def runtime_summary(self) -> Mapping[str, Any]:
        """Return non-secret store runtime metadata."""
        return {"backend": self.backend, "configured": False, "reason": self.reason}

    def save_artifact(self, **_: Any) -> ResearchArtifactRecord:
        """Fail because persistence is unavailable."""
        raise ResearchArtifactStoreError(self.reason)

    def load_artifact(self, artifact_type: str, artifact_id: str) -> Mapping[str, Any]:
        """Fail because persistence is unavailable."""
        del artifact_type, artifact_id
        raise ResearchArtifactStoreError(self.reason)

    def load_artifact_record(self, artifact_type: str, artifact_id: str) -> ResearchArtifactRecord:
        """Fail because persistence is unavailable."""
        del artifact_type, artifact_id
        raise ResearchArtifactStoreError(self.reason)

    def list_artifacts(
        self,
        *,
        artifact_type: str | None = None,
        artifact_ids: Sequence[str] | None = None,
    ) -> tuple[ResearchArtifactRecord, ...]:
        """Fail because persistence is unavailable."""
        del artifact_type, artifact_ids
        raise ResearchArtifactStoreError(self.reason)

    def close(self) -> None:
        """Release store resources."""


def build_artifact_record(
    *,
    artifact_type: str,
    artifact_id: str,
    domain_owner: str,
    producer_tool: str,
    payload: Mapping[str, Any],
    requested_by: str | None = None,
    actor: str | None = None,
    status: str | None = None,
    metadata: Mapping[str, Any] | None = None,
    source_hash: str | None = None,
) -> ResearchArtifactRecord:
    """Normalize and validate a canonical research artifact record.

    Artifact type, ID, domain owner, producer, workflow attribution, status,
    metadata, and payload are converted to stable plain-data values. The supplied
    or computed source hash must match the normalized payload, and governance
    ownership and attribution requirements are enforced before construction.

    Returns:
        An immutable record ready for a concrete store to persist.

    Raises:
        ResearchArtifactStoreError: If identity, ownership, attribution, payload,
            metadata, or source hash violates the artifact contract.
    """
    artifact_type = str(artifact_type or "").strip()
    if not artifact_type:
        raise ResearchArtifactStoreError("research artifact_type is required")
    artifact_id = str(artifact_id or "").strip()
    if not artifact_id:
        raise ResearchArtifactStoreError("research artifact_id is required")
    domain_owner = str(domain_owner or "").strip()
    if not domain_owner:
        raise ResearchArtifactStoreError("research artifact domain_owner is required")
    if domain_owner not in SUPPORTED_DOMAIN_OWNERS:
        raise ResearchArtifactStoreError(
            f"unsupported research artifact domain_owner: {domain_owner}"
        )
    producer_tool = str(producer_tool or "").strip()
    if not producer_tool:
        raise ResearchArtifactStoreError("research artifact producer_tool is required")
    requested_by = _optional_text(requested_by)
    actor = _optional_text(actor)
    if not isinstance(payload, MappingABC):
        raise ResearchArtifactStoreError("research artifact payload must be a mapping")
    return ResearchArtifactRecord(
        artifact_type=artifact_type,
        artifact_id=artifact_id,
        payload=_json_safe_mapping(payload),
        domain_owner=domain_owner,
        producer_tool=producer_tool,
        requested_by=requested_by,
        actor=actor,
        status=status,
        metadata=_json_safe_mapping(metadata or {}),
        source_hash=source_hash,
        schema_version=str(payload.get("schema_version") or SCHEMA_VERSION),
    )


def research_artifact_uri(artifact_type: str, artifact_id: str) -> str:
    """Build the canonical Postgres research URI for an artifact identity.

    The function performs no storage lookup; callers must supply already validated
    type and ID components.
    """
    return f"{RESEARCH_ARTIFACT_URI_SCHEME}://{RESEARCH_ARTIFACT_URI_BACKEND}/{artifact_type}/{artifact_id}"


def parse_research_artifact_uri(uri: str) -> tuple[str, str]:
    """Parse and validate a canonical Postgres research-artifact URI.

    Scheme, backend, and exactly two non-empty path components are required.
    Unsupported or malformed values raise ``ResearchArtifactStoreError``.
    """
    parsed = urlparse(str(uri))
    if parsed.scheme != RESEARCH_ARTIFACT_URI_SCHEME or parsed.netloc != RESEARCH_ARTIFACT_URI_BACKEND:
        raise ResearchArtifactStoreError(f"unsupported research artifact URI: {uri}")
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) != 2:
        raise ResearchArtifactStoreError(f"invalid research artifact URI: {uri}")
    return parts[0], parts[1]


def load_artifact_ref(store: ResearchArtifactStore, artifact_type: str, artifact_id_or_uri: str) -> Mapping[str, Any]:
    """Load an artifact by exact ID or canonical URI.

    URI references are parsed and required to match ``artifact_type`` before the
    store read. Blank values and type mismatches raise typed store errors rather
    than falling back to another artifact kind.
    """
    value = str(artifact_id_or_uri or "").strip()
    if not value:
        raise ResearchArtifactStoreError("artifact ID or URI is required")
    if value.startswith(f"{RESEARCH_ARTIFACT_URI_SCHEME}://"):
        parsed_type, parsed_id = parse_research_artifact_uri(value)
        if parsed_type != artifact_type:
            raise ResearchArtifactStoreError(
                f"artifact URI type {parsed_type} does not match expected {artifact_type}"
            )
        return store.load_artifact(parsed_type, parsed_id)
    return store.load_artifact(artifact_type, value)


def _json_safe_mapping(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {str(key): _json_safe(value) for key, value in payload.items()}


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _required_context_text(value: str, label: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ResearchArtifactStoreError(f"research artifact context {label} is required")
    return normalized


def _validate_context_override(
    value: str | None,
    expected: str,
    label: str,
) -> None:
    normalized = _optional_text(value)
    if normalized is not None and normalized != expected:
        raise ResearchArtifactStoreError(
            f"research artifact {label} conflicts with the active workflow context"
        )


def _json_safe(value: Any) -> Any:
    if isinstance(value, MappingABC):
        return _json_safe_mapping(value)
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    return value
