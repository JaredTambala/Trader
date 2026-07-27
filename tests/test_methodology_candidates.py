from __future__ import annotations

from trader_research.governance.artifacts import DOMAIN_OWNER_BY_ARTIFACT_TYPE

from dataclasses import replace
import hashlib
from pathlib import Path

from trader_research.foundation.artifacts import InMemoryResearchArtifactStore
from trader_research.governance.artifacts import (
    METHODOLOGY_CANDIDATE,
    METHODOLOGY_CANDIDATE_VALIDATION_REPORT,
    METHODOLOGY_EVIDENCE_PACKET,
    METHODOLOGY_FIELD_EXTRACTION_REPORT,
)
from trader_research.knowledge.chunking import chunk_sections
from trader_research.knowledge.domain import (
    EvidenceBackedField,
    EvidenceReference,
    KnowledgeChunk,
    KnowledgeSourceManifest,
    MethodologyCandidate,
)
from trader_research.knowledge.extractors import ExtractedSection
from trader_research.knowledge.embeddings import DeterministicEmbeddingProvider
from trader_research.knowledge.index import index_chunks
from trader_research.knowledge.evidence_assembly import ACCEPTED_TARGET_BINDINGS, assemble_methodology_evidence
from trader_research.knowledge.evidence_profiles import profile_for_family
from trader_research.knowledge.methodology_candidates import discover_methodology_candidates
from trader_research.knowledge.methodology_extraction import extract_methodology_fields
from trader_research.knowledge.methodology_validation import validate_methodology_candidate
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
        _chunk(source, 3, "Simple Moving Average risk includes noisy regimes and whipsaw failure modes.", "Page 183"),
        _chunk(source, 4, "Another exercise says compute average sums and ratios for moving portfolios.", "Page 225"),
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
    assert chunks[0].chunk_id not in candidate["chunk_ids"]
    assert chunks[1].chunk_id in candidate["chunk_ids"]
    assert chunks[2].chunk_id in candidate["chunk_ids"]
    assert candidate["method_identity"]["canonical_name"] == "Pairs Trading"
    assert candidate["method_identity"]["identity_evidence_unit_ids"]
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


def test_discovery_separates_adjacent_method_identities_without_known_targets(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    store = JsonKnowledgeStore(artifact_root)
    source = KnowledgeSourceManifest(
        source_id="knowledge_source_adjacent_indicators",
        title="Adjacent Indicator Source",
        source_type="method_textbook",
        path="tests/fixtures/knowledge/technical_notes.txt",
        file_hash="adjacent123",
        file_size_bytes=256,
        topics=("technical indicators",),
        method_families=("technical_indicators",),
    )
    chunks = chunk_sections(
        source,
        (
            ExtractedSection(
                text=(
                    "Simple Moving Average (SMA): The simple moving average sums lagged prices. "
                    "Exponentially Weighted Average (EWA): The exponentially weighted average gives more weight "
                    "to recent prices. "
                    "Bollinger Bands (BB): Bollinger bands use upper and lower bands around a moving average. "
                    "Relative Strength Index (RSI): RSI is an oscillator."
                ),
                section="technical indicators",
                heading="Page 181",
            ),
        ),
    )
    store.save_source(source)
    store.replace_chunks(source.source_id, chunks)
    artifact_store = InMemoryResearchArtifactStore()

    discovered = discover_methodology_candidates(
        artifact_root=artifact_root,
        query="exponentially weighted average EWA",
        source_ids=(source.source_id,),
        method_families=("technical_indicators",),
        neighbor_radius=1,
        max_candidates=10,
        knowledge_store=store,
        artifact_store=artifact_store,
        embedding_provider=DeterministicEmbeddingProvider(),
    )

    assert discovered.ok is True
    by_title = {candidate["title"]: candidate for candidate in discovered.data["methodology_candidates"]}
    assert {"Simple Moving Average", "Exponentially Weighted Average", "Bollinger Bands", "Relative Strength Index"} <= set(
        by_title
    )
    ewa = by_title["Exponentially Weighted Average"]
    assert ewa["method_identity"]["aliases"] == ["EWA", "Exponentially Weighted Average"]
    assert ewa["method_identity"]["query_alignment"]["status"] == "direct"
    assert by_title["Simple Moving Average"]["chunk_ids"] != ewa["chunk_ids"]
    assert by_title["Bollinger Bands"]["chunk_ids"] != ewa["chunk_ids"]
    assert all(chunk_id.startswith("knowledge_evidence_unit_") for chunk_id in ewa["chunk_ids"])


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
    for role in packet["role_evidence"]:
        if role["status"] != "found":
            continue
        assert role["target_binding_required"] is True
        assert role["target_binding_summary"]["accepted_count"] >= 1
        for chunk_ref in role["chunks"]:
            assert chunk_ref["accepted_target_binding"] is True
            assert chunk_ref["target_binding"] in ACCEPTED_TARGET_BINDINGS
            assert chunk_ref["evidence_unit_id"] == chunk_ref["chunk_id"]
    assert artifact_store.load_artifact_record(METHODOLOGY_EVIDENCE_PACKET, packet["evidence_packet_id"]).status == (
        "assembled"
    )


def test_target_bound_packet_rejects_adjacent_bollinger_signal_for_ewa(tmp_path: Path) -> None:
    artifact_root, store, source, chunks = _store_with_adjacent_indicator_units(tmp_path)
    artifact_store = InMemoryResearchArtifactStore()
    index_chunks(store, store.load_chunks(source.source_id), provider=DeterministicEmbeddingProvider())
    discovered = discover_methodology_candidates(
        artifact_root=artifact_root,
        query="exponentially weighted average EWA",
        source_ids=(source.source_id,),
        method_families=("technical_indicators",),
        neighbor_radius=1,
        max_candidates=10,
        knowledge_store=store,
        artifact_store=artifact_store,
        embedding_provider=DeterministicEmbeddingProvider(),
    )
    candidate = next(
        item for item in discovered.data["methodology_candidates"] if item["title"] == "Exponentially Weighted Average"
    )
    bollinger_chunk = next(chunk for chunk in chunks if "Bollinger Bands" in chunk.detected_labels)

    assembled = assemble_methodology_evidence(
        artifact_root=artifact_root,
        methodology_candidate_id=candidate["methodology_candidate_id"],
        readiness_goal="signal",
        neighbor_radius=1,
        max_chunks_per_role=10,
        knowledge_store=store,
        artifact_store=artifact_store,
    )
    packet = assembled.data["methodology_evidence_packet"]
    signal_role = next(role for role in packet["role_evidence"] if role["role_id"] == "signal_logic")
    formula_role = next(role for role in packet["role_evidence"] if role["role_id"] == "formula_algorithm")

    assert assembled.ok is False
    assert signal_role["status"] == "missing"
    assert signal_role["chunks"] == []
    assert any(
        ref["chunk_id"] == bollinger_chunk.chunk_id
        and ref["target_binding"] == "rejected"
        and "Bollinger Bands" in ref["competing_method_labels"]
        for ref in signal_role["rejected_chunks"]
    )
    assert formula_role["chunks"][0]["target_binding"] in ACCEPTED_TARGET_BINDINGS

    extracted = extract_methodology_fields(
        artifact_root=artifact_root,
        evidence_packet=packet,
        knowledge_store=store,
        artifact_store=artifact_store,
    )

    assert extracted.ok is True
    extracted_candidate = extracted.data["methodology_candidate"]
    signal_fields = extracted_candidate["core_fields"].get("signal_decision_logic", {})
    assert all(field["value"] is None for field in signal_fields.values())
    formula = extracted_candidate["extension_fields"]["technical_indicators"]["indicator_formula"]
    assert "Exponentially Weighted Average" in formula["value"]
    assert formula["evidence_refs"][0]["chunk_id"] != bollinger_chunk.chunk_id


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


def test_validation_blocks_candidate_extracted_without_evidence_packet(tmp_path: Path) -> None:
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
    assert validated.ok is False
    report = validated.data["methodology_candidate_validation_report"]
    assert report["status"] == "blocked"
    assert "methodology_evidence_packet lineage" in "\n".join(report["blockers"])
    assert artifact_store.load_artifact_record(
        METHODOLOGY_CANDIDATE_VALIDATION_REPORT,
        report["validation_id"],
    ).status == "blocked"


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


def test_validation_blocks_stale_packet_evidence_unit_hashes(tmp_path: Path) -> None:
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
    packet = assembled.data["methodology_evidence_packet"]
    extracted = extract_methodology_fields(
        artifact_root=artifact_root,
        evidence_packet_id=packet["evidence_packet_id"],
        knowledge_store=store,
        artifact_store=artifact_store,
    )
    tampered_roles = []
    tampered = False
    for role in packet["role_evidence"]:
        role_copy = dict(role)
        chunks_copy = []
        for chunk_ref in role.get("chunks", ()):
            ref_copy = dict(chunk_ref)
            if not tampered:
                ref_copy["text_hash"] = "stale_hash"
                tampered = True
            chunks_copy.append(ref_copy)
        role_copy["chunks"] = chunks_copy
        tampered_roles.append(role_copy)
    artifact_store.save_artifact(
        domain_owner=DOMAIN_OWNER_BY_ARTIFACT_TYPE[METHODOLOGY_EVIDENCE_PACKET],
        producer_tool="test_methodology_fixture",
        artifact_type=METHODOLOGY_EVIDENCE_PACKET,
        artifact_id=packet["evidence_packet_id"],
        payload={**packet, "role_evidence": tampered_roles},
        status=packet["status"],
    )

    validated = validate_methodology_candidate(
        artifact_root=artifact_root,
        extraction_report_id=extracted.data["methodology_field_extraction_report"]["extraction_id"],
        knowledge_store=store,
        artifact_store=artifact_store,
    )

    assert validated.ok is False
    blockers = "\n".join(validated.data["methodology_candidate_validation_report"]["blockers"])
    assert "stale text_hash" in blockers


def test_validation_blocks_fields_sourced_from_rejected_competing_method(tmp_path: Path) -> None:
    artifact_root, store, source, chunks = _store_with_adjacent_indicator_units(tmp_path)
    artifact_store = InMemoryResearchArtifactStore()
    index_chunks(store, store.load_chunks(source.source_id), provider=DeterministicEmbeddingProvider())
    discovered = discover_methodology_candidates(
        artifact_root=artifact_root,
        query="exponentially weighted average EWA",
        source_ids=(source.source_id,),
        method_families=("technical_indicators",),
        neighbor_radius=1,
        max_candidates=10,
        knowledge_store=store,
        artifact_store=artifact_store,
        embedding_provider=DeterministicEmbeddingProvider(),
    )
    ewa = next(
        item for item in discovered.data["methodology_candidates"] if item["title"] == "Exponentially Weighted Average"
    )
    ewa_chunk = next(chunk for chunk in chunks if "Exponentially Weighted Average" in chunk.detected_labels)
    bollinger_chunk = next(chunk for chunk in chunks if "Bollinger Bands" in chunk.detected_labels)
    assembled = assemble_methodology_evidence(
        artifact_root=artifact_root,
        methodology_candidate_id=ewa["methodology_candidate_id"],
        readiness_goal="signal",
        neighbor_radius=1,
        max_chunks_per_role=10,
        knowledge_store=store,
        artifact_store=artifact_store,
    )
    packet = assembled.data["methodology_evidence_packet"]
    ewa_ref = EvidenceReference(
        source_id=source.source_id,
        chunk_id=ewa_chunk.chunk_id,
        locator=ewa_chunk.locator,
        claim="role evidence supports formula algorithm; evidence_role=formula_algorithm",
    )
    bollinger_ref = EvidenceReference(
        source_id=source.source_id,
        chunk_id=bollinger_chunk.chunk_id,
        locator=bollinger_chunk.locator,
        claim="role evidence supports signal logic; evidence_role=signal_logic",
    )
    candidate = MethodologyCandidate(
        methodology_candidate_id="methodology_candidate_contaminated_ewa",
        title="Exponentially Weighted Average",
        families=("technical_indicators",),
        status="extracted",
        source_ids=(source.source_id,),
        chunk_ids=(ewa_chunk.chunk_id, bollinger_chunk.chunk_id),
        method_identity=ewa["method_identity"],
        core_fields={
            "identity": {
                "method_name": EvidenceBackedField(value="Exponentially Weighted Average", evidence_refs=(ewa_ref,)),
            },
            "data_requirements": {
                "required_inputs": EvidenceBackedField(value=("ordered price series",), evidence_refs=(ewa_ref,)),
            },
            "signal_decision_logic": {
                "signal_definition": EvidenceBackedField(
                    value="Bollinger band crossing signal",
                    evidence_refs=(bollinger_ref,),
                    quality="role_evidence:signal_logic",
                ),
            },
        },
        extension_fields={
            "technical_indicators": {
                "indicator_formula": EvidenceBackedField(
                    value="EWA weighted moving average formula",
                    evidence_refs=(ewa_ref,),
                    quality="role_evidence:formula_algorithm",
                )
            }
        },
        lineage={"evidence_packet_id": packet["evidence_packet_id"], "readiness_goal": "signal"},
    )

    validated = validate_methodology_candidate(
        artifact_root=artifact_root,
        methodology_candidate=candidate.to_dict(),
        knowledge_store=store,
        artifact_store=artifact_store,
    )

    assert validated.ok is False
    blockers = "\n".join(validated.data["methodology_candidate_validation_report"]["blockers"])
    assert "must include claim_span" in blockers
    assert "must cite a target-bound claim span" in blockers


def test_shared_evidence_unit_supports_distinct_method_claim_spans(tmp_path: Path) -> None:
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
        locator={"source_id": source.source_id, "page": 182, "heading": "Technical rules"},
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
        role for role in oscillator_packet["role_evidence"] if role["role_id"] == "signal_logic"
    )
    oscillator_signal_text = " ".join(
        span["text"] for ref in oscillator_signal["chunks"] for span in ref["claim_spans"]
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
    signal_field = extracted_candidate["core_fields"]["signal_decision_logic"]["signal_definition"]
    assert all(ref["claim_span"]["target_method"] == "Moving Average Oscillator" for ref in signal_field["evidence_refs"])

    stale_candidate = MethodologyCandidate.from_dict(extracted_candidate)
    stale_extensions = {group: dict(fields) for group, fields in stale_candidate.extension_fields.items()}
    stale_extensions["technical_indicators"]["overbought_threshold"] = EvidenceBackedField(
        value="stale neighboring-method threshold",
        evidence_refs=stale_candidate.core_fields["signal_decision_logic"]["signal_definition"].evidence_refs,
        quality="role_evidence:threshold_semantics",
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
    assert "overbought_threshold" not in reextracted.data["methodology_candidate"]["extension_fields"][
        "technical_indicators"
    ]

    validated = validate_methodology_candidate(
        artifact_root=artifact_root,
        extraction_report_id=reextracted.data["methodology_field_extraction_report"]["extraction_id"],
        knowledge_store=store,
        artifact_store=artifact_store,
    )
    assert validated.ok is True


def test_real_pdf_shaped_oscillator_evidence_rejects_neighbor_method_claims(tmp_path: Path) -> None:
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
    signal_role = next(role for role in packet["role_evidence"] if role["role_id"] == "signal_logic")
    accepted_signal_text = " ".join(
        span["text"] for chunk_ref in signal_role["chunks"] for span in chunk_ref["claim_spans"]
    )

    assert "short moving average intersects" in accepted_signal_text
    assert "upper band" not in accepted_signal_text
    assert "lower band" not in accepted_signal_text
    assert "RSI Oscillator" not in accepted_signal_text
    threshold_role = next(role for role in packet["role_evidence"] if role["role_id"] == "threshold_semantics")
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
    technical = extracted.data["methodology_candidate"]["extension_fields"]["technical_indicators"]
    assert "overbought_threshold" not in technical
    assert "oversold_threshold" not in technical


def test_field_synthesis_preserves_claim_spans_across_evidence_units(tmp_path: Path) -> None:
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
    algorithm = extracted.data["methodology_candidate"]["core_fields"]["method_specification"]["algorithm_steps"]
    assert "short moving average" in algorithm["value"]
    assert "long moving average" in algorithm["value"]
    assert {ref["chunk_id"] for ref in algorithm["evidence_refs"]} == {chunk.chunk_id for chunk in chunks}
    assert all(ref["claim_span"] is not None for ref in algorithm["evidence_refs"])


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
        domain_owner=DOMAIN_OWNER_BY_ARTIFACT_TYPE[METHODOLOGY_CANDIDATE],
        producer_tool="test_methodology_fixture",
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
