"""Contracts for target-bound methodology evidence-packet assembly.

Subject: Role-labeled evidence selection and target binding for discovered methodology candidates.
Level: Offline application workflow contract.
Collaborators: Candidate discovery, deterministic retrieval, JSON knowledge store, and artifact records.
Guarantees: Packets prefer relevant claims, reject neighboring methods, and expose readiness gaps.
Non-goals: Canonical method cards, computational implementation validation, Postgres, or model reasoning.
"""

from __future__ import annotations

from pathlib import Path

from trader_research.foundation.artifacts import InMemoryResearchArtifactStore
from trader_research.governance.artifacts import METHODOLOGY_EVIDENCE_PACKET
from trader_research.knowledge.embeddings import DeterministicEmbeddingProvider
from trader_research.knowledge.evidence_assembly import (
    ACCEPTED_TARGET_BINDINGS,
    assemble_methodology_evidence,
)
from trader_research.knowledge.index import index_chunks
from trader_research.knowledge.methodology_candidates import (
    discover_methodology_candidates,
)
from trader_research.knowledge.methodology_extraction import extract_methodology_fields
from tests.trader_research.knowledge.methodology_candidate_fixtures import (
    _store_with_adjacent_indicator_units,
    _store_with_pairs_chunks,
    _store_with_sma_chunks,
)


def test_sma_packet_extraction_prefers_named_candidate_span_over_generic_formula_chunks(
    tmp_path: Path,
) -> None:
    """SMA extraction prefers explicitly named claims over unrelated generic formulas."""
    artifact_root, store, source, chunks = _store_with_sma_chunks(tmp_path)
    artifact_store = InMemoryResearchArtifactStore()
    index_chunks(
        store,
        store.load_chunks(source.source_id),
        provider=DeterministicEmbeddingProvider(),
    )
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
        item
        for item in discovered.data["methodology_candidates"]
        if item["title"] == "Simple Moving Average"
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
    formula = extracted_candidate["extension_fields"]["technical_indicators"][
        "indicator_formula"
    ]
    assert "Simple Moving Average" in formula["value"]
    assert formula["evidence_refs"][0]["chunk_id"] == chunks[1].chunk_id


def test_assembly_creates_role_labeled_evidence_packet(tmp_path: Path) -> None:
    """Assembly records role-labeled, target-bound evidence in a canonical packet."""
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
    role_ids = {
        role["role_id"] for role in packet["role_evidence"] if role["status"] == "found"
    }
    assert {
        "leg_universe",
        "spread_definition",
        "stationarity_test",
        "entry_logic",
        "exit_logic",
    } <= role_ids
    for role in packet["role_evidence"]:
        if role["status"] != "found":
            continue
        assert role["target_binding_required"] is True
        assert role["target_binding_summary"]["accepted_count"] >= 1
        for chunk_ref in role["chunks"]:
            assert chunk_ref["accepted_target_binding"] is True
            assert chunk_ref["target_binding"] in ACCEPTED_TARGET_BINDINGS
            assert chunk_ref["evidence_unit_id"] == chunk_ref["chunk_id"]
    assert artifact_store.load_artifact_record(
        METHODOLOGY_EVIDENCE_PACKET, packet["evidence_packet_id"]
    ).status == ("assembled")


def test_target_bound_packet_rejects_adjacent_bollinger_signal_for_ewa(
    tmp_path: Path,
) -> None:
    """An EWA packet excludes neighboring Bollinger signal claims while retaining its formula."""
    artifact_root, store, source, chunks = _store_with_adjacent_indicator_units(
        tmp_path
    )
    artifact_store = InMemoryResearchArtifactStore()
    index_chunks(
        store,
        store.load_chunks(source.source_id),
        provider=DeterministicEmbeddingProvider(),
    )
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
        item
        for item in discovered.data["methodology_candidates"]
        if item["title"] == "Exponentially Weighted Average"
    )
    bollinger_chunk = next(
        chunk for chunk in chunks if "Bollinger Bands" in chunk.detected_labels
    )

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
    signal_role = next(
        role for role in packet["role_evidence"] if role["role_id"] == "signal_logic"
    )
    formula_role = next(
        role
        for role in packet["role_evidence"]
        if role["role_id"] == "formula_algorithm"
    )

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
    formula = extracted_candidate["extension_fields"]["technical_indicators"][
        "indicator_formula"
    ]
    assert "Exponentially Weighted Average" in formula["value"]
    assert formula["evidence_refs"][0]["chunk_id"] != bollinger_chunk.chunk_id


def test_assembly_blocks_missing_strategy_readiness_roles(tmp_path: Path) -> None:
    """Assembly reports missing evidence roles required for strategy readiness."""
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
        methodology_candidate_id=discovered.data["methodology_candidates"][0][
            "methodology_candidate_id"
        ],
        readiness_goal="strategy_template",
        knowledge_store=store,
        artifact_store=artifact_store,
    )

    assert assembled.ok is False
    packet = assembled.data["methodology_evidence_packet"]
    assert packet["status"] == "blocked"
    assert "limitations" in packet["missing_roles"]
    assert "missing required evidence role" in "\n".join(packet["blockers"])
