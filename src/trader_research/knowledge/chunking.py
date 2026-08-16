"""Split extracted knowledge text while preserving source locators.

Chunking is deterministic for the same document and configuration, retains page
or section provenance needed for citations, and emits bounded text units for
indexing. It performs no embedding, retrieval, or persistence.
"""

from __future__ import annotations

from dataclasses import replace
import hashlib
import re
from typing import Sequence

from trader_research.foundation import stable_research_id

from .domain import KnowledgeChunk, KnowledgeSourceManifest
from .extractors import ExtractedSection


DEFAULT_MAX_CHARS = 700
"""Default maximum evidence-unit size for deterministic local indexing."""

CHUNKER_VERSION = "evidence-unit-v1"
"""Version marker for schema-v2 evidence-unit chunking semantics."""

_SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9(])")
_INLINE_LABEL_BOUNDARY_RE = re.compile(
    r"(?<=[.;])\s+(?=[A-Z][A-Za-z][A-Za-z0-9 /,+-]{2,90}?\s*\([A-Z][A-Z0-9]{1,12}\)\s*:)"
)
_METHOD_LABEL_PATTERNS = (
    re.compile(
        r"(?:^|[.;]\s+)([A-Z][A-Za-z][A-Za-z0-9 /,+-]{2,90}?)\s*\(([A-Z][A-Z0-9]{1,12})\)\s*:"
    ),
    re.compile(r"(?:^|[.;]\s+)([A-Z][A-Za-z][A-Za-z0-9 /,+-]{2,90}?)\s*\(([A-Z][A-Z0-9]{1,12})\)"),
    re.compile(r"(?:^|[.;]\s+)([A-Z][A-Za-z][A-Za-z0-9 /,+-]{2,90}?)\s+Rule\s*:"),
)


def chunk_sections(
    source: KnowledgeSourceManifest,
    sections: Sequence[ExtractedSection],
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> tuple[KnowledgeChunk, ...]:
    """Split extracted sections into stable, locator-preserving evidence units.

    Text is chunked deterministically in source order, each evidence unit receives
    a hash of its exact text, and the locator preserves page/section/offset
    metadata from extraction. Units are sentence/paragraph aware and may split at
    inline method labels to improve retrieval precision. That optimization does
    not assign exclusive semantic ownership: claim-span extraction may reuse one
    evidence unit for several methodologies.
    """
    chunks: list[KnowledgeChunk] = []
    for section in sections:
        parent_section_id = stable_research_id(
            "knowledge_section",
            {
                "source_id": source.source_id,
                "page": section.page,
                "section": section.section,
                "heading": section.heading,
                "start_offset": section.start_offset,
                "end_offset": section.end_offset,
            },
        )
        for unit in _split_text(section.text, max_chars=max_chars):
            text = unit.text
            text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
            ordinal = len(chunks)
            locator = {
                "source_id": source.source_id,
                "page": section.page,
                "section": section.section,
                "heading": section.heading,
                "part": unit.part_index,
                "start_offset": section.start_offset,
                "end_offset": section.end_offset,
                "parent_section_id": parent_section_id,
                "paragraph_index": unit.paragraph_index,
                "sentence_start_index": unit.sentence_start_index,
                "sentence_end_index": unit.sentence_end_index,
                "chunker_version": CHUNKER_VERSION,
            }
            chunk_id = stable_research_id(
                "knowledge_evidence_unit",
                {
                    "source_id": source.source_id,
                    "ordinal": ordinal,
                    "text_hash": text_hash,
                    "locator": locator,
                },
            )
            chunks.append(
                KnowledgeChunk(
                    chunk_id=chunk_id,
                    source_id=source.source_id,
                    ordinal=ordinal,
                    text=text,
                    text_hash=text_hash,
                    locator=locator,
                    topics=source.topics,
                    method_families=source.method_families,
                    parent_section_id=parent_section_id,
                    paragraph_index=unit.paragraph_index,
                    sentence_start_index=unit.sentence_start_index,
                    sentence_end_index=unit.sentence_end_index,
                    detected_labels=_detect_method_labels(text),
                    chunker_version=CHUNKER_VERSION,
                )
            )
    return _with_neighbors(chunks)


class _EvidenceUnitText:
    """Intermediate text span produced before stable IDs and neighbor links exist."""

    def __init__(
        self,
        *,
        text: str,
        part_index: int,
        paragraph_index: int,
        sentence_start_index: int,
        sentence_end_index: int,
    ) -> None:
        self.text = text
        self.part_index = part_index
        self.paragraph_index = paragraph_index
        self.sentence_start_index = sentence_start_index
        self.sentence_end_index = sentence_end_index


def _split_text(text: str, *, max_chars: int) -> tuple[_EvidenceUnitText, ...]:
    cleaned = text.replace("\x00", " ").strip()
    if not cleaned:
        return tuple()
    paragraphs = [paragraph.strip() for paragraph in cleaned.split("\n\n") if paragraph.strip()]
    units: list[_EvidenceUnitText] = []
    part_index = 0
    for paragraph_index, paragraph in enumerate(paragraphs):
        sentences = _sentences(paragraph)
        current: list[str] = []
        current_start = 0
        for sentence_index, sentence in enumerate(sentences):
            if len(sentence) > max_chars:
                if current:
                    units.append(
                        _EvidenceUnitText(
                            text=" ".join(current).strip(),
                            part_index=part_index,
                            paragraph_index=paragraph_index,
                            sentence_start_index=current_start,
                            sentence_end_index=sentence_index - 1,
                        )
                    )
                    part_index += 1
                    current = []
                for hard_part in _hard_split(sentence, max_chars=max_chars):
                    units.append(
                        _EvidenceUnitText(
                            text=hard_part,
                            part_index=part_index,
                            paragraph_index=paragraph_index,
                            sentence_start_index=sentence_index,
                            sentence_end_index=sentence_index,
                        )
                    )
                    part_index += 1
                current_start = sentence_index + 1
                continue
            candidate = " ".join((*current, sentence)).strip()
            starts_new_unit = bool(
                current
                and (
                    _detect_method_labels(sentence)
                    or _is_title_like_line(sentence)
                    or _is_title_like_line(" ".join(current))
                )
            )
            if current and (len(candidate) > max_chars or starts_new_unit):
                units.append(
                    _EvidenceUnitText(
                        text=" ".join(current).strip(),
                        part_index=part_index,
                        paragraph_index=paragraph_index,
                        sentence_start_index=current_start,
                        sentence_end_index=sentence_index - 1,
                    )
                )
                part_index += 1
                current = [sentence]
                current_start = sentence_index
            else:
                if not current:
                    current_start = sentence_index
                current.append(sentence)
        if current:
            units.append(
                _EvidenceUnitText(
                    text=" ".join(current).strip(),
                    part_index=part_index,
                    paragraph_index=paragraph_index,
                    sentence_start_index=current_start,
                    sentence_end_index=len(sentences) - 1,
                )
            )
            part_index += 1
    return tuple(unit for unit in units if unit.text)


def _hard_split(text: str, *, max_chars: int) -> tuple[str, ...]:
    parts = []
    for start in range(0, len(text), max_chars):
        part = text[start : start + max_chars].strip()
        if part:
            parts.append(part)
    return tuple(parts)


def _sentences(paragraph: str) -> tuple[str, ...]:
    if not paragraph.strip():
        return tuple()
    sentence_parts: list[str] = []
    for raw_line in paragraph.splitlines():
        normalized = " ".join(raw_line.split())
        if not normalized:
            continue
        label_parts: list[str] = []
        for part in _INLINE_LABEL_BOUNDARY_RE.split(normalized):
            label_parts.extend(_SENTENCE_BOUNDARY_RE.split(part))
        sentence_parts.extend(part.strip() for part in label_parts if part.strip())
    if not sentence_parts:
        normalized = " ".join(paragraph.split())
        return (normalized,) if normalized else tuple()
    return tuple(sentence_parts)


def _detect_method_labels(text: str) -> tuple[str, ...]:
    labels: list[str] = []
    normalized = " ".join(text.split())
    for pattern in _METHOD_LABEL_PATTERNS:
        for match in pattern.finditer(normalized):
            name = " ".join(match.group(1).split()).strip(" :-")
            if name and len(name.split()) <= 10:
                labels.append(name)
            if match.lastindex and match.lastindex >= 2:
                acronym = str(match.group(2)).strip()
                if acronym:
                    labels.append(acronym)
    return tuple(dict.fromkeys(labels))


def _is_title_like_line(text: str) -> bool:
    normalized = " ".join(text.split()).strip(" :-")
    if not normalized or re.search(r"[.!?]", normalized):
        return False
    normalized = re.sub(r"^chapter\s+\d+[.: -]*", "", normalized, flags=re.IGNORECASE).strip()
    words = re.findall(r"[A-Za-z][A-Za-z0-9+-]*", normalized)
    if not 2 <= len(words) <= 10:
        return False
    titleish = sum(1 for word in words if word[:1].isupper() or word.lower() in {"and", "or", "of", "the"})
    return titleish / len(words) >= 0.7


def _with_neighbors(chunks: Sequence[KnowledgeChunk]) -> tuple[KnowledgeChunk, ...]:
    by_index: list[KnowledgeChunk] = []
    for index, chunk in enumerate(chunks):
        neighbors = []
        if index > 0 and chunks[index - 1].source_id == chunk.source_id:
            neighbors.append(chunks[index - 1].chunk_id)
        if index + 1 < len(chunks) and chunks[index + 1].source_id == chunk.source_id:
            neighbors.append(chunks[index + 1].chunk_id)
        by_index.append(replace(chunk, neighbor_chunk_ids=tuple(neighbors)))
    return tuple(by_index)
