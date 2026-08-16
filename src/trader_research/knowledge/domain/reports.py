"""Define ingestion and validation report values for knowledge operations.

Reports carry bounded counts, warnings, blockers, and canonical references needed
for operators to understand partial or failed work. They are evidence summaries,
not substitutes for stored sources, chunks, or method cards.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping

from .common import (
    KNOWLEDGE_SCHEMA_VERSION,
    _jsonable,
    _utc_now,
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
    valid, and the warnings or blockers produced during lookup. Tool results use
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
        validation status so failed tool results still contain a complete audit
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
