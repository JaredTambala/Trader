from __future__ import annotations

import json

import pytest

from trader_research.knowledge.chunking import chunk_sections
from trader_research.knowledge.domain import (
    DEFAULT_SOURCE_TYPE,
    EvidenceBackedField,
    EvidenceReference,
    KnowledgeChunk,
    KnowledgeEmbeddingManifest,
    KnowledgeIngestionReport,
    KnowledgeSourceManifest,
    MethodCard,
    MethodologyCandidate,
    MethodologyCandidateValidationReport,
    MethodologyEvidencePacket,
    MethodologyFieldExtractionReport,
    RichMethodCard,
    RICH_METHOD_CARD_FORMAT,
    SOURCE_TYPE_LABELS,
)
from trader_research.knowledge.extractors import ExtractedSection


def _evidence_ref() -> EvidenceReference:
    return EvidenceReference(
        source_id="knowledge_source_demo",
        chunk_id="knowledge_chunk_demo",
        locator={"page": 12, "heading": "Pairs Trading"},
        claim="source describes the methodology field",
    )


def _field(value: object) -> EvidenceBackedField:
    return EvidenceBackedField(value=value, evidence_refs=(_evidence_ref(),), confidence=0.8, quality="direct")


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


def test_chunking_sanitizes_nul_bytes_before_hashing() -> None:
    source = KnowledgeSourceManifest(
        source_id="knowledge_source_nul",
        title="NUL Source",
        source_type="internal_note",
        path="tests/fixtures/knowledge/quant_notes.txt",
        file_hash="abc123",
        file_size_bytes=42,
    )

    chunks = chunk_sections(
        source,
        (ExtractedSection(text="alpha\x00beta", section="demo", heading="demo"),),
    )

    assert len(chunks) == 1
    assert chunks[0].text == "alpha beta"
    assert "\x00" not in chunks[0].text
    assert chunks[0].text_hash


def test_methodology_candidate_round_trips_rich_nullable_fields() -> None:
    candidate = MethodologyCandidate(
        methodology_candidate_id="methodology_candidate_pairs_demo",
        title="Cointegration pairs trading",
        families=("statistical_arbitrage",),
        status="extracted",
        source_ids=("knowledge_source_demo",),
        chunk_ids=("knowledge_chunk_demo",),
        candidate_spans=({"chunk_id": "knowledge_chunk_demo", "start": 20, "end": 220},),
        core_fields={
            "identity": {
                "method_name": _field("Cointegration pairs trading"),
                "limitations": EvidenceBackedField(),
            },
            "method_specification": {
                "algorithm_steps": _field(("estimate hedge ratio", "test residual stationarity")),
            },
        },
        extension_fields={
            "statistical_arbitrage": {
                "cointegration_test": _field("Engle-Granger"),
                "entry_zscore": EvidenceBackedField(),
            }
        },
        lineage={"retrieval_id": "evidence_retrieval_demo"},
    )

    payload = candidate.to_dict()

    assert payload["artifact_type"] == "methodology_candidate"
    assert payload["core_fields"]["identity"]["limitations"]["value"] is None
    assert MethodologyCandidate.from_dict(payload).to_dict() == payload
    json.dumps(payload)


def test_methodology_evidence_packet_round_trips_role_evidence() -> None:
    packet = MethodologyEvidencePacket(
        evidence_packet_id="methodology_evidence_packet_demo",
        methodology_candidate_id="methodology_candidate_pairs_demo",
        family="statistical_arbitrage",
        readiness_goal="signal",
        status="assembled",
        candidate_ref={"uri": "research://postgres/methodology_candidate/methodology_candidate_pairs_demo"},
        source_ids=("knowledge_source_demo",),
        chunk_ids=("knowledge_chunk_demo",),
        role_evidence=(
            {
                "role_id": "spread_definition",
                "status": "found",
                "required": True,
                "field_paths": ["extension_fields.statistical_arbitrage.spread_definition"],
                "chunks": [
                    {
                        "source_id": "knowledge_source_demo",
                        "chunk_id": "knowledge_chunk_demo",
                        "locator": {"page": 12},
                        "text_hash": "abc123",
                    }
                ],
            },
        ),
        diagnostics={"required_roles": ["spread_definition"]},
    )

    payload = packet.to_dict()

    assert payload["artifact_type"] == "methodology_evidence_packet"
    assert MethodologyEvidencePacket.from_dict(payload).to_dict() == payload
    json.dumps(payload)


def test_rich_method_card_round_trips_and_projects_to_shallow_card() -> None:
    card = RichMethodCard(
        method_card_id="method_card_draft_pairs_demo",
        method_id="cointegration_pairs",
        title="Cointegration pairs trading",
        family="statistical_arbitrage",
        status="draft",
        assumptions=("residual spread can mean revert",),
        inputs=("two or more aligned price series",),
        outputs=("spread signal",),
        failure_modes=("structural break",),
        evidence_refs=(_evidence_ref(),),
        core_fields={
            "signal_decision_logic": {
                "entry_rules": _field("enter when spread z-score exceeds the threshold"),
            }
        },
        extension_fields={
            "statistical_arbitrage": {
                "hedge_ratio_method": _field("regression hedge ratio"),
            }
        },
        source_methodology_candidate_id="methodology_candidate_pairs_demo",
        validation_refs=({"artifact_type": "citation_validation_report", "artifact_id": "citation_demo"},),
    )

    payload = card.to_dict()
    parsed = RichMethodCard.from_dict(payload)
    shallow = parsed.to_method_card()

    assert payload["artifact_type"] == "method_card_draft"
    assert payload["card_format"] == RICH_METHOD_CARD_FORMAT
    assert parsed.to_dict() == payload
    assert shallow.to_dict()["method_card_id"] == card.method_card_id
    assert "core_fields" not in shallow.to_dict()
    json.dumps(payload)


def test_methodology_extraction_and_validation_reports_round_trip_json() -> None:
    extraction = MethodologyFieldExtractionReport(
        extraction_id="methodology_field_extraction_demo",
        methodology_candidate_id="methodology_candidate_demo",
        status="extracted",
        evidence_packet_id="methodology_evidence_packet_demo",
        candidate_ref={"uri": "research://postgres/methodology_candidate/methodology_candidate_demo"},
        source_ids=("knowledge_source_demo",),
        chunk_ids=("knowledge_chunk_demo",),
        populated_field_count=1,
        populated_fields=("identity.method_name",),
    )
    validation = MethodologyCandidateValidationReport(
        validation_id="methodology_candidate_validation_demo",
        methodology_candidate_id="methodology_candidate_demo",
        status="passed",
        valid=True,
        checked_refs=(_evidence_ref().to_dict(),),
        field_summary={"populated_field_count": 1},
        source_summary={"source_ids": ["knowledge_source_demo"]},
        readiness_summary={"descriptive": {"status": "passed"}},
    )

    extraction_payload = extraction.to_dict()
    validation_payload = validation.to_dict()

    assert MethodologyFieldExtractionReport.from_dict(extraction_payload).to_dict() == extraction_payload
    assert MethodologyCandidateValidationReport.from_dict(validation_payload).to_dict() == validation_payload
    json.dumps({"extraction": extraction_payload, "validation": validation_payload})


def test_populated_methodology_field_requires_evidence() -> None:
    with pytest.raises(ValueError, match="requires evidence_refs"):
        EvidenceBackedField(value="unsupported claim")


def test_null_methodology_field_does_not_require_evidence() -> None:
    field = EvidenceBackedField()

    assert field.to_dict()["value"] is None
    assert field.to_dict()["evidence_refs"] == []


@pytest.mark.parametrize(
    ("block", "field_name", "value"),
    (
        ("technical_indicators", "lookback_period", 14),
        ("options_derivatives", "legs", ("long call", "long put")),
        ("statistical_arbitrage", "cointegration_test", "Engle-Granger"),
        ("sentiment_alternative_data", "commodity_mapping", {"WTI": "crude oil"}),
    ),
)
def test_methodology_candidate_supports_domain_extension_blocks(
    block: str,
    field_name: str,
    value: object,
) -> None:
    candidate = MethodologyCandidate(
        methodology_candidate_id=f"methodology_candidate_{block}",
        title=f"{block} candidate",
        families=(block,),
        extension_fields={block: {field_name: _field(value)}},
    )

    payload = candidate.to_dict()
    expected_value = list(value) if isinstance(value, tuple) else value

    assert set(payload["extension_fields"]) == {block}
    assert payload["extension_fields"][block][field_name]["value"] == expected_value


def test_methodology_candidate_rejects_unknown_field_groups_and_names() -> None:
    with pytest.raises(ValueError, match="unsupported core_fields group"):
        MethodologyCandidate(
            methodology_candidate_id="methodology_candidate_bad_group",
            title="Bad group",
            families=("technical_indicators",),
            core_fields={"unknown_group": {}},
        )

    with pytest.raises(ValueError, match="unsupported extension_fields field"):
        MethodologyCandidate(
            methodology_candidate_id="methodology_candidate_bad_field",
            title="Bad field",
            families=("technical_indicators",),
            extension_fields={"technical_indicators": {"delta": _field("not a technical field")}},
        )
