from __future__ import annotations

import hashlib
from pathlib import Path

from trader_research.artifact_store import InMemoryResearchArtifactStore
from trader_research.domain import (
    METHODOLOGY_CANDIDATE,
    METHODOLOGY_CANDIDATE_VALIDATION_REPORT,
    METHODOLOGY_EVIDENCE_PACKET,
    METHODOLOGY_FIELD_EXTRACTION_REPORT,
)
from trader_research.knowledge.domain import (
    EvidenceBackedField,
    EvidenceReference,
    KnowledgeChunk,
    KnowledgeSourceManifest,
    MethodologyCandidate,
)
from trader_research.knowledge.embeddings import DeterministicEmbeddingProvider
from trader_research.knowledge.index import index_chunks
from trader_research.knowledge.evidence_assembly import assemble_methodology_evidence
from trader_research.knowledge.evidence_profiles import profile_for_family
from trader_research.knowledge.methodology_candidates import discover_methodology_candidates
from trader_research.knowledge.methodology_extraction import (
    extract_methodology_fields,
    validate_methodology_candidate,
)
from trader_research.knowledge.store import JsonKnowledgeStore


def _store_with_pairs_chunks(tmp_path: Path, *, source_type: str = "method_textbook"):
    artifact_root = tmp_path / "artifacts"
    store = JsonKnowledgeStore(artifact_root)
    source = KnowledgeSourceManifest(
        source_id="knowledge_source_pairs",
        title="Pairs Trading Source",
        source_type=source_type,
        path="tests/fixtures/knowledge/quant_notes.txt",
        file_hash="abc123",
        file_size_bytes=42,
        topics=("statistical arbitrage",),
        method_families=("statistical_arbitrage",),
    )
    chunks = (
        _chunk(source, 0, "Background context for market-neutral trading.", "Pairs Trading"),
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
        _chunk(source, 0, "Compute unrelated average portfolio sums from active trades.", "Page 80"),
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
        _chunk(source, 2, "A signal occurs when price crosses a moving average rule threshold.", "Page 182"),
        _chunk(source, 3, "Risk includes noisy regimes and whipsaw failure modes.", "Page 183"),
        _chunk(source, 4, "Another exercise says compute average sums and ratios for moving portfolios.", "Page 225"),
    )
    store.save_source(source)
    store.replace_chunks(source.source_id, chunks)
    return artifact_root, store, source, chunks


def _chunk(source: KnowledgeSourceManifest, ordinal: int, text: str, heading: str) -> KnowledgeChunk:
    text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return KnowledgeChunk(
        chunk_id=f"knowledge_chunk_pairs_{ordinal}",
        source_id=source.source_id,
        ordinal=ordinal,
        text=text,
        text_hash=text_hash,
        locator={"source_id": source.source_id, "heading": heading, "page": ordinal + 1},
        topics=source.topics,
        method_families=source.method_families,
    )


def test_discovery_creates_deterministic_candidate_from_source_scope(tmp_path: Path) -> None:
    artifact_root, store, source, chunks = _store_with_pairs_chunks(tmp_path)
    artifact_store = InMemoryResearchArtifactStore()

    result = discover_methodology_candidates(
        artifact_root=artifact_root,
        source_ids=(source.source_id,),
        method_families=("statistical_arbitrage",),
        neighbor_radius=1,
        max_candidates=3,
        knowledge_store=store,
        artifact_store=artifact_store,
        embedding_provider=DeterministicEmbeddingProvider(),
    )
    repeated = discover_methodology_candidates(
        artifact_root=artifact_root,
        source_ids=(source.source_id,),
        method_families=("statistical_arbitrage",),
        neighbor_radius=1,
        max_candidates=3,
        knowledge_store=store,
        artifact_store=artifact_store,
        embedding_provider=DeterministicEmbeddingProvider(),
    )

    assert result.ok is True
    candidate = result.data["methodology_candidates"][0]
    assert candidate["artifact_type"] == METHODOLOGY_CANDIDATE
    assert candidate["methodology_candidate_id"] == repeated.data["methodology_candidates"][0]["methodology_candidate_id"]
    assert chunks[0].chunk_id in candidate["chunk_ids"]
    assert chunks[2].chunk_id in candidate["chunk_ids"]
    record = artifact_store.load_artifact_record(METHODOLOGY_CANDIDATE, candidate["methodology_candidate_id"])
    assert record.reference().to_dict()["uri"] == f"research://postgres/methodology_candidate/{candidate['methodology_candidate_id']}"


def test_discovery_uses_query_retrieval_and_family_filters(tmp_path: Path) -> None:
    artifact_root, store, source, _ = _store_with_pairs_chunks(tmp_path)
    artifact_store = InMemoryResearchArtifactStore()
    index_chunks(store, store.load_chunks(source.source_id), provider=DeterministicEmbeddingProvider())

    result = discover_methodology_candidates(
        artifact_root=artifact_root,
        query="cointegration hedge ratio spread",
        method_families=("statistical_arbitrage",),
        top_k=2,
        knowledge_store=store,
        artifact_store=artifact_store,
        embedding_provider=DeterministicEmbeddingProvider(),
    )

    assert result.ok is True
    assert result.data["candidate_count"] >= 1
    assert result.data["methodology_candidates"][0]["families"] == ["statistical_arbitrage"]
    discovery = result.data["methodology_candidates"][0]["lineage"]["discovery"]
    assert discovery["source_family_metadata_used_as_label"] is False
    assert discovery["family_attribution"]["statistical_arbitrage"]


def test_discovery_rejects_missing_inputs_unknown_sources_and_unavailable_store(tmp_path: Path) -> None:
    artifact_root, store, _, _ = _store_with_pairs_chunks(tmp_path)

    no_scope = discover_methodology_candidates(
        artifact_root=artifact_root,
        knowledge_store=store,
        artifact_store=InMemoryResearchArtifactStore(),
    )
    unknown_source = discover_methodology_candidates(
        artifact_root=artifact_root,
        source_ids=("missing_source",),
        knowledge_store=store,
        artifact_store=InMemoryResearchArtifactStore(),
    )
    unavailable = discover_methodology_candidates(
        artifact_root=artifact_root,
        source_ids=("knowledge_source_pairs",),
        knowledge_store=store,
        artifact_store=None,
    )

    assert no_scope.ok is False
    assert no_scope.errors[0]["code"] == "validation_error"
    assert unknown_source.ok is False
    assert "unknown source_id" in unknown_source.errors[0]["message"]
    assert unavailable.ok is False
    assert unavailable.errors[0]["code"] == "research_artifact_store_unavailable"


def test_family_evidence_profile_is_target_agnostic() -> None:
    profile = profile_for_family("technical_indicators")

    assert profile is not None
    assert profile.role("formula_algorithm") is not None
    assert profile.role("signal_logic") is not None
    assert "unknown_target" not in {role.role_id for role in profile.roles}


def test_sma_packet_extraction_prefers_named_candidate_span_over_generic_formula_chunks(tmp_path: Path) -> None:
    artifact_root, store, source, chunks = _store_with_sma_chunks(tmp_path)
    artifact_store = InMemoryResearchArtifactStore()
    index_chunks(store, store.load_chunks(source.source_id), provider=DeterministicEmbeddingProvider())
    discovered = discover_methodology_candidates(
        artifact_root=artifact_root,
        query="simple moving average SMA",
        source_ids=(source.source_id,),
        method_families=("technical_indicators",),
        neighbor_radius=1,
        max_candidates=3,
        knowledge_store=store,
        artifact_store=artifact_store,
        embedding_provider=DeterministicEmbeddingProvider(),
    )
    candidate = next(
        item for item in discovered.data["methodology_candidates"] if item["title"] == "Simple Moving Average"
    )

    assembled = assemble_methodology_evidence(
        artifact_root=artifact_root,
        methodology_candidate_id=candidate["methodology_candidate_id"],
        readiness_goal="strategy_template",
        neighbor_radius=1,
        knowledge_store=store,
        artifact_store=artifact_store,
    )
    extracted = extract_methodology_fields(
        artifact_root=artifact_root,
        evidence_packet_uri=assembled.artifacts["methodology_evidence_packet"]["uri"],
        knowledge_store=store,
        artifact_store=artifact_store,
    )

    assert assembled.ok is True
    formula_role = next(
        role
        for role in assembled.data["methodology_evidence_packet"]["role_evidence"]
        if role["role_id"] == "formula_algorithm"
    )
    assert formula_role["chunks"][0]["chunk_id"] == chunks[1].chunk_id
    extracted_candidate = extracted.data["methodology_candidate"]
    formula = extracted_candidate["extension_fields"]["technical_indicators"]["indicator_formula"]
    assert "Simple Moving Average" in formula["value"]
    assert formula["evidence_refs"][0]["chunk_id"] == chunks[1].chunk_id


def test_assembly_creates_role_labeled_evidence_packet(tmp_path: Path) -> None:
    artifact_root, store, source, _ = _store_with_pairs_chunks(tmp_path)
    artifact_store = InMemoryResearchArtifactStore()
    discovered = discover_methodology_candidates(
        artifact_root=artifact_root,
        source_ids=(source.source_id,),
        method_families=("statistical_arbitrage",),
        knowledge_store=store,
        artifact_store=artifact_store,
    )
    candidate_ref = discovered.artifacts["methodology_candidates"][0]

    assembled = assemble_methodology_evidence(
        artifact_root=artifact_root,
        methodology_candidate_uri=candidate_ref["uri"],
        readiness_goal="signal",
        knowledge_store=store,
        artifact_store=artifact_store,
    )

    assert assembled.ok is True
    packet = assembled.data["methodology_evidence_packet"]
    assert packet["artifact_type"] == METHODOLOGY_EVIDENCE_PACKET
    assert packet["family"] == "statistical_arbitrage"
    role_ids = {role["role_id"] for role in packet["role_evidence"] if role["status"] == "found"}
    assert {"leg_universe", "spread_definition", "stationarity_test", "entry_logic", "exit_logic"} <= role_ids
    assert artifact_store.load_artifact_record(METHODOLOGY_EVIDENCE_PACKET, packet["evidence_packet_id"]).status == (
        "assembled"
    )


def test_assembly_blocks_missing_strategy_readiness_roles(tmp_path: Path) -> None:
    artifact_root, store, source, _ = _store_with_pairs_chunks(tmp_path)
    artifact_store = InMemoryResearchArtifactStore()
    discovered = discover_methodology_candidates(
        artifact_root=artifact_root,
        source_ids=(source.source_id,),
        method_families=("statistical_arbitrage",),
        knowledge_store=store,
        artifact_store=artifact_store,
    )

    assembled = assemble_methodology_evidence(
        artifact_root=artifact_root,
        methodology_candidate_id=discovered.data["methodology_candidates"][0]["methodology_candidate_id"],
        readiness_goal="strategy_template",
        knowledge_store=store,
        artifact_store=artifact_store,
    )

    assert assembled.ok is False
    packet = assembled.data["methodology_evidence_packet"]
    assert packet["status"] == "blocked"
    assert "limitations" in packet["missing_roles"]
    assert "missing required evidence role" in "\n".join(packet["blockers"])


def test_extraction_and_validation_pass_for_evidenced_pairs_candidate(tmp_path: Path) -> None:
    artifact_root, store, source, _ = _store_with_pairs_chunks(tmp_path)
    artifact_store = InMemoryResearchArtifactStore()
    discovered = discover_methodology_candidates(
        artifact_root=artifact_root,
        source_ids=(source.source_id,),
        method_families=("statistical_arbitrage",),
        knowledge_store=store,
        artifact_store=artifact_store,
    )
    candidate_id = discovered.data["methodology_candidates"][0]["methodology_candidate_id"]

    extracted = extract_methodology_fields(
        artifact_root=artifact_root,
        methodology_candidate_id=candidate_id,
        knowledge_store=store,
        artifact_store=artifact_store,
    )
    extraction_report = extracted.data["methodology_field_extraction_report"]
    validated = validate_methodology_candidate(
        artifact_root=artifact_root,
        extraction_report_id=extraction_report["extraction_id"],
        knowledge_store=store,
        artifact_store=artifact_store,
    )

    assert extracted.ok is True
    candidate = extracted.data["methodology_candidate"]
    assert candidate["status"] == "extracted"
    assert candidate["extension_fields"]["statistical_arbitrage"]["cointegration_test"]["evidence_refs"]
    assert "options_derivatives" not in candidate["extension_fields"]
    assert extraction_report["artifact_type"] == METHODOLOGY_FIELD_EXTRACTION_REPORT
    assert validated.ok is True
    report = validated.data["methodology_candidate_validation_report"]
    assert report["status"] == "passed"
    assert artifact_store.load_artifact_record(
        METHODOLOGY_CANDIDATE_VALIDATION_REPORT,
        report["validation_id"],
    ).status == "passed"


def test_packet_grounded_extraction_and_validation_report_readiness(tmp_path: Path) -> None:
    artifact_root, store, source, _ = _store_with_pairs_chunks(tmp_path)
    artifact_store = InMemoryResearchArtifactStore()
    discovered = discover_methodology_candidates(
        artifact_root=artifact_root,
        source_ids=(source.source_id,),
        method_families=("statistical_arbitrage",),
        knowledge_store=store,
        artifact_store=artifact_store,
    )
    assembled = assemble_methodology_evidence(
        artifact_root=artifact_root,
        methodology_candidate_id=discovered.data["methodology_candidates"][0]["methodology_candidate_id"],
        readiness_goal="signal",
        knowledge_store=store,
        artifact_store=artifact_store,
    )
    packet_id = assembled.data["methodology_evidence_packet"]["evidence_packet_id"]

    extracted = extract_methodology_fields(
        artifact_root=artifact_root,
        evidence_packet_id=packet_id,
        knowledge_store=store,
        artifact_store=artifact_store,
    )
    validated = validate_methodology_candidate(
        artifact_root=artifact_root,
        extraction_report_id=extracted.data["methodology_field_extraction_report"]["extraction_id"],
        knowledge_store=store,
        artifact_store=artifact_store,
    )

    assert extracted.ok is True
    candidate = extracted.data["methodology_candidate"]
    assert candidate["lineage"]["evidence_packet_id"] == packet_id
    spread = candidate["extension_fields"]["statistical_arbitrage"]["spread_definition"]
    assert spread["quality"] == "role_evidence:spread_definition"
    assert "source-backed spread definition evidence" not in spread["value"]
    assert validated.ok is True
    readiness = validated.data["methodology_candidate_validation_report"]["readiness_summary"]
    assert readiness["signal"]["status"] == "passed"
    assert readiness["strategy_template"]["status"] == "blocked"


def test_extraction_rejects_invalid_refs_and_blocks_missing_chunks(tmp_path: Path) -> None:
    artifact_root, store, source, _ = _store_with_pairs_chunks(tmp_path)
    artifact_store = InMemoryResearchArtifactStore()
    bad_type = extract_methodology_fields(
        artifact_root=artifact_root,
        methodology_candidate={"artifact_type": "method_card", "methodology_candidate_id": "bad"},
        knowledge_store=store,
        artifact_store=artifact_store,
    )
    missing_chunk_candidate = MethodologyCandidate(
        methodology_candidate_id="methodology_candidate_missing_chunk",
        title="Missing chunk",
        families=("statistical_arbitrage",),
        source_ids=(source.source_id,),
        chunk_ids=("missing_chunk",),
    )
    artifact_store.save_artifact(
        artifact_type=METHODOLOGY_CANDIDATE,
        artifact_id=missing_chunk_candidate.methodology_candidate_id,
        payload=missing_chunk_candidate.to_dict(),
        status=missing_chunk_candidate.status,
    )
    missing = extract_methodology_fields(
        artifact_root=artifact_root,
        methodology_candidate_id=missing_chunk_candidate.methodology_candidate_id,
        knowledge_store=store,
        artifact_store=artifact_store,
    )

    assert bad_type.ok is False
    assert missing.ok is False
    assert missing.data["methodology_field_extraction_report"]["status"] == "blocked"


def test_validation_blocks_bad_evidence_and_family_minimum_failures(tmp_path: Path) -> None:
    artifact_root, store, source, chunks = _store_with_pairs_chunks(tmp_path, source_type="internal_note")
    artifact_store = InMemoryResearchArtifactStore()
    bad_locator_ref = EvidenceReference(
        source_id=source.source_id,
        chunk_id=chunks[1].chunk_id,
        locator={"heading": "Wrong Heading"},
        claim="bad locator",
    )
    candidate = MethodologyCandidate(
        methodology_candidate_id="methodology_candidate_invalid",
        title="Invalid textbook-derived pairs method",
        families=("statistical_arbitrage",),
        source_ids=(source.source_id,),
        chunk_ids=(chunks[1].chunk_id,),
        core_fields={
            "identity": {
                "method_name": EvidenceBackedField(value="Invalid pairs method", evidence_refs=(bad_locator_ref,)),
            },
            "data_requirements": {
                "required_inputs": EvidenceBackedField(value=("price series",), evidence_refs=(bad_locator_ref,)),
            },
        },
        extension_fields={
            "statistical_arbitrage": {
                "spread_definition": EvidenceBackedField(
                    value="x " * 100,
                    evidence_refs=(bad_locator_ref,),
                )
            }
        },
        lineage={"discovery": {"source_types": ["method_textbook"]}},
    )

    result = validate_methodology_candidate(
        artifact_root=artifact_root,
        methodology_candidate=candidate.to_dict(),
        knowledge_store=store,
        artifact_store=artifact_store,
    )

    assert result.ok is False
    report = result.data["methodology_candidate_validation_report"]
    blockers = "\n".join(report["blockers"])
    assert "locator mismatch" in blockers
    assert "statistical_arbitrage requires" in blockers
    assert "excessive direct quotation" in blockers
    assert "internal_note" in blockers
