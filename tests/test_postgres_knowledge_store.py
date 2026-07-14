from __future__ import annotations

from pathlib import Path

import pytest

from trader_research.knowledge.citation_validation import validate_citations
from trader_research.knowledge.domain import MethodCard, MethodCardSet
from trader_research.knowledge.embeddings import DeterministicEmbeddingProvider
from trader_research.knowledge.ingestion import ingest_documents
from trader_research.knowledge.postgres_store import PostgresKnowledgeStore
from trader_research.knowledge.retrieval import get_evidence_chunks, retrieve_evidence
from trader_research.knowledge.sources import register_source
from trader_research.methods.contracts import MethodRegistryEntry, ParameterSpec


pytestmark = pytest.mark.postgres


def test_postgres_knowledge_store_register_ingest_retrieve_validate(
    postgres_knowledge_store: PostgresKnowledgeStore,
    tmp_path: Path,
) -> None:
    source = Path("tests/fixtures/knowledge/sma_method.md")
    registered = register_source(
        artifact_root=tmp_path / "artifacts",
        path=source,
        title="SMA Source",
        source_type="method_textbook",
        topics=("indicators",),
        method_families=("indicator",),
        knowledge_store=postgres_knowledge_store,
    )
    source_id = registered.data["knowledge_source_manifest"]["source_id"]
    ingested = ingest_documents(
        artifact_root=tmp_path / "artifacts",
        source_ids=(source_id,),
        embedding_provider=DeterministicEmbeddingProvider(),
        knowledge_store=postgres_knowledge_store,
    )
    retrieved = retrieve_evidence(
        artifact_root=tmp_path / "artifacts",
        query="simple moving average warmup",
        source_ids=(source_id,),
        embedding_provider=DeterministicEmbeddingProvider(),
        top_k=1,
        knowledge_store=postgres_knowledge_store,
    )
    evidence = retrieved.data["evidence_retrieval_report"]["results"][0]
    dereferenced = get_evidence_chunks(
        artifact_root=tmp_path / "artifacts",
        chunk_ids=(evidence["chunk_id"],),
        source_id=source_id,
        knowledge_store=postgres_knowledge_store,
    )
    citations = validate_citations(
        artifact_root=tmp_path / "artifacts",
        artifact={
            "knowledge_evidence_refs": [
                {
                    "source_id": evidence["source_id"],
                    "chunk_id": evidence["chunk_id"],
                    "locator": evidence["locator"],
                    "method_card_id": "method_card_sma_seed_v1",
                }
            ]
        },
        knowledge_store=postgres_knowledge_store,
    )
    method_card = MethodCard(
        method_card_id="method_card_postgres_demo",
        method_card_set_id="method_card_set_postgres_demo",
        revision_number=1,
        method_id="sma",
        title="Postgres Method Card Demo",
        family="indicator",
        status="draft",
        assumptions=("ordered observations",),
        inputs=("prices",),
        outputs=("average",),
        failure_modes=("warmup",),
    )
    postgres_knowledge_store.save_method_card(method_card)
    method_card_set = MethodCardSet(
        method_card_set_id=method_card.method_card_set_id,
        method_id=method_card.method_id,
        family=method_card.family,
        canonical_title=method_card.title,
        status="active",
        current_draft_method_card_id=method_card.method_card_id,
        card_ids=(method_card.method_card_id,),
        revision_count=1,
        latest_revision_number=1,
        status_counts={"draft": 1},
    )
    postgres_knowledge_store.save_method_card_set(method_card_set)
    method_contract = MethodRegistryEntry(
        method_id="postgres_db_backed_demo",
        family="indicator",
        status="approved",
        purpose="Demonstrate Postgres-backed method contract persistence.",
        parameters=(ParameterSpec("period", "int", min_value=2, max_value=50),),
        inputs=("price series",),
        outputs=("derived series",),
        assumptions=("ordered observations",),
        failure_modes=("warmup",),
        artifact_outputs=("indicator_validation_report.json",),
        warmup="period - 1 observations",
        nan_policy="propagate",
        no_lookahead=True,
    )
    postgres_knowledge_store.save_method_contract(method_contract)
    runtime = postgres_knowledge_store.runtime_summary()

    assert registered.ok is True
    assert ingested.ok is True
    assert ingested.data["knowledge_ingestion_report"]["chunks_indexed"] >= 1
    assert retrieved.ok is True
    assert evidence["retrieval_scores"]["combined_rank"] == 1
    assert evidence["retrieval_scores"]["lexical_rank"] is not None
    assert evidence["retrieval_scores"]["vector_rank"] is not None
    assert dereferenced.ok is True
    assert "simple moving average computes the arithmetic mean" in dereferenced.data["chunks"][0]["text"]
    assert dereferenced.data["chunks"][0]["hash_verified"] is True
    assert dereferenced.data["chunks"][0]["locator"] == evidence["locator"]
    assert citations.ok is True
    assert postgres_knowledge_store.list_persisted_method_cards() == (method_card,)
    assert postgres_knowledge_store.list_method_card_sets() == (method_card_set,)
    assert postgres_knowledge_store.list_persisted_method_contracts() == (method_contract,)
    assert runtime["pgvector_available"] is True
