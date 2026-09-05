"""Define registered source, extracted document, and chunk domain models.

Values preserve approval status, content identity, locators, and generation
lineage from registration through indexing. Construction normalizes external
metadata before it reaches retrieval or methodology services.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from .common import (
    DEFAULT_SOURCE_TYPE,
    KNOWLEDGE_EVIDENCE_UNIT_ARTIFACT_TYPE,
    KNOWLEDGE_SCHEMA_VERSION,
    SOURCE_TYPE_LABELS,
    SUPPORTED_SOURCE_EXTENSIONS,
    _jsonable,
    _mapping,
    _parse_datetime,
    _string_tuple,
    _utc_now,
)

@dataclass(frozen=True)
class KnowledgeSourceManifest:
    """Persisted registration record for a curated knowledge source file.

    The manifest captures file identity, source classification, optional topic and
    method-family tags, duplicate detection results, and registration warnings.
    Validation keeps source IDs, titles, supported file extensions, and allowed
    source types consistent before the document is chunked or cited by method
    cards.
    """

    source_id: str
    title: str
    source_type: str
    path: str
    file_hash: str
    file_size_bytes: int
    access_policy: str = "local_curated"
    topics: tuple[str, ...] = tuple()
    method_families: tuple[str, ...] = tuple()
    canonical_citation: str | None = None
    status: str = "registered"
    duplicate_source_ids: tuple[str, ...] = tuple()
    warnings: tuple[str, ...] = tuple()
    created_at: datetime = field(default_factory=_utc_now)
    schema_version: str = KNOWLEDGE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.source_id.strip():
            raise ValueError("source_id is required")
        if not self.title.strip():
            raise ValueError("source title is required")
        if self.source_type not in SOURCE_TYPE_LABELS:
            allowed = ", ".join(sorted(SOURCE_TYPE_LABELS))
            raise ValueError(f"unsupported source_type: {self.source_type}; allowed values: {allowed}")
        if Path(self.path).suffix.lower() not in SUPPORTED_SOURCE_EXTENSIONS:
            raise ValueError(f"unsupported source file type: {Path(self.path).suffix}")
        if not self.file_hash.strip():
            raise ValueError("file_hash is required")

    def to_dict(self) -> dict[str, Any]:
        """Serialize source metadata into the persisted manifest artifact shape.

        Datetimes are converted to JSON-safe values, tuple fields become lists, and
        duplicate/warning metadata is preserved for source registration review.
        """
        return {
            "artifact_type": "knowledge_source_manifest",
            "schema_version": self.schema_version,
            "source_id": self.source_id,
            "title": self.title,
            "source_type": self.source_type,
            "path": self.path,
            "file_hash": self.file_hash,
            "file_size_bytes": self.file_size_bytes,
            "access_policy": self.access_policy,
            "topics": list(self.topics),
            "method_families": list(self.method_families),
            "canonical_citation": self.canonical_citation,
            "status": self.status,
            "duplicate_source_ids": list(self.duplicate_source_ids),
            "warnings": list(self.warnings),
            "created_at": _jsonable(self.created_at),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "KnowledgeSourceManifest":
        """Parse a persisted source manifest while applying defaults for legacy fields.

        Optional tuples, citation text, timestamps, access policy, and schema
        version are normalized before dataclass validation enforces required
        source identity and file metadata.
        """
        return cls(
            source_id=str(payload.get("source_id") or ""),
            title=str(payload.get("title") or ""),
            source_type=str(payload.get("source_type") or DEFAULT_SOURCE_TYPE),
            path=str(payload.get("path") or ""),
            file_hash=str(payload.get("file_hash") or ""),
            file_size_bytes=int(payload.get("file_size_bytes") or 0),
            access_policy=str(payload.get("access_policy") or "local_curated"),
            topics=_string_tuple(payload.get("topics")),
            method_families=_string_tuple(payload.get("method_families")),
            canonical_citation=str(payload["canonical_citation"])
            if payload.get("canonical_citation") is not None
            else None,
            status=str(payload.get("status") or "registered"),
            duplicate_source_ids=_string_tuple(payload.get("duplicate_source_ids")),
            warnings=_string_tuple(payload.get("warnings")),
            created_at=_parse_datetime(payload.get("created_at")),
            schema_version=str(payload.get("schema_version") or KNOWLEDGE_SCHEMA_VERSION),
        )


@dataclass(frozen=True)
class KnowledgeChunk:
    """Citeable evidence unit stored in the knowledge index.

    The public retrieval APIs still use `chunk_id` as the request field, but the
    stored object is a schema-v2 evidence unit. It is intentionally smaller than
    the earlier broad chunks and carries local ordering, section, label, and
    neighbor metadata so methodology discovery can bind claims to one method
    rather than a mixed source span.
    """

    chunk_id: str
    source_id: str
    ordinal: int
    text: str
    text_hash: str
    locator: Mapping[str, Any]
    topics: tuple[str, ...] = tuple()
    method_families: tuple[str, ...] = tuple()
    parent_section_id: str | None = None
    paragraph_index: int | None = None
    sentence_start_index: int | None = None
    sentence_end_index: int | None = None
    detected_labels: tuple[str, ...] = tuple()
    neighbor_chunk_ids: tuple[str, ...] = tuple()
    chunker_version: str = "evidence-unit-v1"
    schema_version: str = KNOWLEDGE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.chunk_id.strip():
            raise ValueError("evidence unit chunk_id is required")
        if not self.source_id.strip():
            raise ValueError("source_id is required")
        if not self.text.strip():
            raise ValueError("evidence unit text is required")
        if not self.text_hash.strip():
            raise ValueError("evidence unit text_hash is required")
        if not self.locator:
            raise ValueError("evidence unit locator is required")
        if self.schema_version != KNOWLEDGE_SCHEMA_VERSION:
            raise ValueError(f"unsupported knowledge evidence unit schema_version: {self.schema_version}")
        if not self.chunker_version.strip():
            raise ValueError("chunker_version is required")

    @property
    def evidence_unit_id(self) -> str:
        """Return the canonical schema-v2 evidence-unit identifier."""
        return self.chunk_id

    def to_dict(self) -> dict[str, Any]:
        """Serialize a citeable evidence unit with locator and binding metadata.

        Locator metadata is normalized through `_jsonable`, while tuple fields are
        emitted as lists so the unit can be stored in JSON or Postgres payloads.
        """
        return {
            "artifact_type": KNOWLEDGE_EVIDENCE_UNIT_ARTIFACT_TYPE,
            "schema_version": self.schema_version,
            "evidence_unit_id": self.evidence_unit_id,
            "chunk_id": self.chunk_id,
            "source_id": self.source_id,
            "ordinal": self.ordinal,
            "text": self.text,
            "text_hash": self.text_hash,
            "locator": _jsonable(self.locator),
            "topics": list(self.topics),
            "method_families": list(self.method_families),
            "parent_section_id": self.parent_section_id,
            "paragraph_index": self.paragraph_index,
            "sentence_start_index": self.sentence_start_index,
            "sentence_end_index": self.sentence_end_index,
            "detected_labels": list(self.detected_labels),
            "neighbor_chunk_ids": list(self.neighbor_chunk_ids),
            "chunker_version": self.chunker_version,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "KnowledgeChunk":
        """Parse a schema-v2 evidence-unit payload into a validated domain object.

        Missing optional topics and method families become empty tuples, while
        required source, text, hash, ordinal, locator, and schema fields are
        validated by the dataclass constructor. Legacy chunk payloads without the
        schema-v2 marker fail closed and must be regenerated by reingesting the
        source.
        """
        schema_version = str(payload.get("schema_version") or "")
        artifact_type = str(payload.get("artifact_type") or "")
        if schema_version != KNOWLEDGE_SCHEMA_VERSION or artifact_type != KNOWLEDGE_EVIDENCE_UNIT_ARTIFACT_TYPE:
            raise ValueError("knowledge evidence unit must be regenerated with schema_version 2")
        return cls(
            chunk_id=str(payload.get("evidence_unit_id") or payload.get("chunk_id") or ""),
            source_id=str(payload.get("source_id") or ""),
            ordinal=int(payload.get("ordinal") or 0),
            text=str(payload.get("text") or ""),
            text_hash=str(payload.get("text_hash") or ""),
            locator=_mapping(payload.get("locator")),
            topics=_string_tuple(payload.get("topics")),
            method_families=_string_tuple(payload.get("method_families")),
            parent_section_id=str(payload["parent_section_id"]) if payload.get("parent_section_id") is not None else None,
            paragraph_index=int(payload["paragraph_index"]) if payload.get("paragraph_index") is not None else None,
            sentence_start_index=int(payload["sentence_start_index"])
            if payload.get("sentence_start_index") is not None
            else None,
            sentence_end_index=int(payload["sentence_end_index"])
            if payload.get("sentence_end_index") is not None
            else None,
            detected_labels=_string_tuple(payload.get("detected_labels")),
            neighbor_chunk_ids=_string_tuple(payload.get("neighbor_chunk_ids")),
            chunker_version=str(payload.get("chunker_version") or "evidence-unit-v1"),
            schema_version=schema_version,
        )


@dataclass(frozen=True)
class KnowledgeEmbeddingManifest:
    """Runtime embedding metadata for chunks indexed in one ingestion run.

    The manifest records provider, model, version, vector dimension, and chunk IDs
    so future retrieval can detect incompatible embeddings and reviewers can audit
    which backend produced the indexed vectors. It intentionally excludes API keys
    and request payloads.
    """

    embedding_manifest_id: str
    provider: str
    model: str
    version: str
    dimension: int
    chunk_ids: tuple[str, ...]
    created_at: datetime = field(default_factory=_utc_now)
    schema_version: str = KNOWLEDGE_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        """Serialize embedding runtime metadata without including vector payloads.

        The manifest stores provider, model, version, dimension, chunk IDs, and
        creation time so retrieval can audit vector compatibility later.
        """
        return {
            "artifact_type": "knowledge_embedding_manifest",
            "schema_version": self.schema_version,
            "embedding_manifest_id": self.embedding_manifest_id,
            "provider": self.provider,
            "model": self.model,
            "version": self.version,
            "dimension": self.dimension,
            "chunk_ids": list(self.chunk_ids),
            "created_at": _jsonable(self.created_at),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "KnowledgeEmbeddingManifest":
        """Parse a stored embedding manifest and normalize timestamps and chunk IDs."""
        return cls(
            embedding_manifest_id=str(payload.get("embedding_manifest_id") or ""),
            provider=str(payload.get("provider") or ""),
            model=str(payload.get("model") or ""),
            version=str(payload.get("version") or ""),
            dimension=int(payload.get("dimension") or 0),
            chunk_ids=_string_tuple(payload.get("chunk_ids")),
            created_at=_parse_datetime(payload.get("created_at")),
            schema_version=str(payload.get("schema_version") or KNOWLEDGE_SCHEMA_VERSION),
        )


@dataclass(frozen=True)
class KnowledgeIngestionReport:
    """Summary artifact produced after extraction, chunking, and indexing.

    The report records which sources were processed, how many chunks were created
    and indexed, the embedding manifest generated for the run, and any warnings or
    blockers. It is the durable handoff that tells downstream agents whether a
    source is citeable or why ingestion could not make it available.
    """

    ingestion_id: str
    source_ids: tuple[str, ...]
    status: str
    chunks_created: int
    chunks_indexed: int
    embedding_manifest_id: str | None = None
    warnings: tuple[str, ...] = tuple()
    blockers: tuple[str, ...] = tuple()
    created_at: datetime = field(default_factory=_utc_now)
    schema_version: str = KNOWLEDGE_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        """Serialize ingestion status, counts, warnings, blockers, and schema metadata.

        The payload is the durable report used by tools to explain whether sources
        were indexed, partially reused, or blocked during extraction or embedding.
        """
        return {
            "artifact_type": "knowledge_ingestion_report",
            "schema_version": self.schema_version,
            "ingestion_id": self.ingestion_id,
            "source_ids": list(self.source_ids),
            "status": self.status,
            "chunks_created": self.chunks_created,
            "chunks_indexed": self.chunks_indexed,
            "evidence_units_created": self.chunks_created,
            "evidence_units_indexed": self.chunks_indexed,
            "embedding_manifest_id": self.embedding_manifest_id,
            "warnings": list(self.warnings),
            "blockers": list(self.blockers),
            "created_at": _jsonable(self.created_at),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "KnowledgeIngestionReport":
        """Parse and validate a stored knowledge-ingestion report.

        Source and run identity, status, generation, chunk and embedding counts,
        optional artifacts, warnings, blockers, and timestamps are normalized.
        Constructor rules reject inconsistent counts or unsupported lifecycle state.
        """
        return cls(
            ingestion_id=str(payload.get("ingestion_id") or ""),
            source_ids=_string_tuple(payload.get("source_ids")),
            status=str(payload.get("status") or ""),
            chunks_created=int(payload.get("chunks_created") or 0),
            chunks_indexed=int(payload.get("chunks_indexed") or 0),
            embedding_manifest_id=str(payload["embedding_manifest_id"])
            if payload.get("embedding_manifest_id") is not None
            else None,
            warnings=_string_tuple(payload.get("warnings")),
            blockers=_string_tuple(payload.get("blockers")),
            created_at=_parse_datetime(payload.get("created_at")),
            schema_version=str(payload.get("schema_version") or KNOWLEDGE_SCHEMA_VERSION),
        )
