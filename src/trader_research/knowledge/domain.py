"""Typed artifacts for the Quant Methods knowledge base."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


KNOWLEDGE_SCHEMA_VERSION = "1"
"""Schema version for local knowledge artifacts."""

SUPPORTED_SOURCE_EXTENSIONS = frozenset({".md", ".txt", ".pdf"})
"""File types accepted by the first knowledge-ingestion slice."""

SOURCE_TYPE_LABELS = frozenset(
    {
        "foundation_textbook",
        "method_textbook",
        "primary_paper",
        "software_documentation",
        "internal_note",
    }
)
"""Allowed source-type labels for registered knowledge documents."""

DEFAULT_SOURCE_TYPE = "internal_note"
"""Default source-type label for local notes and operator-authored documents."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


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
    """Citeable unit of source text stored in the knowledge index.

    A chunk stores exact text, a content hash, its source ID, ordinal position, and
    locator metadata such as page, heading, or offsets. The validation contract
    requires non-empty text and locator data so retrieval results can be
    dereferenced and citation validation can prove which source span supports a
    claim.
    """

    chunk_id: str
    source_id: str
    ordinal: int
    text: str
    text_hash: str
    locator: Mapping[str, Any]
    topics: tuple[str, ...] = tuple()
    method_families: tuple[str, ...] = tuple()

    def __post_init__(self) -> None:
        if not self.chunk_id.strip():
            raise ValueError("chunk_id is required")
        if not self.source_id.strip():
            raise ValueError("source_id is required")
        if not self.text.strip():
            raise ValueError("chunk text is required")
        if not self.text_hash.strip():
            raise ValueError("chunk text_hash is required")
        if not self.locator:
            raise ValueError("chunk locator is required")

    def to_dict(self) -> dict[str, Any]:
        """Serialize a citeable chunk with locator, topics, and exact text hash.

        Locator metadata is normalized through `_jsonable`, while tuple fields are
        emitted as lists so the chunk can be stored in JSON or Postgres payloads.
        """
        return {
            "chunk_id": self.chunk_id,
            "source_id": self.source_id,
            "ordinal": self.ordinal,
            "text": self.text,
            "text_hash": self.text_hash,
            "locator": _jsonable(self.locator),
            "topics": list(self.topics),
            "method_families": list(self.method_families),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "KnowledgeChunk":
        """Parse a chunk payload from storage into a validated domain object.

        Missing optional topics and method families become empty tuples, while
        required source, text, hash, ordinal, and locator fields are validated by
        the dataclass constructor.
        """
        return cls(
            chunk_id=str(payload.get("chunk_id") or ""),
            source_id=str(payload.get("source_id") or ""),
            ordinal=int(payload.get("ordinal") or 0),
            text=str(payload.get("text") or ""),
            text_hash=str(payload.get("text_hash") or ""),
            locator=_mapping(payload.get("locator")),
            topics=_string_tuple(payload.get("topics")),
            method_families=_string_tuple(payload.get("method_families")),
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
            "embedding_manifest_id": self.embedding_manifest_id,
            "warnings": list(self.warnings),
            "blockers": list(self.blockers),
            "created_at": _jsonable(self.created_at),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "KnowledgeIngestionReport":
        """Parse a stored ingestion report while normalizing optional collections, status, and counts."""
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


@dataclass(frozen=True)
class EvidenceReference:
    """Serializable citation pointer used by method cards and generated artifacts.

    A reference can point at a source, a specific chunk, a method card, or a
    combination of those identifiers, with an optional locator snapshot and claim
    text. Citation validation uses these fields to prove that claimed evidence
    exists, belongs to the expected source, and has not been cited with a mismatched
    locator.
    """

    source_id: str | None = None
    chunk_id: str | None = None
    locator: Mapping[str, Any] = field(default_factory=dict)
    method_card_id: str | None = None
    claim: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize citation identifiers, locator details, and optional claim text.

        Locator mappings are normalized for JSON storage while absent source,
        chunk, or method-card IDs are preserved as `None` so validators can
        distinguish partial references from empty strings.
        """
        return {
            "source_id": self.source_id,
            "chunk_id": self.chunk_id,
            "locator": _jsonable(self.locator),
            "method_card_id": self.method_card_id,
            "claim": self.claim,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "EvidenceReference":
        """Parse an evidence reference from JSON-compatible artifact data.

        Optional identifiers and claim text remain optional, while locator payloads
        are normalized to mappings so citation validation can compare fields
        against stored chunk locators.
        """
        return cls(
            source_id=str(payload["source_id"]) if payload.get("source_id") is not None else None,
            chunk_id=str(payload["chunk_id"]) if payload.get("chunk_id") is not None else None,
            locator=_mapping(payload.get("locator")),
            method_card_id=str(payload["method_card_id"]) if payload.get("method_card_id") is not None else None,
            claim=str(payload["claim"]) if payload.get("claim") is not None else None,
        )


@dataclass(frozen=True)
class MethodCard:
    """Curated contract for a quantitative method and its evidence base.

    Method cards describe the method family, assumptions, inputs, outputs, failure
    modes, supporting evidence references, approval status, and version lineage.
    Draft cards can be created from validated source evidence; approved cards are
    the stable artifacts that method implementations and research tools are
    expected to cite.
    """

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
        if self.status not in {"approved", "draft", "planned"}:
            raise ValueError(f"unsupported method-card status: {self.status}")

    @property
    def approved(self) -> bool:
        """Return whether this method card is approved for implementation evidence citations."""
        return self.status == "approved"

    def to_dict(self) -> dict[str, Any]:
        """Serialize method-card contract fields, evidence refs, and approval metadata.

        Draft cards emit the draft artifact type, approved/planned cards emit the
        method-card artifact type, and all tuple fields are converted to lists for
        persistence or tool-envelope payloads.
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

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "MethodCard":
        """Parse a method-card payload from seeded data or persisted artifacts.

        Evidence references, tuple fields, approval metadata, timestamps, status,
        version, and schema version are normalized before the constructor enforces
        method-card identity and allowed status values.
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
            evidence_refs=tuple(EvidenceReference.from_dict(_mapping(item)) for item in _sequence(payload.get("evidence_refs"))),
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
class EvidenceRetrievalReport:
    """Retrieval artifact containing ranked chunks that downstream agents may cite.

    The report stores the original query, applied filters, and JSON-compatible
    result rows that include source/chunk identifiers and locators. It provides a
    reviewable bridge between search execution and later method-card or artifact
    citations.
    """

    retrieval_id: str
    query: str
    results: tuple[Mapping[str, Any], ...]
    filters: Mapping[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utc_now)
    schema_version: str = KNOWLEDGE_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        """Serialize retrieval results, filters, query, and creation timestamp.

        Result rows are normalized recursively so downstream agents can cite
        returned chunk/source identifiers without depending on store-specific row
        objects.
        """
        return {
            "artifact_type": "evidence_retrieval_report",
            "schema_version": self.schema_version,
            "retrieval_id": self.retrieval_id,
            "query": self.query,
            "filters": _jsonable(self.filters),
            "results": _jsonable(list(self.results)),
            "created_at": _jsonable(self.created_at),
        }


@dataclass(frozen=True)
class EvidenceChunkDereferenceReport:
    """Dereference artifact for turning chunk IDs back into bounded source text.

    The report preserves the requested IDs, resolved chunk payloads, missing IDs,
    filters, and warnings so a tool can supply evidence context without silently
    dropping unresolved references. It is useful when generation or validation
    needs exact text rather than only search result metadata.
    """

    dereference_id: str
    requested_chunk_ids: tuple[str, ...]
    chunks: tuple[Mapping[str, Any], ...]
    missing_chunk_ids: tuple[str, ...] = tuple()
    filters: Mapping[str, Any] = field(default_factory=dict)
    warnings: tuple[str, ...] = tuple()
    created_at: datetime = field(default_factory=_utc_now)
    schema_version: str = KNOWLEDGE_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        """Serialize dereferenced chunk payloads together with missing IDs and warnings.

        The report includes request filters and counts so callers can verify that
        the evidence context contains exactly the chunks they asked to inspect.
        """
        return {
            "artifact_type": "evidence_chunk_dereference_report",
            "schema_version": self.schema_version,
            "dereference_id": self.dereference_id,
            "requested_chunk_ids": list(self.requested_chunk_ids),
            "filters": _jsonable(self.filters),
            "chunk_count": len(self.chunks),
            "chunks": _jsonable(list(self.chunks)),
            "missing_chunk_ids": list(self.missing_chunk_ids),
            "warnings": list(self.warnings),
            "created_at": _jsonable(self.created_at),
        }


@dataclass(frozen=True)
class CitationValidationReport:
    """Audit record for citation checks against knowledge-store state.

    The report captures every checked reference, whether all required evidence was
    valid, and the warnings or blockers produced during lookup. Tool envelopes use
    this object to expose the full validation trail even when invalid citations
    cause the command to return an error.
    """

    validation_id: str
    valid: bool
    checked_refs: tuple[Mapping[str, Any], ...]
    warnings: tuple[str, ...] = tuple()
    blockers: tuple[str, ...] = tuple()
    created_at: datetime = field(default_factory=_utc_now)
    schema_version: str = KNOWLEDGE_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        """Serialize citation-validation results with checked references and blockers.

        The report preserves every checked reference, warning, blocker, and
        validation status so failed tool envelopes still contain a complete audit
        trail for review.
        """
        return {
            "artifact_type": "citation_validation_report",
            "schema_version": self.schema_version,
            "validation_id": self.validation_id,
            "valid": self.valid,
            "checked_refs": _jsonable(list(self.checked_refs)),
            "warnings": list(self.warnings),
            "blockers": list(self.blockers),
            "created_at": _jsonable(self.created_at),
        }


def _parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if isinstance(value, str) and value:
        text = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    return _utc_now()


def _jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _jsonable(val) for key, val in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> Sequence[Any]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes)):
        return (value,)
    if isinstance(value, Sequence):
        return value
    return (value,)


def _string_tuple(value: Any) -> tuple[str, ...]:
    return tuple(str(item) for item in _sequence(value) if str(item).strip())
