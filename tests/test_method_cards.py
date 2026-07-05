from __future__ import annotations

from pathlib import Path

from trader_research.knowledge.chunking import chunk_sections
from trader_research.knowledge.domain import KnowledgeSourceManifest
from trader_research.knowledge.extractors import extract_text
from trader_research.knowledge.method_cards import (
    create_method_card_draft,
    get_method_card,
    publish_method_card,
    search_method_cards,
)
from trader_research.knowledge.store import JsonKnowledgeStore
from trader_research.methods import math_validate_method_contract


FIXTURE = Path("tests/fixtures/knowledge/sma_method.md")


def test_method_card_draft_and_publish_lifecycle(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    store, evidence_ref = _store_with_evidence(artifact_root)

    no_evidence = create_method_card_draft(
        artifact_root=artifact_root,
        method_id="custom_rank_ic",
        title="Custom Rank IC",
        family="signal_diagnostic",
        assumptions=("signals and labels are aligned",),
        inputs=("signals",),
        outputs=("rank correlation",),
        failure_modes=("small sample size",),
        evidence_refs=(),
        knowledge_store=store,
    )
    bad_locator = create_method_card_draft(
        artifact_root=artifact_root,
        method_id="custom_rank_ic",
        title="Custom Rank IC",
        family="signal_diagnostic",
        assumptions=("signals and labels are aligned",),
        inputs=("signals",),
        outputs=("rank correlation",),
        failure_modes=("small sample size",),
        evidence_refs=({**evidence_ref, "locator": {**evidence_ref["locator"], "heading": "Wrong"}},),
        knowledge_store=store,
    )
    draft = create_method_card_draft(
        artifact_root=artifact_root,
        method_id="custom_rank_ic",
        title="Custom Rank IC",
        family="signal_diagnostic",
        assumptions=("signals and labels are aligned",),
        inputs=("signals",),
        outputs=("rank correlation",),
        failure_modes=("small sample size",),
        evidence_refs=(evidence_ref,),
        knowledge_store=store,
    )
    draft_id = draft.data["method_card_draft"]["method_card_id"]
    default_search_before_publish = search_method_cards(artifact_root, "Custom Rank IC", knowledge_store=store)
    draft_search_before_publish = search_method_cards(
        artifact_root,
        "Custom Rank IC",
        include_drafts=True,
        knowledge_store=store,
    )
    missing_approval = publish_method_card(
        artifact_root=artifact_root,
        draft_method_card_id=draft_id,
        approved_method_card_id="method_card_custom_rank_ic_v1",
        approved_by="",
        approval_note="reviewed",
        approve=True,
        knowledge_store=store,
    )
    not_approved = publish_method_card(
        artifact_root=artifact_root,
        draft_method_card_id=draft_id,
        approved_method_card_id="method_card_custom_rank_ic_v1",
        approved_by="tester",
        approval_note="reviewed",
        approve=False,
        knowledge_store=store,
    )
    published = publish_method_card(
        artifact_root=artifact_root,
        draft_method_card_id=draft_id,
        approved_method_card_id="method_card_custom_rank_ic_v1",
        approved_by="tester",
        approval_note="reviewed",
        approve=True,
        knowledge_store=store,
    )
    duplicate = publish_method_card(
        artifact_root=artifact_root,
        draft_method_card_id=draft_id,
        approved_method_card_id="method_card_custom_rank_ic_v1",
        approved_by="tester",
        approval_note="reviewed",
        approve=True,
        knowledge_store=store,
    )
    conflicting_duplicate = publish_method_card(
        artifact_root=artifact_root,
        draft_method_card_id=draft_id,
        approved_method_card_id="method_card_custom_rank_ic_v1",
        approved_by="tester",
        approval_note="different review",
        approve=True,
        knowledge_store=store,
    )

    assert no_evidence.ok is False
    assert "evidence_ref is required" in no_evidence.errors[0]["message"]
    assert bad_locator.ok is False
    assert bad_locator.errors[0]["code"] == "method_card_draft_validation_failed"
    assert draft.ok is True
    assert draft.data["method_card_draft"]["status"] == "draft"
    assert get_method_card(artifact_root, draft_id, include_drafts=True, knowledge_store=store) is not None
    assert not default_search_before_publish
    assert draft_search_before_publish
    assert missing_approval.ok is False
    assert not_approved.ok is False
    assert published.ok is True
    assert published.data["method_card"]["status"] == "approved"
    assert published.data["method_card"]["source_method_card_id"] == draft_id
    assert get_method_card(artifact_root, draft_id, include_drafts=True, knowledge_store=store).status == "draft"
    assert duplicate.ok is True
    assert duplicate.data["idempotent"] is True
    assert conflicting_duplicate.ok is False


def test_math_validation_uses_persisted_approved_method_cards(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    store, evidence_ref = _store_with_evidence(artifact_root)
    draft = create_method_card_draft(
        artifact_root=artifact_root,
        method_id="rank_ic",
        title="Persisted Rank IC",
        family="signal_diagnostic",
        assumptions=("signals and labels are aligned",),
        inputs=("signals", "forward returns"),
        outputs=("rank correlation", "p-value"),
        failure_modes=("small sample size",),
        evidence_refs=(evidence_ref,),
        knowledge_store=store,
    )
    draft_id = draft.data["method_card_draft"]["method_card_id"]
    draft_contract = math_validate_method_contract(
        artifact_root=artifact_root,
        method_contract={
            "method_id": "rank_ic",
            "parameters": {"horizon": 5},
            "knowledge_evidence_refs": [{"method_card_id": draft_id}],
        },
        knowledge_store=store,
    )
    published = publish_method_card(
        artifact_root=artifact_root,
        draft_method_card_id=draft_id,
        approved_method_card_id="method_card_persisted_rank_ic_v1",
        approved_by="tester",
        approval_note="reviewed",
        approve=True,
        knowledge_store=store,
    )
    approved_contract = math_validate_method_contract(
        artifact_root=artifact_root,
        method_contract={
            "method_id": "rank_ic",
            "parameters": {"horizon": 5},
            "knowledge_evidence_refs": [{"method_card_id": published.data["method_card"]["method_card_id"]}],
        },
        knowledge_store=store,
    )

    assert draft_contract.ok is False
    assert "no approved method-card evidence" in draft_contract.data["method_validation_report"]["blockers"][0]
    assert approved_contract.ok is True
    assert "not in the seeded registry allowlist" in approved_contract.warnings[0]


def _store_with_evidence(artifact_root: Path) -> tuple[JsonKnowledgeStore, dict[str, object]]:
    store = JsonKnowledgeStore(artifact_root)
    source = KnowledgeSourceManifest(
        source_id="source_sma",
        title="SMA Source",
        source_type="internal_note",
        path=str(FIXTURE),
        file_hash="hash_sma",
        file_size_bytes=FIXTURE.stat().st_size,
        topics=("indicators",),
        method_families=("indicator",),
    )
    chunks = chunk_sections(source, extract_text(FIXTURE).sections)
    store.save_source(source)
    store.replace_chunks(source.source_id, chunks)
    evidence_ref = {
        "source_id": source.source_id,
        "chunk_id": chunks[0].chunk_id,
        "locator": dict(chunks[0].locator),
    }
    return store, evidence_ref
