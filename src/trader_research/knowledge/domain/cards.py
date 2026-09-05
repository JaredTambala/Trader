"""Define canonical method-card and revision-set domain models.

Cards bind normalized methodology fields to exact evidence and lifecycle state.
Revision sets provide stable method-level identity while preserving immutable
card versions and current approved or draft pointers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import hashlib
from typing import Any, Mapping

from .common import (
    KNOWLEDGE_SCHEMA_VERSION,
    METHOD_CARD_SET_STATUSES,
    METHOD_CARD_STATUSES,
    _jsonable,
    _mapping,
    _parse_datetime,
    _sequence,
    _slug_text,
    _string_tuple,
    _utc_now,
)
from .evidence import EvidenceBackedField, EvidenceReference
from .fields import (
    METHODOLOGY_CORE_FIELD_SCHEMA,
    METHODOLOGY_EXTENSION_FIELD_SCHEMA,
    _normalize_methodology_field_groups,
    _serialize_methodology_field_groups,
)

def default_method_card_set_id(
    *,
    method_id: str,
    title: str,
    family: str,
    source_fingerprint: str | None = None,
) -> str:
    """Build the stable aggregate ID shared by method-card revisions.

    Normalized method ID, title, family, and optional source fingerprint are
    hashed, while a bounded title-derived slug keeps the identifier readable.
    Equivalent inputs therefore resolve to the same logical revision set.

    Returns:
        An identifier in ``method_card_set_<slug>_<digest>`` form.
    """
    slug = _slug_text(title or method_id or family)[:48] or "method"
    payload = "|".join(
        (
            method_id.strip().lower(),
            title.strip().lower(),
            family.strip().lower(),
            str(source_fingerprint or "").strip().lower(),
        )
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]
    return f"method_card_set_{slug}_{digest}"


@dataclass(frozen=True)
class MethodCardSet:
    """Stable aggregate identity for method-card revisions.

    `method_card_id` names one immutable draft or approved revision. A
    `method_card_set_id` groups those revisions into the logical methodology card
    operators see in pgAdmin and downstream tools.
    """

    method_card_set_id: str
    method_id: str
    family: str
    canonical_title: str
    status: str
    source_fingerprint: str | None = None
    current_approved_method_card_id: str | None = None
    current_draft_method_card_id: str | None = None
    card_ids: tuple[str, ...] = tuple()
    revision_count: int = 0
    latest_revision_number: int = 0
    status_counts: Mapping[str, int] = field(default_factory=dict)
    lineage: Mapping[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utc_now)
    updated_at: datetime = field(default_factory=_utc_now)
    schema_version: str = KNOWLEDGE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.method_card_set_id.strip():
            raise ValueError("method_card_set_id is required")
        if not self.method_id.strip():
            raise ValueError("method_id is required")
        if not self.family.strip():
            raise ValueError("family is required")
        if not self.canonical_title.strip():
            raise ValueError("canonical_title is required")
        if self.status not in METHOD_CARD_SET_STATUSES:
            raise ValueError(f"unsupported method-card set status: {self.status}")
        if self.revision_count < 0:
            raise ValueError("revision_count must be non-negative")
        if self.latest_revision_number < 0:
            raise ValueError("latest_revision_number must be non-negative")

    def to_dict(self) -> dict[str, Any]:
        """Serialize stable method-card-set lineage and lifecycle pointers.

        Aggregate identity, source fingerprint, current approved and draft cards,
        immutable revision IDs, counts, lineage, and timestamps are emitted as a
        JSON-compatible payload.
        """
        return {
            "artifact_type": "method_card_set",
            "schema_version": self.schema_version,
            "method_card_set_id": self.method_card_set_id,
            "method_id": self.method_id,
            "family": self.family,
            "canonical_title": self.canonical_title,
            "status": self.status,
            "source_fingerprint": self.source_fingerprint,
            "current_approved_method_card_id": self.current_approved_method_card_id,
            "current_draft_method_card_id": self.current_draft_method_card_id,
            "card_ids": list(self.card_ids),
            "revision_count": self.revision_count,
            "latest_revision_number": self.latest_revision_number,
            "status_counts": dict(self.status_counts),
            "lineage": _jsonable(self.lineage),
            "created_at": _jsonable(self.created_at),
            "updated_at": _jsonable(self.updated_at),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "MethodCardSet":
        """Parse and validate a stored method-card-set summary.

        IDs, lifecycle pointers, revision counts, status counts, lineage, and
        timestamps are normalized before constructor checks enforce required
        identity, supported status, and non-negative revision metadata.
        """
        return cls(
            method_card_set_id=str(payload.get("method_card_set_id") or ""),
            method_id=str(payload.get("method_id") or ""),
            family=str(payload.get("family") or ""),
            canonical_title=str(payload.get("canonical_title") or payload.get("title") or ""),
            status=str(payload.get("status") or "active"),
            source_fingerprint=str(payload["source_fingerprint"])
            if payload.get("source_fingerprint") is not None
            else None,
            current_approved_method_card_id=str(payload["current_approved_method_card_id"])
            if payload.get("current_approved_method_card_id") is not None
            else None,
            current_draft_method_card_id=str(payload["current_draft_method_card_id"])
            if payload.get("current_draft_method_card_id") is not None
            else None,
            card_ids=_string_tuple(payload.get("card_ids")),
            revision_count=int(payload.get("revision_count") or 0),
            latest_revision_number=int(payload.get("latest_revision_number") or 0),
            status_counts={
                str(key): int(value)
                for key, value in _mapping(payload.get("status_counts")).items()
                if str(key).strip()
            },
            lineage=_mapping(payload.get("lineage")),
            created_at=_parse_datetime(payload.get("created_at")),
            updated_at=_parse_datetime(payload.get("updated_at")),
            schema_version=str(payload.get("schema_version") or KNOWLEDGE_SCHEMA_VERSION),
        )


@dataclass(frozen=True)
class MethodCard:
    """Canonical evidence-backed methodology record."""

    method_card_id: str
    method_id: str
    title: str
    family: str
    status: str
    assumptions: tuple[str, ...]
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    failure_modes: tuple[str, ...]
    evidence_refs: tuple[EvidenceReference, ...] = tuple()
    core_fields: Mapping[str, Mapping[str, EvidenceBackedField]] = field(default_factory=dict)
    extension_fields: Mapping[str, Mapping[str, EvidenceBackedField]] = field(default_factory=dict)
    method_card_set_id: str | None = None
    revision_number: int | None = None
    supersedes_method_card_id: str | None = None
    source_methodology_candidate_id: str | None = None
    validation_refs: tuple[Mapping[str, Any], ...] = tuple()
    lineage: Mapping[str, Any] = field(default_factory=dict)
    version: int = 1
    source_method_card_id: str | None = None
    approved_by: str | None = None
    approval_note: str | None = None
    created_at: datetime = field(default_factory=_utc_now)
    schema_version: str = KNOWLEDGE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.method_card_id.strip():
            raise ValueError("method_card_id is required")
        if not self.method_id.strip():
            raise ValueError("method_id is required")
        if self.status not in METHOD_CARD_STATUSES:
            raise ValueError(f"unsupported method-card status: {self.status}")
        if not str(self.method_card_set_id or "").strip():
            raise ValueError("method_card_set_id is required")
        if self.revision_number is None:
            raise ValueError("revision_number is required")
        if int(self.revision_number or 0) < 1:
            raise ValueError("revision_number must be a positive integer")
        if not str(self.source_methodology_candidate_id or "").strip():
            raise ValueError("source_methodology_candidate_id is required")
        if not self.validation_refs:
            raise ValueError("validation_refs are required")
        if not self.evidence_refs:
            raise ValueError("evidence_refs are required")
        object.__setattr__(
            self,
            "core_fields",
            _normalize_methodology_field_groups(
                self.core_fields,
                schema=METHODOLOGY_CORE_FIELD_SCHEMA,
                scope="core_fields",
            ),
        )
        object.__setattr__(
            self,
            "extension_fields",
            _normalize_methodology_field_groups(
                self.extension_fields,
                schema=METHODOLOGY_EXTENSION_FIELD_SCHEMA,
                scope="extension_fields",
            ),
        )

    @property
    def approved(self) -> bool:
        """Return whether this card is approved for implementation evidence citations."""
        return self.status == "approved"

    def to_summary(self) -> "MethodCardSummary":
        """Derive the compact read model used by method-card search.

        The summary retains identity, lifecycle, family, title, revision-set
        linkage, assumptions, failure modes, and creation time while omitting
        complete field-level evidence and implementation detail.
        """
        return MethodCardSummary(
            method_card_id=self.method_card_id,
            method_id=self.method_id,
            title=self.title,
            family=self.family,
            status=self.status,
            assumptions=self.assumptions,
            inputs=self.inputs,
            outputs=self.outputs,
            failure_modes=self.failure_modes,
            evidence_refs=self.evidence_refs,
            method_card_set_id=self.method_card_set_id,
            revision_number=self.revision_number,
            supersedes_method_card_id=self.supersedes_method_card_id,
            version=self.version,
            source_method_card_id=self.source_method_card_id,
            approved_by=self.approved_by,
            approval_note=self.approval_note,
            created_at=self.created_at,
            schema_version=self.schema_version,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize the complete canonical method-card revision.

        Identity, lifecycle, aggregate linkage, source-backed core and extension
        fields, assumptions, failure modes, evidence references, provenance, and
        timestamps are emitted without dropping explicit null field values.
        """
        return {
            "artifact_type": "method_card_draft" if self.status == "draft" else "method_card",
            "schema_version": self.schema_version,
            "method_card_id": self.method_card_id,
            "method_id": self.method_id,
            "title": self.title,
            "family": self.family,
            "status": self.status,
            "version": self.version,
            "method_card_set_id": self.method_card_set_id,
            "revision_number": self.revision_number,
            "supersedes_method_card_id": self.supersedes_method_card_id,
            "assumptions": list(self.assumptions),
            "inputs": list(self.inputs),
            "outputs": list(self.outputs),
            "failure_modes": list(self.failure_modes),
            "evidence_refs": [ref.to_dict() for ref in self.evidence_refs],
            "core_fields": _serialize_methodology_field_groups(self.core_fields),
            "extension_fields": _serialize_methodology_field_groups(self.extension_fields),
            "source_methodology_candidate_id": self.source_methodology_candidate_id,
            "validation_refs": _jsonable(list(self.validation_refs)),
            "lineage": _jsonable(self.lineage),
            "source_method_card_id": self.source_method_card_id,
            "approved_by": self.approved_by,
            "approval_note": self.approval_note,
            "created_at": _jsonable(self.created_at),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "MethodCard":
        """Parse and validate a canonical card with field-level evidence.

        Core and extension field groups, exact evidence refs, lifecycle metadata,
        assumptions, failure modes, provenance, aggregate linkage, and timestamps
        are normalized. Constructor validation preserves required identity and
        supported lifecycle rules.
        """
        return cls(
            method_card_id=str(payload.get("method_card_id") or ""),
            method_id=str(payload.get("method_id") or ""),
            title=str(payload.get("title") or ""),
            family=str(payload.get("family") or ""),
            status=str(payload.get("status") or "planned"),
            assumptions=_string_tuple(payload.get("assumptions")),
            inputs=_string_tuple(payload.get("inputs")),
            outputs=_string_tuple(payload.get("outputs")),
            failure_modes=_string_tuple(payload.get("failure_modes")),
            evidence_refs=tuple(
                EvidenceReference.from_dict(_mapping(item))
                for item in _sequence(payload.get("evidence_refs"))
            ),
            core_fields=_mapping(payload.get("core_fields")),
            extension_fields=_mapping(payload.get("extension_fields")),
            method_card_set_id=str(payload["method_card_set_id"])
            if payload.get("method_card_set_id") is not None
            else None,
            revision_number=int(payload["revision_number"]) if payload.get("revision_number") is not None else None,
            supersedes_method_card_id=str(payload["supersedes_method_card_id"])
            if payload.get("supersedes_method_card_id") is not None
            else None,
            source_methodology_candidate_id=str(payload["source_methodology_candidate_id"])
            if payload.get("source_methodology_candidate_id") is not None
            else None,
            validation_refs=tuple(_mapping(item) for item in _sequence(payload.get("validation_refs"))),
            lineage=_mapping(payload.get("lineage")),
            version=int(payload.get("version") or 1),
            source_method_card_id=str(payload["source_method_card_id"])
            if payload.get("source_method_card_id") is not None
            else None,
            approved_by=str(payload["approved_by"]) if payload.get("approved_by") is not None else None,
            approval_note=str(payload["approval_note"]) if payload.get("approval_note") is not None else None,
            created_at=_parse_datetime(payload.get("created_at")),
            schema_version=str(payload.get("schema_version") or KNOWLEDGE_SCHEMA_VERSION),
        )


@dataclass(frozen=True)
class MethodCardSummary:
    """Derived, non-writable read model for searching canonical method cards."""

    method_card_id: str
    method_id: str
    title: str
    family: str
    status: str
    assumptions: tuple[str, ...]
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    failure_modes: tuple[str, ...]
    evidence_refs: tuple[EvidenceReference, ...] = tuple()
    method_card_set_id: str | None = None
    revision_number: int | None = None
    supersedes_method_card_id: str | None = None
    version: int = 1
    source_method_card_id: str | None = None
    approved_by: str | None = None
    approval_note: str | None = None
    created_at: datetime = field(default_factory=_utc_now)
    schema_version: str = KNOWLEDGE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.method_card_id.strip():
            raise ValueError("method_card_id is required")
        if not self.method_id.strip():
            raise ValueError("method_id is required")
        if self.status not in METHOD_CARD_STATUSES:
            raise ValueError(f"unsupported method-card status: {self.status}")
        if not str(self.method_card_set_id or "").strip():
            raise ValueError("method_card_set_id is required")
        if self.revision_number is None:
            raise ValueError("revision_number is required")
        if int(self.revision_number or 0) < 1:
            raise ValueError("revision_number must be a positive integer")

    @property
    def approved(self) -> bool:
        """Return whether this method card is approved for implementation evidence citations."""
        return self.status == "approved"

    def to_dict(self) -> dict[str, Any]:
        """Serialize the compact method-card search projection.

        The payload contains only identity, title, family, version, status,
        revision-set linkage, assumptions, failure modes, evidence count, and
        creation time; complete card fields and citation text remain excluded.
        """
        return {
            "read_model": "method_card_summary",
            "schema_version": self.schema_version,
            "method_card_id": self.method_card_id,
            "method_id": self.method_id,
            "title": self.title,
            "family": self.family,
            "status": self.status,
            "version": self.version,
            "method_card_set_id": self.method_card_set_id,
            "revision_number": self.revision_number,
            "supersedes_method_card_id": self.supersedes_method_card_id,
            "assumptions": list(self.assumptions),
            "inputs": list(self.inputs),
            "outputs": list(self.outputs),
            "failure_modes": list(self.failure_modes),
            "evidence_refs": [ref.to_dict() for ref in self.evidence_refs],
            "source_method_card_id": self.source_method_card_id,
            "approved_by": self.approved_by,
            "approval_note": self.approval_note,
            "created_at": _jsonable(self.created_at),
        }
