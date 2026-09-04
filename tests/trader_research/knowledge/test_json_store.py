"""Unit contracts for the filesystem JSON knowledge store and retrieval index.

Subject: Active source/chunk state, embedding indexes, method cards, fusion ranking, and legacy rejection.
Level: In-process unit contract.
Collaborators: Real JSON store, deterministic embeddings, checked-in source text, and temporary files.
Guarantees: Stored evidence is queryable and deterministic while obsolete chunk manifests fail explicitly.
Non-goals: Postgres transactions, provider embeddings, semantic quality, concurrent writers, or MCP behavior.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from trader_research.knowledge.domain import (
    EvidenceReference,
    KnowledgeIngestionReport,
    KnowledgeSourceManifest,
    MethodCard,
)
from trader_research.knowledge.embeddings import DeterministicEmbeddingProvider
from trader_research.knowledge.extractors import extract_text
from trader_research.knowledge.index import (
    index_chunks,
    reciprocal_rank_fusion,
    search_chunks,
)
from trader_research.knowledge.chunking import chunk_sections
from trader_research.knowledge.store import JsonKnowledgeStore


FIXTURE = Path("tests/trader_research/knowledge/fixtures/sma_method.md")


def test_json_knowledge_store_contract_indexes_active_chunks(tmp_path: Path) -> None:
    """The JSON store persists active evidence, indexes it, and exposes deterministic hybrid retrieval."""
    store = JsonKnowledgeStore(tmp_path / "artifacts")
    source = KnowledgeSourceManifest(
        source_id="source_sma",
        title="SMA Source",
        source_type="internal_note",
        path=str(FIXTURE),
        file_hash="hash_sma",
        file_size_bytes=FIXTURE.stat().st_size,
        topics=("indicators",),
        method_families=("indicator",),
    )
    store.save_source(source)
    duplicate = store.find_sources_by_file_hash("hash_sma")
    chunks = chunk_sections(source, extract_text(FIXTURE).sections)
    store.replace_chunks(source.source_id, chunks)
    manifest = index_chunks(store, chunks, provider=DeterministicEmbeddingProvider())
    report = KnowledgeIngestionReport(
        ingestion_id="ingestion_sma",
        source_ids=(source.source_id,),
        status="indexed",
        chunks_created=len(chunks),
        chunks_indexed=len(chunks),
        embedding_manifest_id=manifest.embedding_manifest_id,
    )
    store.save_ingestion_report(report)
    method_card = MethodCard(
        method_card_id="method_card_store_demo",
        method_card_set_id="method_card_set_store_demo",
        revision_number=1,
        method_id="sma",
        title="SMA Store Demo",
        family="indicator",
        status="draft",
        assumptions=("ordered observations",),
        inputs=("prices",),
        outputs=("average",),
        failure_modes=("warmup",),
        evidence_refs=(
            EvidenceReference(source_id=source.source_id, chunk_id=chunks[0].chunk_id),
        ),
        source_methodology_candidate_id="methodology_candidate_store_demo",
        validation_refs=(
            {
                "artifact_type": "methodology_candidate_validation_report",
                "artifact_id": "validation_store_demo",
            },
        ),
    )
    store.save_method_card(method_card)

    lexical = store.search_lexical("simple moving average", limit=3)
    vector = store.search_vector(
        DeterministicEmbeddingProvider().embed("moving average warmup"),
        provider="local",
        model="deterministic-hash-vector",
        version="1",
        limit=3,
    )
    hybrid = search_chunks(
        store,
        "moving average warmup",
        provider=DeterministicEmbeddingProvider(),
        top_k=1,
    )

    assert duplicate[0].source_id == source.source_id
    assert store.load_source(source.source_id) == source
    assert store.load_chunks(source.source_id)
    assert store.load_chunks_by_ids((chunks[0].chunk_id, "missing")) == (chunks[0],)
    assert (
        store.list_ingestion_reports(source_ids=(source.source_id,))[0].ingestion_id
        == report.ingestion_id
    )
    assert store.list_persisted_method_cards() == (method_card,)
    assert not hasattr(store, "save_method_contract")
    assert not hasattr(store, "list_persisted_method_contracts")
    assert lexical
    assert vector
    assert hybrid[0]["retrieval_scores"]["combined_rank"] == 1


def test_reciprocal_rank_fusion_is_deterministic() -> None:
    """Lexical and vector rankings fuse deterministically with complete component score provenance."""
    lexical = (
        {"chunk_id": "b", "score": 10.0, "source_id": "s"},
        {"chunk_id": "a", "score": 5.0, "source_id": "s"},
    )
    vector = (
        {"chunk_id": "a", "score": 0.9, "source_id": "s"},
        {"chunk_id": "c", "score": 0.8, "source_id": "s"},
    )

    fused = reciprocal_rank_fusion(lexical, vector, top_k=3)

    assert [result["chunk_id"] for result in fused] == ["a", "b", "c"]
    assert fused[0]["retrieval_scores"] == {
        "lexical_rank": 2,
        "vector_rank": 1,
        "combined_rank": 1,
        "lexical_score": 5.0,
        "vector_score": 0.9,
        "fusion_score": (1.0 / 62.0) + (1.0 / 61.0),
    }


def test_json_knowledge_store_rejects_legacy_chunk_manifest(tmp_path: Path) -> None:
    """The JSON store rejects obsolete chunk manifests instead of silently interpreting stale evidence."""
    store = JsonKnowledgeStore(tmp_path / "artifacts")
    source = KnowledgeSourceManifest(
        source_id="source_legacy_chunks",
        title="Legacy Chunk Source",
        source_type="internal_note",
        path=str(FIXTURE),
        file_hash="hash_legacy",
        file_size_bytes=FIXTURE.stat().st_size,
    )
    store.save_source(source)
    store.repository.ensure_dirs()
    store.repository.chunk_manifest_path(source.source_id).write_text(
        json.dumps(
            {
                "artifact_type": "knowledge_chunk_manifest",
                "source_id": source.source_id,
                "chunks": [
                    {
                        "chunk_id": "knowledge_chunk_legacy",
                        "source_id": source.source_id,
                        "ordinal": 0,
                        "text": "legacy text",
                        "text_hash": "legacy_hash",
                        "locator": {"source_id": source.source_id},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="legacy knowledge chunk manifest"):
        store.load_chunks(source.source_id)
