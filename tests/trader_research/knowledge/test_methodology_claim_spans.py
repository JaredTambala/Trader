"""Contracts for claim-span isolation and multi-unit field synthesis.

Subject: Method-specific claim selection when evidence units contain adjacent or distributed methods.
Level: Offline application workflow contract.
Collaborators: Knowledge domain values, JSON store, evidence assembly, extraction, and validation.
Guarantees: Accepted spans stay target-bound and combine across units without neighboring-method leakage.
Non-goals: Retrieval ranking, method-card lifecycle, computational execution, Postgres, or model reasoning.
"""

from __future__ import annotations

from dataclasses import replace
import hashlib
from pathlib import Path

from trader_research.foundation.artifacts import InMemoryResearchArtifactStore
from trader_research.governance.artifacts import (
    DOMAIN_OWNER_BY_ARTIFACT_TYPE,
    METHODOLOGY_CANDIDATE,
)
from trader_research.knowledge.domain import (
    EvidenceBackedField,
    KnowledgeChunk,
    KnowledgeSourceManifest,
    MethodologyCandidate,
)
from trader_research.knowledge.evidence_assembly import assemble_methodology_evidence
from trader_research.knowledge.methodology_extraction import extract_methodology_fields
from trader_research.knowledge.methodology_validation import (
    validate_methodology_candidate,
)
from trader_research.knowledge.store import JsonKnowledgeStore


def test_shared_evidence_unit_supports_distinct_method_claim_spans(
    tmp_path: Path,
) -> None:
    """One evidence unit supplies separate target-bound spans to adjacent methods."""
    artifact_root = tmp_path / "artifacts"
    store = JsonKnowledgeStore(artifact_root)
    artifact_store = InMemoryResearchArtifactStore()
    source = KnowledgeSourceManifest(
        source_id="knowledge_source_shared_indicator_unit",
        title="Shared Indicator Evidence",
        source_type="method_textbook",
        path="tests/fixtures/knowledge/technical_notes.txt",
        file_hash="shared-indicator-unit",
        file_size_bytes=512,
        topics=("technical indicators",),
        method_families=("technical_indicators",),
    )
    text = (
        "Bollinger Bands: compute bands around a moving average from a price series; "
        "buy when price crosses the lower band and sell at the upper band. "
        "Moving Average Oscillator: compute short and long moving averages from a price series; "
        "buy when the short average crosses the long average from below and sell when it crosses from above."
    )
    chunk = KnowledgeChunk(
        chunk_id="knowledge_evidence_unit_shared_indicators",
        source_id=source.source_id,
        ordinal=0,
        text=text,
        text_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        locator={
            "source_id": source.source_id,
            "page": 182,
            "heading": "Technical rules",
        },
        topics=source.topics,
        method_families=source.method_families,
        detected_labels=("Bollinger Bands", "Moving Average Oscillator"),
    )
    store.save_source(source)
    store.replace_chunks(source.source_id, (chunk,))

    candidates = (
        MethodologyCandidate(
            methodology_candidate_id="methodology_candidate_shared_bollinger",
            title="Bollinger Bands",
            families=("technical_indicators",),
            source_ids=(source.source_id,),
            chunk_ids=(chunk.chunk_id,),
            method_identity={
                "canonical_name": "Bollinger Bands",
                "source_name": "Bollinger Bands",
                "identity_evidence_unit_ids": [chunk.chunk_id],
            },
        ),
        MethodologyCandidate(
            methodology_candidate_id="methodology_candidate_shared_oscillator",
            title="Moving Average Oscillator",
            families=("technical_indicators",),
            source_ids=(source.source_id,),
            chunk_ids=(chunk.chunk_id,),
            method_identity={
                "canonical_name": "Moving Average Oscillator",
                "source_name": "Moving Average Oscillator",
                "identity_evidence_unit_ids": [chunk.chunk_id],
            },
        ),
    )
    for candidate in candidates:
        artifact_store.save_artifact(
            domain_owner=DOMAIN_OWNER_BY_ARTIFACT_TYPE[METHODOLOGY_CANDIDATE],
            producer_tool="test_methodology_fixture",
            artifact_type=METHODOLOGY_CANDIDATE,
            artifact_id=candidate.methodology_candidate_id,
            payload=candidate.to_dict(),
            status=candidate.status,
        )

    assembled = [
        assemble_methodology_evidence(
            artifact_root=artifact_root,
            methodology_candidate_id=candidate.methodology_candidate_id,
            readiness_goal="signal",
            neighbor_radius=0,
            knowledge_store=store,
            artifact_store=artifact_store,
        )
        for candidate in candidates
    ]

    assert all(result.ok for result in assembled)
    for result, candidate in zip(assembled, candidates, strict=True):
        packet = result.data["methodology_evidence_packet"]
        assert packet["chunk_ids"] == [chunk.chunk_id]
        accepted_spans = [
            span
            for role in packet["role_evidence"]
            for chunk_ref in role["chunks"]
            for span in chunk_ref["claim_spans"]
        ]
        assert accepted_spans
        assert {span["target_method"] for span in accepted_spans} == {candidate.title}

    oscillator_packet = assembled[1].data["methodology_evidence_packet"]
    oscillator_signal = next(
        role
        for role in oscillator_packet["role_evidence"]
        if role["role_id"] == "signal_logic"
    )
    oscillator_signal_text = " ".join(
        span["text"]
        for ref in oscillator_signal["chunks"]
        for span in ref["claim_spans"]
    )
    assert "short average crosses" in oscillator_signal_text
    assert "lower band" not in oscillator_signal_text

    extracted = extract_methodology_fields(
        artifact_root=artifact_root,
        evidence_packet=oscillator_packet,
        knowledge_store=store,
        artifact_store=artifact_store,
    )
    assert extracted.ok is True
    extracted_candidate = extracted.data["methodology_candidate"]
    technical_fields = extracted_candidate["extension_fields"]["technical_indicators"]
    assert "overbought_threshold" not in technical_fields
    assert "oversold_threshold" not in technical_fields
    signal_field = extracted_candidate["core_fields"]["signal_decision_logic"][
        "signal_definition"
    ]
    assert all(
        ref["claim_span"]["target_method"] == "Moving Average Oscillator"
        for ref in signal_field["evidence_refs"]
    )

    stale_candidate = MethodologyCandidate.from_dict(extracted_candidate)
    stale_extensions = {
        group: dict(fields)
        for group, fields in stale_candidate.extension_fields.items()
    }
    stale_extensions["technical_indicators"]["overbought_threshold"] = (
        EvidenceBackedField(
            value="stale neighboring-method threshold",
            evidence_refs=stale_candidate.core_fields["signal_decision_logic"][
                "signal_definition"
            ].evidence_refs,
            quality="role_evidence:threshold_semantics",
        )
    )
    stale_candidate = replace(stale_candidate, extension_fields=stale_extensions)
    artifact_store.save_artifact(
        domain_owner=DOMAIN_OWNER_BY_ARTIFACT_TYPE[METHODOLOGY_CANDIDATE],
        producer_tool="test_methodology_fixture",
        artifact_type=METHODOLOGY_CANDIDATE,
        artifact_id=stale_candidate.methodology_candidate_id,
        payload=stale_candidate.to_dict(),
        status=stale_candidate.status,
    )
    reextracted = extract_methodology_fields(
        artifact_root=artifact_root,
        evidence_packet=oscillator_packet,
        knowledge_store=store,
        artifact_store=artifact_store,
    )
    assert (
        "overbought_threshold"
        not in reextracted.data["methodology_candidate"]["extension_fields"][
            "technical_indicators"
        ]
    )

    validated = validate_methodology_candidate(
        artifact_root=artifact_root,
        extraction_report_id=reextracted.data["methodology_field_extraction_report"][
            "extraction_id"
        ],
        knowledge_store=store,
        artifact_store=artifact_store,
    )
    assert validated.ok is True


def test_real_pdf_shaped_oscillator_evidence_rejects_neighbor_method_claims(
    tmp_path: Path,
) -> None:
    """Fragmented PDF evidence excludes Bollinger and RSI claims from oscillator fields."""
    artifact_root = tmp_path / "artifacts"
    store = JsonKnowledgeStore(artifact_root)
    artifact_store = InMemoryResearchArtifactStore()
    source = KnowledgeSourceManifest(
        source_id="knowledge_source_real_pdf_shaped_oscillator",
        title="Algorithmic Trading Technical Rules Excerpt",
        source_type="method_textbook",
        path="tests/fixtures/knowledge/technical_notes.txt",
        file_hash="real-pdf-shaped-oscillator",
        file_size_bytes=1024,
        topics=("technical indicators",),
        method_families=("technical_indicators",),
    )
    texts = (
        "Bollinger Bands: compute upper and lower bands around a moving average.",
        "t = P(m) + 2 sigma(m), the upper band, then sell;",
        (
            "t - 2 sigma(m), the lower band, then buy; Moving Average Oscillator:"
            "The moving average oscillator rule requires computing two moving averages of short and long time spans."
        ),
        (
            "The upward trend is signaled when the short moving average intersects from below the long average. "
            "RSI Oscillator: Another oscillator measures the strength of price movement and defines overbought and "
            "oversold regions."
        ),
    )
    chunks = tuple(
        KnowledgeChunk(
            chunk_id=f"knowledge_evidence_unit_real_pdf_{ordinal}",
            source_id=source.source_id,
            ordinal=ordinal,
            text=text,
            text_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            locator={
                "source_id": source.source_id,
                "page": 182,
                "part": ordinal,
                "parent_section_id": "page-182",
                "paragraph_index": 0,
            },
            topics=source.topics,
            method_families=source.method_families,
            parent_section_id="page-182",
            paragraph_index=0,
            detected_labels=("Bollinger Bands",) if ordinal == 0 else tuple(),
        )
        for ordinal, text in enumerate(texts)
    )
    store.save_source(source)
    store.replace_chunks(source.source_id, chunks)
    candidate = MethodologyCandidate(
        methodology_candidate_id="methodology_candidate_real_pdf_oscillator",
        title="Moving Average Oscillator",
        families=("technical_indicators",),
        source_ids=(source.source_id,),
        chunk_ids=tuple(chunk.chunk_id for chunk in chunks),
        method_identity={
            "canonical_name": "Moving Average Oscillator",
            "source_name": "Moving Average Oscillator",
            "identity_evidence_unit_ids": [chunks[2].chunk_id],
        },
    )
    artifact_store.save_artifact(
        domain_owner=DOMAIN_OWNER_BY_ARTIFACT_TYPE[METHODOLOGY_CANDIDATE],
        producer_tool="test_methodology_fixture",
        artifact_type=METHODOLOGY_CANDIDATE,
        artifact_id=candidate.methodology_candidate_id,
        payload=candidate.to_dict(),
        status=candidate.status,
    )

    assembled = assemble_methodology_evidence(
        artifact_root=artifact_root,
        methodology_candidate_id=candidate.methodology_candidate_id,
        readiness_goal="implementation",
        neighbor_radius=3,
        max_chunks_per_role=8,
        knowledge_store=store,
        artifact_store=artifact_store,
    )
    packet = assembled.data["methodology_evidence_packet"]
    signal_role = next(
        role for role in packet["role_evidence"] if role["role_id"] == "signal_logic"
    )
    accepted_signal_text = " ".join(
        span["text"]
        for chunk_ref in signal_role["chunks"]
        for span in chunk_ref["claim_spans"]
    )

    assert "short moving average intersects" in accepted_signal_text
    assert "upper band" not in accepted_signal_text
    assert "lower band" not in accepted_signal_text
    assert "RSI Oscillator" not in accepted_signal_text
    threshold_role = next(
        role
        for role in packet["role_evidence"]
        if role["role_id"] == "threshold_semantics"
    )
    assert any(
        "RSI Oscillator" in span["text"]
        for chunk_ref in (*threshold_role["chunks"], *threshold_role["rejected_chunks"])
        for span in chunk_ref["rejected_claim_spans"]
    )

    extracted = extract_methodology_fields(
        artifact_root=artifact_root,
        evidence_packet=packet,
        knowledge_store=store,
        artifact_store=artifact_store,
    )
    technical = extracted.data["methodology_candidate"]["extension_fields"][
        "technical_indicators"
    ]
    assert "overbought_threshold" not in technical
    assert "oversold_threshold" not in technical


def test_field_synthesis_preserves_claim_spans_across_evidence_units(
    tmp_path: Path,
) -> None:
    """Field synthesis combines distributed claims while preserving each exact citation span."""
    artifact_root = tmp_path / "artifacts"
    store = JsonKnowledgeStore(artifact_root)
    artifact_store = InMemoryResearchArtifactStore()
    source = KnowledgeSourceManifest(
        source_id="knowledge_source_multi_span_method",
        title="Multi-Span Method Source",
        source_type="method_textbook",
        path="tests/fixtures/knowledge/technical_notes.txt",
        file_hash="multi-span-method",
        file_size_bytes=256,
        topics=("technical indicators",),
        method_families=("technical_indicators",),
    )
    texts = (
        "Cascade Difference: this indicator method computes a short moving average from a price series.",
        "Cascade Difference subtracts a long moving average from the short moving average.",
    )
    chunks = tuple(
        KnowledgeChunk(
            chunk_id=f"knowledge_evidence_unit_multi_span_{ordinal}",
            source_id=source.source_id,
            ordinal=ordinal,
            text=text,
            text_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            locator={"source_id": source.source_id, "page": 10, "part": ordinal},
            topics=source.topics,
            method_families=source.method_families,
            detected_labels=("Cascade Difference",) if ordinal == 0 else tuple(),
        )
        for ordinal, text in enumerate(texts)
    )
    store.save_source(source)
    store.replace_chunks(source.source_id, chunks)
    candidate = MethodologyCandidate(
        methodology_candidate_id="methodology_candidate_multi_span_method",
        title="Cascade Difference",
        families=("technical_indicators",),
        source_ids=(source.source_id,),
        chunk_ids=tuple(chunk.chunk_id for chunk in chunks),
        method_identity={
            "canonical_name": "Cascade Difference",
            "source_name": "Cascade Difference",
            "identity_evidence_unit_ids": [chunks[0].chunk_id],
        },
    )
    artifact_store.save_artifact(
        domain_owner=DOMAIN_OWNER_BY_ARTIFACT_TYPE[METHODOLOGY_CANDIDATE],
        producer_tool="test_methodology_fixture",
        artifact_type=METHODOLOGY_CANDIDATE,
        artifact_id=candidate.methodology_candidate_id,
        payload=candidate.to_dict(),
        status=candidate.status,
    )
    assembled = assemble_methodology_evidence(
        artifact_root=artifact_root,
        methodology_candidate_id=candidate.methodology_candidate_id,
        readiness_goal="implementation",
        neighbor_radius=1,
        knowledge_store=store,
        artifact_store=artifact_store,
    )
    extracted = extract_methodology_fields(
        artifact_root=artifact_root,
        evidence_packet=assembled.data["methodology_evidence_packet"],
        knowledge_store=store,
        artifact_store=artifact_store,
    )

    assert assembled.ok is True
    algorithm = extracted.data["methodology_candidate"]["core_fields"][
        "method_specification"
    ]["algorithm_steps"]
    assert "short moving average" in algorithm["value"]
    assert "long moving average" in algorithm["value"]
    assert {ref["chunk_id"] for ref in algorithm["evidence_refs"]} == {
        chunk.chunk_id for chunk in chunks
    }
    assert all(ref["claim_span"] is not None for ref in algorithm["evidence_refs"])
