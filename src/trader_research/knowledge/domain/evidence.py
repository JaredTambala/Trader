"""Define exact evidence references and evidence-backed field values.

Models preserve source, chunk, locator, and character-span provenance needed to
recheck a claim. They distinguish absent support from populated values and fail
validation when persisted evidence shapes are incomplete or inconsistent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from typing import Any, Mapping

from .common import (
    _jsonable,
    _has_methodology_value,
    _mapping,
    _sequence,
    _string_tuple,
)

@dataclass(frozen=True)
class EvidenceClaimSpan:
    """Addressable source text supporting one methodology claim.

    Evidence units remain reusable retrieval containers. This span identifies the
    exact text within one unit that was selected for a role and target method, so
    semantic validation does not infer ownership from the surrounding chunk.
    """

    span_id: str
    start_char: int
    end_char: int
    text: str
    text_hash: str
    evidence_role: str
    target_method: str
    target_binding: str
    matched_terms: tuple[str, ...] = tuple()
    method_labels: tuple[str, ...] = tuple()
    extraction_engine: str = "deterministic_claim_spans"
    extraction_version: str = "1"

    def __post_init__(self) -> None:
        if not self.span_id.strip():
            raise ValueError("claim span_id is required")
        if self.start_char < 0 or self.end_char <= self.start_char:
            raise ValueError("claim span offsets must identify non-empty text")
        if not self.text:
            raise ValueError("claim span text is required")
        if hashlib.sha256(self.text.encode("utf-8")).hexdigest() != self.text_hash:
            raise ValueError("claim span text_hash does not match text")
        if not self.evidence_role.strip() or not self.target_method.strip():
            raise ValueError("claim span evidence_role and target_method are required")

    def to_dict(self) -> dict[str, Any]:
        """Serialize exact claim-span provenance for artifact persistence.

        Source, chunk, locator, character offsets, quoted text, digest, and optional
        target-field and role context are emitted so downstream validation can
        recheck the precise evidence region.
        """
        return {
            "span_id": self.span_id,
            "start_char": self.start_char,
            "end_char": self.end_char,
            "text": self.text,
            "text_hash": self.text_hash,
            "evidence_role": self.evidence_role,
            "target_method": self.target_method,
            "target_binding": self.target_binding,
            "matched_terms": list(self.matched_terms),
            "method_labels": list(self.method_labels),
            "extraction_engine": self.extraction_engine,
            "extraction_version": self.extraction_version,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "EvidenceClaimSpan":
        """Parse and validate an exact persisted claim span.

        Identifiers, locator, offsets, text, digest, and optional target context
        are normalized before constructor checks enforce non-empty provenance,
        valid bounds, and digest agreement.
        """
        return cls(
            span_id=str(payload.get("span_id") or ""),
            start_char=int(payload.get("start_char") or 0),
            end_char=int(payload.get("end_char") or 0),
            text=str(payload.get("text") or ""),
            text_hash=str(payload.get("text_hash") or ""),
            evidence_role=str(payload.get("evidence_role") or ""),
            target_method=str(payload.get("target_method") or ""),
            target_binding=str(payload.get("target_binding") or ""),
            matched_terms=_string_tuple(payload.get("matched_terms")),
            method_labels=_string_tuple(payload.get("method_labels")),
            extraction_engine=str(payload.get("extraction_engine") or "deterministic_claim_spans"),
            extraction_version=str(payload.get("extraction_version") or "1"),
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
    claim_span: EvidenceClaimSpan | None = None

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
            "claim_span": self.claim_span.to_dict() if self.claim_span is not None else None,
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
            claim_span=(
                EvidenceClaimSpan.from_dict(_mapping(payload.get("claim_span")))
                if payload.get("claim_span") is not None
                else None
            ),
        )


@dataclass(frozen=True)
class EvidenceBackedField:
    """Nullable methodology field value with field-level citation evidence.

    Methodology artifacts can leave fields unset when a source does not
    support them. When a value is populated, at least one evidence reference is
    required so later extraction, validation, and strategy generation can explain
    exactly which chunk or source backs the claim.
    """

    value: Any | None = None
    evidence_refs: tuple[EvidenceReference, ...] = tuple()
    confidence: float | None = None
    quality: str | None = None
    warnings: tuple[str, ...] = tuple()
    blockers: tuple[str, ...] = tuple()

    def __post_init__(self) -> None:
        if _has_methodology_value(self.value) and not self.evidence_refs:
            raise ValueError("populated methodology field requires evidence_refs")
        if self.confidence is not None and not 0.0 <= self.confidence <= 1.0:
            raise ValueError("field confidence must be between 0 and 1")

    def to_dict(self) -> dict[str, Any]:
        """Serialize a nullable field value, evidence refs, and quality metadata."""
        return {
            "value": _jsonable(self.value),
            "evidence_refs": [ref.to_dict() for ref in self.evidence_refs],
            "confidence": self.confidence,
            "quality": self.quality,
            "warnings": list(self.warnings),
            "blockers": list(self.blockers),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "EvidenceBackedField":
        """Parse one evidence-backed field from JSON-compatible payload data."""
        return cls(
            value=payload.get("value"),
            evidence_refs=tuple(
                EvidenceReference.from_dict(_mapping(item))
                for item in _sequence(payload.get("evidence_refs"))
            ),
            confidence=float(payload["confidence"]) if payload.get("confidence") is not None else None,
            quality=str(payload["quality"]) if payload.get("quality") is not None else None,
            warnings=_string_tuple(payload.get("warnings")),
            blockers=_string_tuple(payload.get("blockers")),
        )
