"""Knowledge methodology domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping

from .common import (
    KNOWLEDGE_SCHEMA_VERSION,
    METHODOLOGY_CANDIDATE_STATUSES,
    METHODOLOGY_EVIDENCE_PACKET_STATUSES,
    _jsonable,
    _mapping,
    _parse_datetime,
    _sequence,
    _string_tuple,
    _utc_now,
)
from .evidence import EvidenceBackedField
from .fields import (
    METHODOLOGY_CORE_FIELD_SCHEMA,
    METHODOLOGY_EXTENSION_FIELD_SCHEMA,
    _normalize_methodology_field_groups,
    _serialize_methodology_field_groups,
)

@dataclass(frozen=True)
class MethodologyCandidate:
    """Source-backed methodology candidate before method-card approval.

    Candidates describe what an ingested source appears to contain without making
    it executable. They carry candidate spans plus nullable methodology fields so later
    extraction and validation can add evidence-backed structure before a draft
    method card is created.
    """

    methodology_candidate_id: str
    title: str
    families: tuple[str, ...]
    status: str = "discovered"
    source_ids: tuple[str, ...] = tuple()
    chunk_ids: tuple[str, ...] = tuple()
    candidate_spans: tuple[Mapping[str, Any], ...] = tuple()
    method_identity: Mapping[str, Any] = field(default_factory=dict)
    core_fields: Mapping[str, Mapping[str, EvidenceBackedField]] = field(default_factory=dict)
    extension_fields: Mapping[str, Mapping[str, EvidenceBackedField]] = field(default_factory=dict)
    lineage: Mapping[str, Any] = field(default_factory=dict)
    warnings: tuple[str, ...] = tuple()
    blockers: tuple[str, ...] = tuple()
    created_at: datetime = field(default_factory=_utc_now)
    schema_version: str = KNOWLEDGE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.methodology_candidate_id.strip():
            raise ValueError("methodology_candidate_id is required")
        if not self.title.strip():
            raise ValueError("methodology candidate title is required")
        if self.status not in METHODOLOGY_CANDIDATE_STATUSES:
            allowed = ", ".join(sorted(METHODOLOGY_CANDIDATE_STATUSES))
            raise ValueError(f"unsupported methodology candidate status: {self.status}; allowed values: {allowed}")
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

    def to_dict(self) -> dict[str, Any]:
        """Serialize the methodology candidate with candidate spans and methodology fields."""
        return {
            "artifact_type": "methodology_candidate",
            "schema_version": self.schema_version,
            "methodology_candidate_id": self.methodology_candidate_id,
            "title": self.title,
            "families": list(self.families),
            "status": self.status,
            "source_ids": list(self.source_ids),
            "chunk_ids": list(self.chunk_ids),
            "candidate_spans": _jsonable(list(self.candidate_spans)),
            "method_identity": _jsonable(self.method_identity),
            "core_fields": _serialize_methodology_field_groups(self.core_fields),
            "extension_fields": _serialize_methodology_field_groups(self.extension_fields),
            "lineage": _jsonable(self.lineage),
            "warnings": list(self.warnings),
            "blockers": list(self.blockers),
            "created_at": _jsonable(self.created_at),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "MethodologyCandidate":
        """Parse a persisted methodology-candidate payload."""
        return cls(
            methodology_candidate_id=str(payload.get("methodology_candidate_id") or ""),
            title=str(payload.get("title") or ""),
            families=_string_tuple(payload.get("families")),
            status=str(payload.get("status") or "discovered"),
            source_ids=_string_tuple(payload.get("source_ids")),
            chunk_ids=_string_tuple(payload.get("chunk_ids")),
            candidate_spans=tuple(_mapping(item) for item in _sequence(payload.get("candidate_spans"))),
            method_identity=_mapping(payload.get("method_identity")),
            core_fields=_mapping(payload.get("core_fields")),
            extension_fields=_mapping(payload.get("extension_fields")),
            lineage=_mapping(payload.get("lineage")),
            warnings=_string_tuple(payload.get("warnings")),
            blockers=_string_tuple(payload.get("blockers")),
            created_at=_parse_datetime(payload.get("created_at")),
            schema_version=str(payload.get("schema_version") or KNOWLEDGE_SCHEMA_VERSION),
        )


@dataclass(frozen=True)
class MethodologyEvidencePacket:
    """Role-labeled evidence assembled before methodology field extraction.

    The packet is the inspectable bridge between open-world methodology discovery
    and closed-schema extraction. It records which family-level evidence roles
    were found, which roles are missing for the requested readiness goal, and the
    exact source/chunk/hash evidence available to field extractors.
    """

    evidence_packet_id: str
    methodology_candidate_id: str
    family: str
    readiness_goal: str = "descriptive"
    status: str = "assembled"
    candidate_ref: Mapping[str, Any] = field(default_factory=dict)
    source_ids: tuple[str, ...] = tuple()
    chunk_ids: tuple[str, ...] = tuple()
    profile_version: str = "1"
    role_evidence: tuple[Mapping[str, Any], ...] = tuple()
    missing_roles: tuple[str, ...] = tuple()
    diagnostics: Mapping[str, Any] = field(default_factory=dict)
    warnings: tuple[str, ...] = tuple()
    blockers: tuple[str, ...] = tuple()
    created_at: datetime = field(default_factory=_utc_now)
    schema_version: str = KNOWLEDGE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.evidence_packet_id.strip():
            raise ValueError("evidence_packet_id is required")
        if not self.methodology_candidate_id.strip():
            raise ValueError("methodology_candidate_id is required")
        if not self.family.strip():
            raise ValueError("methodology evidence packet family is required")
        if self.status not in METHODOLOGY_EVIDENCE_PACKET_STATUSES:
            allowed = ", ".join(sorted(METHODOLOGY_EVIDENCE_PACKET_STATUSES))
            raise ValueError(f"unsupported evidence packet status: {self.status}; allowed values: {allowed}")

    def to_dict(self) -> dict[str, Any]:
        """Serialize the role-labeled evidence packet for DB-backed persistence."""
        return {
            "artifact_type": "methodology_evidence_packet",
            "schema_version": self.schema_version,
            "evidence_packet_id": self.evidence_packet_id,
            "methodology_candidate_id": self.methodology_candidate_id,
            "family": self.family,
            "readiness_goal": self.readiness_goal,
            "status": self.status,
            "candidate_ref": _jsonable(self.candidate_ref),
            "source_ids": list(self.source_ids),
            "chunk_ids": list(self.chunk_ids),
            "profile_version": self.profile_version,
            "role_evidence": _jsonable(list(self.role_evidence)),
            "missing_roles": list(self.missing_roles),
            "diagnostics": _jsonable(self.diagnostics),
            "warnings": list(self.warnings),
            "blockers": list(self.blockers),
            "created_at": _jsonable(self.created_at),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "MethodologyEvidencePacket":
        """Parse a persisted methodology evidence packet payload."""
        return cls(
            evidence_packet_id=str(payload.get("evidence_packet_id") or ""),
            methodology_candidate_id=str(payload.get("methodology_candidate_id") or ""),
            family=str(payload.get("family") or ""),
            readiness_goal=str(payload.get("readiness_goal") or "descriptive"),
            status=str(payload.get("status") or "assembled"),
            candidate_ref=_mapping(payload.get("candidate_ref")),
            source_ids=_string_tuple(payload.get("source_ids")),
            chunk_ids=_string_tuple(payload.get("chunk_ids")),
            profile_version=str(payload.get("profile_version") or "1"),
            role_evidence=tuple(_mapping(item) for item in _sequence(payload.get("role_evidence"))),
            missing_roles=_string_tuple(payload.get("missing_roles")),
            diagnostics=_mapping(payload.get("diagnostics")),
            warnings=_string_tuple(payload.get("warnings")),
            blockers=_string_tuple(payload.get("blockers")),
            created_at=_parse_datetime(payload.get("created_at")),
            schema_version=str(payload.get("schema_version") or KNOWLEDGE_SCHEMA_VERSION),
        )


@dataclass(frozen=True)
class MethodologyFieldExtractionReport:
    """Audit report for deterministic methodology-field extraction from a candidate."""

    extraction_id: str
    methodology_candidate_id: str
    status: str
    evidence_packet_id: str | None = None
    candidate_ref: Mapping[str, Any] = field(default_factory=dict)
    source_ids: tuple[str, ...] = tuple()
    chunk_ids: tuple[str, ...] = tuple()
    extraction_engine: str = "deterministic_rules"
    populated_field_count: int = 0
    populated_fields: tuple[str, ...] = tuple()
    warnings: tuple[str, ...] = tuple()
    blockers: tuple[str, ...] = tuple()
    created_at: datetime = field(default_factory=_utc_now)
    schema_version: str = KNOWLEDGE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.extraction_id.strip():
            raise ValueError("extraction_id is required")
        if not self.methodology_candidate_id.strip():
            raise ValueError("methodology_candidate_id is required")
        if self.status not in {"extracted", "blocked"}:
            raise ValueError(f"unsupported methodology extraction status: {self.status}")

    def to_dict(self) -> dict[str, Any]:
        """Serialize extraction status and populated-field evidence summary."""
        return {
            "artifact_type": "methodology_field_extraction_report",
            "schema_version": self.schema_version,
            "extraction_id": self.extraction_id,
            "methodology_candidate_id": self.methodology_candidate_id,
            "status": self.status,
            "evidence_packet_id": self.evidence_packet_id,
            "candidate_ref": _jsonable(self.candidate_ref),
            "source_ids": list(self.source_ids),
            "chunk_ids": list(self.chunk_ids),
            "extraction_engine": self.extraction_engine,
            "populated_field_count": self.populated_field_count,
            "populated_fields": list(self.populated_fields),
            "warnings": list(self.warnings),
            "blockers": list(self.blockers),
            "created_at": _jsonable(self.created_at),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "MethodologyFieldExtractionReport":
        """Parse a stored methodology field-extraction report."""
        return cls(
            extraction_id=str(payload.get("extraction_id") or ""),
            methodology_candidate_id=str(payload.get("methodology_candidate_id") or ""),
            status=str(payload.get("status") or ""),
            evidence_packet_id=str(payload["evidence_packet_id"])
            if payload.get("evidence_packet_id") is not None
            else None,
            candidate_ref=_mapping(payload.get("candidate_ref")),
            source_ids=_string_tuple(payload.get("source_ids")),
            chunk_ids=_string_tuple(payload.get("chunk_ids")),
            extraction_engine=str(payload.get("extraction_engine") or "deterministic_rules"),
            populated_field_count=int(payload.get("populated_field_count") or 0),
            populated_fields=_string_tuple(payload.get("populated_fields")),
            warnings=_string_tuple(payload.get("warnings")),
            blockers=_string_tuple(payload.get("blockers")),
            created_at=_parse_datetime(payload.get("created_at")),
            schema_version=str(payload.get("schema_version") or KNOWLEDGE_SCHEMA_VERSION),
        )


@dataclass(frozen=True)
class MethodologyCandidateValidationReport:
    """Validation report for an evidence-backed methodology candidate before card creation."""

    validation_id: str
    methodology_candidate_id: str
    status: str
    valid: bool
    candidate_ref: Mapping[str, Any] = field(default_factory=dict)
    checked_refs: tuple[Mapping[str, Any], ...] = tuple()
    field_summary: Mapping[str, Any] = field(default_factory=dict)
    source_summary: Mapping[str, Any] = field(default_factory=dict)
    readiness_summary: Mapping[str, Any] = field(default_factory=dict)
    warnings: tuple[str, ...] = tuple()
    blockers: tuple[str, ...] = tuple()
    created_at: datetime = field(default_factory=_utc_now)
    schema_version: str = KNOWLEDGE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.validation_id.strip():
            raise ValueError("validation_id is required")
        if not self.methodology_candidate_id.strip():
            raise ValueError("methodology_candidate_id is required")
        if self.status not in {"passed", "blocked"}:
            raise ValueError(f"unsupported methodology validation status: {self.status}")
        if self.valid != (self.status == "passed"):
            raise ValueError("methodology validation valid flag must match status")

    def to_dict(self) -> dict[str, Any]:
        """Serialize validation status, checked refs, warnings, and blockers."""
        return {
            "artifact_type": "methodology_candidate_validation_report",
            "schema_version": self.schema_version,
            "validation_id": self.validation_id,
            "methodology_candidate_id": self.methodology_candidate_id,
            "status": self.status,
            "valid": self.valid,
            "candidate_ref": _jsonable(self.candidate_ref),
            "checked_refs": _jsonable(list(self.checked_refs)),
            "field_summary": _jsonable(self.field_summary),
            "source_summary": _jsonable(self.source_summary),
            "readiness_summary": _jsonable(self.readiness_summary),
            "warnings": list(self.warnings),
            "blockers": list(self.blockers),
            "created_at": _jsonable(self.created_at),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "MethodologyCandidateValidationReport":
        """Parse a stored methodology-candidate validation report."""
        return cls(
            validation_id=str(payload.get("validation_id") or ""),
            methodology_candidate_id=str(payload.get("methodology_candidate_id") or ""),
            status=str(payload.get("status") or ""),
            valid=bool(payload.get("valid")),
            candidate_ref=_mapping(payload.get("candidate_ref")),
            checked_refs=tuple(_mapping(item) for item in _sequence(payload.get("checked_refs"))),
            field_summary=_mapping(payload.get("field_summary")),
            source_summary=_mapping(payload.get("source_summary")),
            readiness_summary=_mapping(payload.get("readiness_summary")),
            warnings=_string_tuple(payload.get("warnings")),
            blockers=_string_tuple(payload.get("blockers")),
            created_at=_parse_datetime(payload.get("created_at")),
            schema_version=str(payload.get("schema_version") or KNOWLEDGE_SCHEMA_VERSION),
        )
