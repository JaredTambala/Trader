"""Deterministic text extraction for local knowledge sources."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


@dataclass(frozen=True)
class ExtractedSection:
    """Text span extracted from a source with enough locator data for citation.

    Extractors fill page, heading, section, and byte/character offsets when the
    source format exposes them. Chunking preserves these fields so retrieval
    results and citation-validation reports can point back to the source span that
    produced a piece of evidence.
    """

    text: str
    page: int | None = None
    section: str | None = None
    heading: str | None = None
    start_offset: int = 0
    end_offset: int = 0


@dataclass(frozen=True)
class ExtractedDocument:
    """Result of extracting text from one local source file.

    `sections` contains non-empty extracted spans in source order; `warnings`
    records recoverable extraction limitations such as empty PDF pages or disabled
    OCR. Ingestion can continue when some sections are present while still
    surfacing these warnings in the final report.
    """

    sections: tuple[ExtractedSection, ...]
    warnings: tuple[str, ...] = tuple()


def extract_text(path: str | Path) -> ExtractedDocument:
    """Dispatch deterministic extraction for markdown, plain text, or PDF sources.

    Markdown is split by headings, text files are treated as a single section, and
    PDFs use embedded text from `pypdf` with page-level locators. Unsupported
    suffixes fail at this boundary so ingestion does not produce chunks with
    unknown provenance semantics.
    """
    source_path = Path(path)
    suffix = source_path.suffix.lower()
    if suffix == ".md":
        return _extract_markdown(source_path)
    if suffix == ".txt":
        return _extract_plain_text(source_path)
    if suffix == ".pdf":
        return _extract_pdf(source_path)
    raise ValueError(f"unsupported source file type: {suffix}")


def _extract_plain_text(path: Path) -> ExtractedDocument:
    text = path.read_text(encoding="utf-8")
    cleaned = text.strip()
    if not cleaned:
        return ExtractedDocument(sections=tuple(), warnings=("source text is empty",))
    return ExtractedDocument(
        sections=(
            ExtractedSection(
                text=cleaned,
                section=path.stem,
                heading=path.stem,
                start_offset=0,
                end_offset=len(text),
            ),
        )
    )


def _extract_markdown(path: Path) -> ExtractedDocument:
    text = path.read_text(encoding="utf-8")
    sections: list[ExtractedSection] = []
    current_heading = path.stem
    current_lines: list[str] = []
    current_start = 0
    offset = 0
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if stripped.startswith("#"):
            if "".join(current_lines).strip():
                content = "".join(current_lines).strip()
                sections.append(
                    ExtractedSection(
                        text=content,
                        section=current_heading,
                        heading=current_heading,
                        start_offset=current_start,
                        end_offset=offset,
                    )
                )
            current_heading = stripped.lstrip("#").strip() or path.stem
            current_lines = []
            current_start = offset + len(line)
        else:
            current_lines.append(line)
        offset += len(line)
    if "".join(current_lines).strip():
        content = "".join(current_lines).strip()
        sections.append(
            ExtractedSection(
                text=content,
                section=current_heading,
                heading=current_heading,
                start_offset=current_start,
                end_offset=len(text),
            )
        )
    if not sections and text.strip():
        sections.append(
            ExtractedSection(
                text=text.strip(),
                section=path.stem,
                heading=path.stem,
                start_offset=0,
                end_offset=len(text),
            )
        )
    warnings = tuple() if sections else ("source text is empty",)
    return ExtractedDocument(sections=tuple(sections), warnings=warnings)


def _extract_pdf(path: Path) -> ExtractedDocument:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    sections: list[ExtractedSection] = []
    warnings: list[str] = []
    for page_index, page in enumerate(reader.pages, start=1):
        page_text = page.extract_text() or ""
        cleaned = page_text.strip()
        if not cleaned:
            warnings.append(f"page {page_index} has no extractable text; OCR is disabled")
            continue
        sections.append(
            ExtractedSection(
                text=cleaned,
                page=page_index,
                section=f"page-{page_index}",
                heading=f"Page {page_index}",
                start_offset=0,
                end_offset=len(page_text),
            )
        )
    if not sections and not warnings:
        warnings.append("PDF has no pages with extractable text; OCR is disabled")
    return ExtractedDocument(sections=tuple(sections), warnings=tuple(warnings))


def extracted_text(sections: Sequence[ExtractedSection]) -> str:
    """Join extracted sections into readable text while preserving section order.

    This helper is used by callers that need a compact human-readable document
    body rather than chunk-level metadata. It deliberately inserts blank lines
    between sections to avoid merging headings, paragraphs, or page extracts into
    ambiguous text.
    """
    return "\n\n".join(section.text for section in sections)
