"""Locator-preserving chunking for knowledge sources."""

from __future__ import annotations

import hashlib
from typing import Sequence

from trader_research.domain import stable_research_id

from .domain import KnowledgeChunk, KnowledgeSourceManifest
from .extractors import ExtractedSection


DEFAULT_MAX_CHARS = 2000
"""Default maximum chunk size for deterministic local indexing."""


def chunk_sections(
    source: KnowledgeSourceManifest,
    sections: Sequence[ExtractedSection],
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> tuple[KnowledgeChunk, ...]:
    """Split extracted sections into stable, locator-preserving knowledge chunks.

    Text is chunked deterministically in source order, each chunk receives a hash
    of its exact text, and the locator preserves page/section/offset metadata from
    extraction. The chunk ID includes source ID, ordinal, text hash, and locator so
    repeated ingestion of unchanged content produces the same citeable IDs while
    changed source text is naturally re-indexed under new IDs.
    """
    chunks: list[KnowledgeChunk] = []
    for section in sections:
        for part_index, part in enumerate(_split_text(section.text, max_chars=max_chars)):
            text_hash = hashlib.sha256(part.encode("utf-8")).hexdigest()
            ordinal = len(chunks)
            locator = {
                "source_id": source.source_id,
                "page": section.page,
                "section": section.section,
                "heading": section.heading,
                "part": part_index,
                "start_offset": section.start_offset,
                "end_offset": section.end_offset,
            }
            chunk_id = stable_research_id(
                "knowledge_chunk",
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
                    text=part,
                    text_hash=text_hash,
                    locator=locator,
                    topics=source.topics,
                    method_families=source.method_families,
                )
            )
    return tuple(chunks)


def _split_text(text: str, *, max_chars: int) -> tuple[str, ...]:
    cleaned = text.replace("\x00", " ").strip()
    if not cleaned:
        return tuple()
    paragraphs = [paragraph.strip() for paragraph in cleaned.split("\n\n") if paragraph.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        if len(paragraph) > max_chars:
            if current:
                chunks.append(current.strip())
                current = ""
            chunks.extend(_hard_split(paragraph, max_chars=max_chars))
            continue
        candidate = f"{current}\n\n{paragraph}".strip() if current else paragraph
        if len(candidate) > max_chars and current:
            chunks.append(current.strip())
            current = paragraph
        else:
            current = candidate
    if current.strip():
        chunks.append(current.strip())
    return tuple(chunks)


def _hard_split(text: str, *, max_chars: int) -> tuple[str, ...]:
    parts = []
    for start in range(0, len(text), max_chars):
        part = text[start : start + max_chars].strip()
        if part:
            parts.append(part)
    return tuple(parts)
