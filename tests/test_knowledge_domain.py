from __future__ import annotations

import json

from trader_research.knowledge.domain import (
    DEFAULT_SOURCE_TYPE,
    EvidenceReference,
    KnowledgeChunk,
    KnowledgeEmbeddingManifest,
    KnowledgeIngestionReport,
    KnowledgeSourceManifest,
    MethodCard,
    SOURCE_TYPE_LABELS,
)


def test_knowledge_artifacts_round_trip_json() -> None:
    source = KnowledgeSourceManifest(
        source_id="knowledge_source_demo",
        title="Demo Source",
        source_type="method_textbook",
        path="tests/fixtures/knowledge/sma_method.md",
        file_hash="abc123",
        file_size_bytes=42,
        topics=("indicators",),
        method_families=("indicator",),
    )
    chunk = KnowledgeChunk(
        chunk_id="knowledge_chunk_demo",
        source_id=source.source_id,
        ordinal=0,
        text="moving average evidence",
        text_hash="def456",
        locator={"source_id": source.source_id, "heading": "Simple Moving Average"},
    )
    embedding = KnowledgeEmbeddingManifest(
        embedding_manifest_id="knowledge_embedding_demo",
        provider="local",
        model="deterministic-hash-vector",
        version="1",
        dimension=32,
        chunk_ids=(chunk.chunk_id,),
    )
    report = KnowledgeIngestionReport(
        ingestion_id="knowledge_ingestion_demo",
        source_ids=(source.source_id,),
        status="indexed",
        chunks_created=1,
        chunks_indexed=1,
        embedding_manifest_id=embedding.embedding_manifest_id,
    )
    method_card = MethodCard(
        method_card_id="method_card_demo",
        method_id="sma",
        title="SMA",
        family="indicator",
        status="approved",
        assumptions=("ordered input",),
        inputs=("prices",),
        outputs=("average",),
        failure_modes=("warmup",),
        evidence_refs=(EvidenceReference(source_id=source.source_id, chunk_id=chunk.chunk_id),),
    )

    payload = {
        "source": source.to_dict(),
        "chunk": chunk.to_dict(),
        "embedding": embedding.to_dict(),
        "report": report.to_dict(),
        "method_card": method_card.to_dict(),
    }

    assert KnowledgeSourceManifest.from_dict(payload["source"]).to_dict()["source_id"] == source.source_id
    assert KnowledgeChunk.from_dict(payload["chunk"]).to_dict()["chunk_id"] == chunk.chunk_id
    assert KnowledgeEmbeddingManifest.from_dict(payload["embedding"]).to_dict()["dimension"] == 32
    assert KnowledgeIngestionReport.from_dict(payload["report"]).to_dict()["chunks_indexed"] == 1
    assert MethodCard.from_dict(payload["method_card"]).approved is True
    json.dumps(payload)


def test_source_type_labels_are_closed_registry() -> None:
    assert SOURCE_TYPE_LABELS == {
        "foundation_textbook",
        "method_textbook",
        "primary_paper",
        "software_documentation",
        "internal_note",
    }
    assert DEFAULT_SOURCE_TYPE == "internal_note"
