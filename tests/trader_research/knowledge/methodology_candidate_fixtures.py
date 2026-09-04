"""Reusable builders for knowledge methodology-candidate contract tests.

These helpers construct bounded local knowledge stores and deterministic evidence
without adding shared repository-level fixture ownership.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from trader_research.knowledge.chunking import chunk_sections
from trader_research.knowledge.domain import KnowledgeChunk, KnowledgeSourceManifest
from trader_research.knowledge.extractors import ExtractedSection
from trader_research.knowledge.store import JsonKnowledgeStore


def _store_with_pairs_chunks(tmp_path: Path, *, source_type: str = "method_textbook"):
    artifact_root = tmp_path / "artifacts"
    store = JsonKnowledgeStore(artifact_root)
    source = KnowledgeSourceManifest(
        source_id="knowledge_source_pairs",
        title="Pairs Trading Source",
        source_type=source_type,
        path="tests/trader_research/knowledge/fixtures/quant_notes.txt",
        file_hash="abc123",
        file_size_bytes=42,
        topics=("statistical arbitrage",),
        method_families=("statistical_arbitrage",),
    )
    chunks = (
        _chunk(
            source, 0, "Background context for market-neutral trading.", "Pairs Trading"
        ),
        _chunk(
            source,
            1,
            (
                "Pairs trading forms a spread between two related assets. The method estimates a hedge ratio "
                "with regression and tests for cointegration and stationarity."
            ),
            "Pairs Trading",
        ),
        _chunk(
            source,
            2,
            "The spread signal enters when the z-score crosses a threshold and exits when it mean reverts.",
            "Pairs Trading",
        ),
    )
    store.save_source(source)
    store.replace_chunks(source.source_id, chunks)
    return artifact_root, store, source, chunks


def _store_with_sma_chunks(tmp_path: Path):
    artifact_root = tmp_path / "artifacts"
    store = JsonKnowledgeStore(artifact_root)
    source = KnowledgeSourceManifest(
        source_id="knowledge_source_sma",
        title="Technical Indicator Source",
        source_type="method_textbook",
        path="tests/fixtures/knowledge/technical_notes.txt",
        file_hash="def456",
        file_size_bytes=84,
        topics=("technical indicators",),
        method_families=("technical_indicators",),
    )
    chunks = (
        _chunk(
            source,
            0,
            "Compute unrelated average portfolio sums from active trades.",
            "Page 80",
        ),
        _chunk(
            source,
            1,
            (
                "The moving average trading rules compare current price with averages of past prices. "
                "Simple Moving Average (SMA): P m t = one over m times the sum of lagged prices. "
                "The moving window has width m."
            ),
            "Page 181",
        ),
        _chunk(
            source,
            2,
            "A signal occurs when price crosses a moving average rule threshold.",
            "Page 182",
        ),
        _chunk(
            source,
            3,
            "Simple Moving Average risk includes noisy regimes and whipsaw failure modes.",
            "Page 183",
        ),
        _chunk(
            source,
            4,
            "Another exercise says compute average sums and ratios for moving portfolios.",
            "Page 225",
        ),
    )
    store.save_source(source)
    store.replace_chunks(source.source_id, chunks)
    return artifact_root, store, source, chunks


def _store_with_adjacent_indicator_units(tmp_path: Path):
    artifact_root = tmp_path / "artifacts"
    store = JsonKnowledgeStore(artifact_root)
    source = KnowledgeSourceManifest(
        source_id="knowledge_source_adjacent_indicator_roles",
        title="Adjacent Indicator Role Source",
        source_type="method_textbook",
        path="tests/fixtures/knowledge/technical_notes.txt",
        file_hash="adjacent-role-123",
        file_size_bytes=512,
        topics=("technical indicators",),
        method_families=("technical_indicators",),
    )
    chunks = chunk_sections(
        source,
        (
            ExtractedSection(
                text=(
                    "Simple Moving Average (SMA): The SMA formula calculates the unweighted average of lagged prices. "
                    "Exponentially Weighted Average (EWA): The EWA indicator computes a weighted moving average of "
                    "closing prices with a smoothing parameter alpha. "
                    "Bollinger Bands (BB): Bollinger Bands generate a signal when price crosses the upper or lower "
                    "band around a moving average."
                ),
                section="technical indicators",
                heading="Page 181",
            ),
        ),
    )
    store.save_source(source)
    store.replace_chunks(source.source_id, chunks)
    return artifact_root, store, source, chunks


def _chunk(
    source: KnowledgeSourceManifest, ordinal: int, text: str, heading: str
) -> KnowledgeChunk:
    text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return KnowledgeChunk(
        chunk_id=f"knowledge_chunk_pairs_{ordinal}",
        source_id=source.source_id,
        ordinal=ordinal,
        text=text,
        text_hash=text_hash,
        locator={
            "source_id": source.source_id,
            "heading": heading,
            "page": ordinal + 1,
        },
        topics=source.topics,
        method_families=source.method_families,
    )
