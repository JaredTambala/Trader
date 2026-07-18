from __future__ import annotations

from pathlib import Path

import pytest
from pypdf import PdfWriter

from trader_research.knowledge.citation_validation import validate_citations
from trader_research.knowledge.embeddings import (
    DeterministicEmbeddingProvider,
    EmbeddingRequestError,
    RuntimeConfiguredEmbeddingProvider,
)
from trader_research.knowledge import extractors
from trader_research.knowledge.extractors import ExtractedDocument, ExtractedSection, extract_text
from trader_research.knowledge.ingestion import ingest_documents
from trader_research.knowledge.retrieval import get_evidence_chunks, retrieve_evidence
from trader_research.knowledge.sources import register_source
from trader_research.knowledge.store import JsonKnowledgeStore


FIXTURE = Path("tests/fixtures/knowledge/sma_method.md")


def test_source_registration_detects_duplicates_and_rejects_bad_paths(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    source_copy = tmp_path / "source_copy.md"
    source_copy.write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")

    first = register_source(
        artifact_root=artifact_root,
        path=FIXTURE,
        title="SMA Source",
        source_type="method_textbook",
        topics=("indicators",),
        method_families=("indicator",),
    )
    second = register_source(
        artifact_root=artifact_root,
        path=source_copy,
        title="SMA Source Copy",
        source_type="internal_note",
        allowed_roots=(tmp_path,),
    )
    unsupported = tmp_path / "source.csv"
    unsupported.write_text("bad,type\n", encoding="utf-8")
    rejected_type = register_source(
        artifact_root=artifact_root,
        path=unsupported,
        title="Bad Source",
        source_type="internal_note",
        allowed_roots=(tmp_path,),
    )
    rejected_source_type = register_source(
        artifact_root=artifact_root,
        path=source_copy,
        title="Bad Label",
        source_type="blog_post",
        allowed_roots=(tmp_path,),
    )
    outside_root = register_source(
        artifact_root=artifact_root,
        path=FIXTURE,
        title="Outside",
        allowed_roots=(tmp_path / "allowed",),
    )

    assert first.ok is True
    assert second.ok is True
    assert second.data["duplicate_source_ids"]
    assert rejected_type.ok is False
    assert rejected_type.errors[0]["code"] == "source_registration_error"
    assert rejected_source_type.ok is False
    assert "unsupported source_type" in rejected_source_type.errors[0]["message"]
    assert outside_root.ok is False


def test_ingest_retrieve_and_validate_citations(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    registered = register_source(
        artifact_root=artifact_root,
        path=FIXTURE,
        title="SMA Source",
        source_type="primary_paper",
        topics=("indicators",),
        method_families=("indicator",),
    )
    source_id = registered.data["knowledge_source_manifest"]["source_id"]
    assert registered.data["knowledge_source_manifest"]["source_type"] == "primary_paper"
    ingested = ingest_documents(
        artifact_root=artifact_root,
        source_ids=(source_id,),
        embedding_provider=DeterministicEmbeddingProvider(),
    )
    retrieved = retrieve_evidence(
        artifact_root=artifact_root,
        query="moving average warmup observations",
        source_ids=(source_id,),
        embedding_provider=DeterministicEmbeddingProvider(),
        top_k=1,
    )
    result = retrieved.data["evidence_retrieval_report"]["results"][0]
    dereferenced = get_evidence_chunks(
        artifact_root=artifact_root,
        chunk_ids=(result["chunk_id"],),
        source_id=source_id,
    )
    truncated = get_evidence_chunks(
        artifact_root=artifact_root,
        chunk_ids=(result["chunk_id"],),
        max_chars_per_chunk=12,
    )
    missing_chunk = get_evidence_chunks(
        artifact_root=artifact_root,
        chunk_ids=("missing_chunk",),
    )
    source_mismatch = get_evidence_chunks(
        artifact_root=artifact_root,
        chunk_ids=(result["chunk_id"],),
        source_id="other_source",
    )
    oversized = get_evidence_chunks(
        artifact_root=artifact_root,
        chunk_ids=tuple(f"chunk_{index}" for index in range(26)),
    )
    citation = validate_citations(
        artifact_root=artifact_root,
        artifact={
            "knowledge_evidence_refs": [
                {
                    "source_id": result["source_id"],
                    "chunk_id": result["chunk_id"],
                    "locator": result["locator"],
                    "method_card_id": "method_card_sma_seed_v1",
                }
            ]
        },
    )
    bad_citation = validate_citations(
        artifact_root=artifact_root,
        artifact={"knowledge_evidence_refs": [{"source_id": source_id, "chunk_id": "missing"}]},
    )

    assert ingested.ok is True
    assert ingested.data["knowledge_ingestion_report"]["chunks_indexed"] >= 1
    assert retrieved.ok is True
    assert result["source_id"] == source_id
    assert result["retrieval_scores"]["combined_rank"] == 1
    assert result["source_status"] == "registered"
    assert dereferenced.ok is True
    dereferenced_chunk = dereferenced.data["evidence_chunk_dereference_report"]["chunks"][0]
    assert result["chunk_id"].startswith("knowledge_evidence_unit_")
    assert dereferenced_chunk["evidence_unit_id"] == result["chunk_id"]
    assert dereferenced_chunk["chunker_version"] == "evidence-unit-v1"
    assert "simple moving average computes the arithmetic mean" in dereferenced_chunk["text"]
    assert "warmup observations exist" in dereferenced_chunk["text"]
    assert dereferenced_chunk["hash_verified"] is True
    assert dereferenced_chunk["text_truncated"] is False
    assert truncated.data["chunks"][0]["text"] == dereferenced_chunk["text"][:12]
    assert truncated.data["chunks"][0]["text_truncated"] is True
    assert missing_chunk.ok is False
    assert missing_chunk.errors[0]["code"] == "chunk_dereference_error"
    assert missing_chunk.data["missing_chunk_ids"] == ["missing_chunk"]
    assert source_mismatch.ok is False
    assert source_mismatch.data["source_mismatch_chunk_ids"] == [result["chunk_id"]]
    assert oversized.ok is False
    assert oversized.errors[0]["code"] == "validation_error"
    assert citation.ok is True
    assert citation.data["citation_validation_report"]["valid"] is True
    assert bad_citation.ok is False
    assert bad_citation.errors[0]["code"] == "citation_validation_failed"


def test_force_ingestion_replaces_chunks_without_loading_legacy_payloads(
    tmp_path: Path,
    monkeypatch,
) -> None:
    artifact_root = tmp_path / "artifacts"
    store = JsonKnowledgeStore(artifact_root)
    registered = register_source(
        artifact_root=artifact_root,
        path=FIXTURE,
        title="Legacy SMA Source",
        source_type="method_textbook",
        knowledge_store=store,
    )
    source_id = registered.data["knowledge_source_manifest"]["source_id"]

    def reject_legacy_load(_source_id: str):
        raise ValueError("knowledge evidence unit must be regenerated with schema_version 2")

    monkeypatch.setattr(store, "load_chunks", reject_legacy_load)

    result = ingest_documents(
        artifact_root=artifact_root,
        source_ids=(source_id,),
        embedding_provider=DeterministicEmbeddingProvider(),
        force=True,
        knowledge_store=store,
    )

    assert result.ok is True
    assert result.data["knowledge_ingestion_report"]["source_ids"] == [source_id]
    assert result.data["knowledge_ingestion_report"]["evidence_units_indexed"] >= 1


def test_pdf_extraction_reports_scanned_page_warning(tmp_path: Path) -> None:
    pdf_path = tmp_path / "blank.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    with pdf_path.open("wb") as handle:
        writer.write(handle)

    extracted = extract_text(pdf_path)

    assert extracted.sections == tuple()
    assert extracted.warnings == ("page 1 has no extractable text; OCR is disabled",)


def test_extraction_replaces_invalid_unicode_surrogates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_path = tmp_path / "invalid.txt"
    source_path.write_text("placeholder", encoding="utf-8")
    monkeypatch.setattr(
        extractors,
        "_extract_plain_text",
        lambda _path: ExtractedDocument(
            sections=(ExtractedSection(text="valid \ud835 text", section="invalid"),)
        ),
    )

    extracted = extract_text(source_path)

    assert extracted.sections[0].text == "valid \ufffd text"
    assert extracted.warnings == (
        "replaced 1 invalid Unicode surrogate code points during text extraction",
    )


def test_ingestion_requires_configured_real_embedding_provider_by_default(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    registered = register_source(
        artifact_root=artifact_root,
        path=FIXTURE,
        title="SMA Source",
        source_type="internal_note",
    )
    source_id = registered.data["knowledge_source_manifest"]["source_id"]

    result = ingest_documents(
        artifact_root=artifact_root,
        source_ids=(source_id,),
        embedding_provider=RuntimeConfiguredEmbeddingProvider(env={}),
    )

    assert result.ok is False
    assert result.errors[0]["code"] == "embedding_configuration_error"
    assert "TRADER_RESEARCH_EMBEDDINGS_PROVIDER" in result.errors[0]["message"]


def test_force_ingestion_stages_embeddings_before_replacing_active_evidence(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    source_path = tmp_path / "method.md"
    source_path.write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    store = JsonKnowledgeStore(artifact_root)
    registered = register_source(
        artifact_root=artifact_root,
        path=source_path,
        title="Staged SMA Source",
        source_type="method_textbook",
        allowed_roots=(tmp_path,),
        knowledge_store=store,
    )
    source_id = registered.data["knowledge_source_manifest"]["source_id"]
    initial = ingest_documents(
        artifact_root=artifact_root,
        source_ids=(source_id,),
        embedding_provider=DeterministicEmbeddingProvider(),
        knowledge_store=store,
    )
    active_before = store.load_chunks(source_id)
    source_path.write_text("Replacement Method: entirely new source text.", encoding="utf-8")

    class FailingEmbeddingProvider:
        provider = "test"
        model = "always-fails"
        version = "1"

        def embed(self, text: str) -> tuple[float, ...]:
            raise EmbeddingRequestError(f"embedding failed for {len(text)} chars")

    failed = ingest_documents(
        artifact_root=artifact_root,
        source_ids=(source_id,),
        embedding_provider=FailingEmbeddingProvider(),
        force=True,
        knowledge_store=store,
    )

    assert initial.ok is True
    assert failed.ok is False
    assert failed.errors[0]["code"] == "embedding_index_error"
    assert store.load_chunks(source_id) == active_before
