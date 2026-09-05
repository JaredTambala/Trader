"""Contracts for open-world methodology candidate discovery.

Subject: Source-scoped and query-scoped discovery of distinct methodology identities.
Level: Offline application contract.
Collaborators: JSON knowledge store, deterministic embeddings, chunking, and artifact records.
Guarantees: Discovery is deterministic, target-agnostic, filtered, and fails closed for invalid scope.
Non-goals: Evidence-packet assembly, field extraction, candidate validation, or method-card publication.
"""

from __future__ import annotations

from pathlib import Path

from trader_research.foundation.artifacts import InMemoryResearchArtifactStore
from trader_research.governance.artifacts import METHODOLOGY_CANDIDATE
from trader_research.knowledge.chunking import chunk_sections
from trader_research.knowledge.domain import KnowledgeSourceManifest
from trader_research.knowledge.embeddings import DeterministicEmbeddingProvider
from trader_research.knowledge.evidence_profiles import profile_for_family
from trader_research.knowledge.extractors import ExtractedSection
from trader_research.knowledge.index import index_chunks
from trader_research.knowledge.methodology_candidates import (
    discover_methodology_candidates,
)
from trader_research.knowledge.store import JsonKnowledgeStore
from tests.trader_research.knowledge.methodology_candidate_fixtures import (
    _store_with_pairs_chunks,
)


def test_discovery_creates_deterministic_candidate_from_source_scope(
    tmp_path: Path,
) -> None:
    """Source-scoped discovery creates stable candidates and canonical artifact references."""
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
    assert (
        candidate["methodology_candidate_id"]
        == repeated.data["methodology_candidates"][0]["methodology_candidate_id"]
    )
    assert chunks[0].chunk_id not in candidate["chunk_ids"]
    assert chunks[1].chunk_id in candidate["chunk_ids"]
    assert chunks[2].chunk_id in candidate["chunk_ids"]
    assert candidate["method_identity"]["canonical_name"] == "Pairs Trading"
    assert candidate["method_identity"]["identity_evidence_unit_ids"]
    record = artifact_store.load_artifact_record(
        METHODOLOGY_CANDIDATE, candidate["methodology_candidate_id"]
    )
    assert (
        record.reference().to_dict()["uri"]
        == f"research://postgres/methodology_candidate/{candidate['methodology_candidate_id']}"
    )


def test_discovery_uses_query_retrieval_and_family_filters(tmp_path: Path) -> None:
    """Query retrieval selects candidates within the requested methodology family."""
    artifact_root, store, source, _ = _store_with_pairs_chunks(tmp_path)
    artifact_store = InMemoryResearchArtifactStore()
    index_chunks(
        store,
        store.load_chunks(source.source_id),
        provider=DeterministicEmbeddingProvider(),
    )

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
    assert result.data["methodology_candidates"][0]["families"] == [
        "statistical_arbitrage"
    ]
    discovery = result.data["methodology_candidates"][0]["lineage"]["discovery"]
    assert discovery["source_family_metadata_used_as_label"] is False
    assert discovery["family_attribution"]["statistical_arbitrage"]


def test_discovery_separates_adjacent_method_identities_without_known_targets(
    tmp_path: Path,
) -> None:
    """Discovery separates neighboring method identities without a maintained target registry."""
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
    by_title = {
        candidate["title"]: candidate
        for candidate in discovered.data["methodology_candidates"]
    }
    assert {
        "Simple Moving Average",
        "Exponentially Weighted Average",
        "Bollinger Bands",
        "Relative Strength Index",
    } <= set(by_title)
    ewa = by_title["Exponentially Weighted Average"]
    assert ewa["method_identity"]["aliases"] == [
        "EWA",
        "Exponentially Weighted Average",
    ]
    assert ewa["method_identity"]["query_alignment"]["status"] == "direct"
    assert by_title["Simple Moving Average"]["chunk_ids"] != ewa["chunk_ids"]
    assert by_title["Bollinger Bands"]["chunk_ids"] != ewa["chunk_ids"]
    assert all(
        chunk_id.startswith("knowledge_evidence_unit_") for chunk_id in ewa["chunk_ids"]
    )


def test_discovery_rejects_missing_inputs_unknown_sources_and_unavailable_store(
    tmp_path: Path,
) -> None:
    """Discovery fails closed for absent scope, unknown sources, and missing persistence."""
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
    """Family evidence profiles define roles without prescribing known method identities."""
    profile = profile_for_family("technical_indicators")

    assert profile is not None
    assert profile.role("formula_algorithm") is not None
    assert profile.role("signal_logic") is not None
    assert "unknown_target" not in {role.role_id for role in profile.roles}
