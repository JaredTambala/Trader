from __future__ import annotations

from pathlib import Path

from pypdf import PdfWriter

from trader_research.knowledge.citation_validation import validate_citations
from trader_research.knowledge.embeddings import DeterministicEmbeddingProvider, RuntimeConfiguredEmbeddingProvider
from trader_research.knowledge.extractors import extract_text
from trader_research.knowledge.ingestion import ingest_documents
from trader_research.knowledge.retrieval import retrieve_evidence
from trader_research.knowledge.sources import register_source


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
    assert citation.ok is True
    assert citation.data["citation_validation_report"]["valid"] is True
    assert bad_citation.ok is False
    assert bad_citation.errors[0]["code"] == "citation_validation_failed"


def test_pdf_extraction_reports_scanned_page_warning(tmp_path: Path) -> None:
    pdf_path = tmp_path / "blank.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    with pdf_path.open("wb") as handle:
        writer.write(handle)

    extracted = extract_text(pdf_path)

    assert extracted.sections == tuple()
    assert extracted.warnings == ("page 1 has no extractable text; OCR is disabled",)


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
