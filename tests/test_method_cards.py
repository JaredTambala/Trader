from __future__ import annotations

from pathlib import Path

from trader_research.artifact_store import InMemoryResearchArtifactStore
from trader_research.knowledge.chunking import chunk_sections
from trader_research.domain import METHODOLOGY_CANDIDATE, METHODOLOGY_CANDIDATE_VALIDATION_REPORT
from trader_research.knowledge.domain import (
    EvidenceBackedField,
    EvidenceReference,
    KnowledgeSourceManifest,
    MethodologyCandidate,
    MethodologyCandidateValidationReport,
    RICH_METHOD_CARD_FORMAT,
)
from trader_research.knowledge.extractors import extract_text
from trader_research.knowledge.method_cards import (
    create_method_card_draft,
    create_rich_method_card_draft,
    get_rich_method_card,
    get_method_card_set,
    has_approved_method_card,
    get_method_card,
    list_method_card_sets,
    publish_method_card,
    search_method_cards,
    update_method_card_status,
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


def test_method_card_lifecycle_update_retires_persisted_cards_from_search(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    store, evidence_ref = _store_with_evidence(artifact_root)
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
    published = publish_method_card(
        artifact_root=artifact_root,
        draft_method_card_id=draft_id,
        approved_method_card_id="method_card_custom_rank_ic_v1",
        approved_by="tester",
        approval_note="reviewed",
        approve=True,
        knowledge_store=store,
    )
    invalid_status = update_method_card_status(
        artifact_root=artifact_root,
        method_card_id=draft_id,
        status="approved",
        updated_by="tester",
        note="not allowed",
        knowledge_store=store,
    )
    missing_replacement = update_method_card_status(
        artifact_root=artifact_root,
        method_card_id="method_card_custom_rank_ic_v1",
        status="superseded",
        updated_by="tester",
        note="replacement required",
        knowledge_store=store,
    )
    rejected_draft = update_method_card_status(
        artifact_root=artifact_root,
        method_card_id=draft_id,
        status="rejected",
        updated_by="tester",
        note="draft was created during cleanup test",
        knowledge_store=store,
    )
    superseded_approved = update_method_card_status(
        artifact_root=artifact_root,
        method_card_id="method_card_custom_rank_ic_v1",
        status="superseded",
        updated_by="tester",
        note="newer reviewed card exists",
        superseded_by_method_card_id="method_card_custom_rank_ic_v2",
        knowledge_store=store,
    )
    visible_after_retirement = search_method_cards(
        artifact_root,
        "Custom Rank IC",
        include_drafts=True,
        knowledge_store=store,
    )
    persisted = {card.method_card_id: card for card in store.list_persisted_method_cards()}

    assert published.ok is True
    assert invalid_status.ok is False
    assert "status must be one of" in invalid_status.errors[0]["message"]
    assert missing_replacement.ok is False
    assert "superseded_by_method_card_id is required" in missing_replacement.errors[0]["message"]
    assert rejected_draft.ok is True
    assert rejected_draft.data["method_card"]["status"] == "rejected"
    assert superseded_approved.ok is True
    assert superseded_approved.data["previous_status"] == "approved"
    assert visible_after_retirement == tuple()
    assert persisted[draft_id].status == "rejected"
    assert persisted["method_card_custom_rank_ic_v1"].status == "superseded"
    assert "Lifecycle approved -> superseded" in str(persisted["method_card_custom_rank_ic_v1"].approval_note)


def test_method_card_set_lineage_groups_revisions_and_current_pointer(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    store, evidence_ref = _store_with_evidence(artifact_root)
    method_card_set_id = "method_card_set_custom_rank_ic"
    draft_v1 = create_method_card_draft(
        artifact_root=artifact_root,
        method_id="custom_rank_ic",
        title="Custom Rank IC",
        family="signal_diagnostic",
        assumptions=("signals and labels are aligned",),
        inputs=("signals",),
        outputs=("rank correlation",),
        failure_modes=("small sample size",),
        evidence_refs=(evidence_ref,),
        version=1,
        method_card_set_id=method_card_set_id,
        knowledge_store=store,
    )
    publish_v1 = publish_method_card(
        artifact_root=artifact_root,
        draft_method_card_id=draft_v1.data["method_card_draft"]["method_card_id"],
        approved_method_card_id="method_card_custom_rank_ic_v1",
        approved_by="tester",
        approval_note="reviewed v1",
        approve=True,
        knowledge_store=store,
    )
    draft_v2 = create_method_card_draft(
        artifact_root=artifact_root,
        method_id="custom_rank_ic",
        title="Custom Rank IC",
        family="signal_diagnostic",
        assumptions=("signals and labels are aligned",),
        inputs=("signals",),
        outputs=("rank correlation",),
        failure_modes=("small sample size",),
        evidence_refs=(evidence_ref,),
        version=2,
        method_card_set_id=method_card_set_id,
        knowledge_store=store,
    )
    publish_v2 = publish_method_card(
        artifact_root=artifact_root,
        draft_method_card_id=draft_v2.data["method_card_draft"]["method_card_id"],
        approved_method_card_id="method_card_custom_rank_ic_v2",
        approved_by="tester",
        approval_note="reviewed v2",
        approve=True,
        knowledge_store=store,
    )
    set_listing = list_method_card_sets(
        artifact_root,
        method_id="custom_rank_ic",
        include_retired=True,
        knowledge_store=store,
    )
    set_detail = get_method_card_set(
        artifact_root,
        method_card_set_id=method_card_set_id,
        knowledge_store=store,
    )
    persisted = {card.method_card_id: card for card in store.list_persisted_method_cards()}

    assert publish_v1.ok is True
    assert publish_v2.ok is True
    assert publish_v2.data["method_card"]["method_card_set_id"] == method_card_set_id
    assert publish_v2.data["method_card"]["supersedes_method_card_id"] == "method_card_custom_rank_ic_v1"
    assert persisted["method_card_custom_rank_ic_v1"].status == "superseded"
    assert persisted["method_card_custom_rank_ic_v2"].status == "approved"
    assert set_listing.ok is True
    assert set_listing.data["method_card_set_count"] == 1
    method_card_set = set_listing.data["method_card_sets"][0]
    assert method_card_set["method_card_set_id"] == method_card_set_id
    assert method_card_set["current_approved_method_card_id"] == "method_card_custom_rank_ic_v2"
    assert method_card_set["current_draft_method_card_id"] is None
    assert method_card_set["revision_count"] == 4
    assert method_card_set["status_counts"] == {"approved": 1, "draft": 2, "superseded": 1}
    assert set_detail.ok is True
    assert set_detail.data["revision_count"] == 4
    assert {row["method_card_id"] for row in set_detail.data["revision_history"]} == {
        draft_v1.data["method_card_draft"]["method_card_id"],
        "method_card_custom_rank_ic_v1",
        draft_v2.data["method_card_draft"]["method_card_id"],
        "method_card_custom_rank_ic_v2",
    }


def test_rich_method_card_draft_publish_preserves_rich_payload_and_shallow_search(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    store, evidence_ref = _store_with_evidence(artifact_root)
    artifact_store = InMemoryResearchArtifactStore()
    validation_report = _persist_pairs_methodology_validation(artifact_store, evidence_ref)

    draft = create_rich_method_card_draft(
        artifact_root=artifact_root,
        methodology_candidate_validation_id=validation_report["validation_id"],
        method_id="cointegration_pairs_method",
        title="Cointegration Pairs Method",
        family="statistical_arbitrage",
        knowledge_store=store,
        artifact_store=artifact_store,
    )
    draft_id = draft.data["method_card_draft"]["method_card_id"]
    shallow_search = search_method_cards(
        artifact_root,
        "Cointegration",
        include_drafts=True,
        knowledge_store=store,
    )
    published = publish_method_card(
        artifact_root=artifact_root,
        draft_method_card_id=draft_id,
        approved_method_card_id="method_card_rich_pairs_rank_ic_v1",
        approved_by="tester",
        approval_note="reviewed rich methodology evidence",
        approve=True,
        knowledge_store=store,
    )

    assert draft.ok is True
    assert draft.data["method_card_draft"]["card_format"] == RICH_METHOD_CARD_FORMAT
    assert draft.data["method_card_draft"]["status"] == "draft"
    assert shallow_search[0].method_card_id == draft_id
    assert "core_fields" not in shallow_search[0].to_dict()
    assert published.ok is True
    assert published.data["method_card"]["card_format"] == RICH_METHOD_CARD_FORMAT
    assert published.data["method_card"]["status"] == "approved"
    rich = get_rich_method_card(
        artifact_root,
        "method_card_rich_pairs_rank_ic_v1",
        knowledge_store=store,
    )
    assert rich is not None
    assert rich.extension_fields["statistical_arbitrage"]["spread_definition"].value
    assert has_approved_method_card(
        artifact_root,
        ["method_card_rich_pairs_rank_ic_v1"],
        method_id="cointegration_pairs_method",
        knowledge_store=store,
    )


def test_rich_method_card_lifecycle_update_preserves_payload_and_hides_card(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    store, evidence_ref = _store_with_evidence(artifact_root)
    artifact_store = InMemoryResearchArtifactStore()
    validation_report = _persist_pairs_methodology_validation(artifact_store, evidence_ref)
    draft = create_rich_method_card_draft(
        artifact_root=artifact_root,
        methodology_candidate_validation_id=validation_report["validation_id"],
        method_id="cointegration_pairs_method",
        title="Cointegration Pairs Method",
        family="statistical_arbitrage",
        knowledge_store=store,
        artifact_store=artifact_store,
    )
    published = publish_method_card(
        artifact_root=artifact_root,
        draft_method_card_id=draft.data["method_card_draft"]["method_card_id"],
        approved_method_card_id="method_card_rich_pairs_rank_ic_v1",
        approved_by="tester",
        approval_note="reviewed rich methodology evidence",
        approve=True,
        knowledge_store=store,
    )
    retired = update_method_card_status(
        artifact_root=artifact_root,
        method_card_id="method_card_rich_pairs_rank_ic_v1",
        status="superseded",
        updated_by="tester",
        note="newer richer card exists",
        superseded_by_method_card_id="method_card_rich_pairs_rank_ic_v2",
        knowledge_store=store,
    )
    persisted_rich = {
        card.method_card_id: card
        for card in store.list_persisted_rich_method_cards()
    }

    assert published.ok is True
    assert retired.ok is True
    assert get_rich_method_card(
        artifact_root,
        "method_card_rich_pairs_rank_ic_v1",
        include_drafts=True,
        knowledge_store=store,
    ) is None
    assert has_approved_method_card(
        artifact_root,
        ["method_card_rich_pairs_rank_ic_v1"],
        method_id="cointegration_pairs_method",
        knowledge_store=store,
    ) is False
    assert persisted_rich["method_card_rich_pairs_rank_ic_v1"].status == "superseded"
    assert persisted_rich["method_card_rich_pairs_rank_ic_v1"].extension_fields[
        "statistical_arbitrage"
    ]["spread_definition"].value
    assert persisted_rich["method_card_rich_pairs_rank_ic_v1"].lineage["superseded_by_method_card_id"] == (
        "method_card_rich_pairs_rank_ic_v2"
    )


def test_rich_method_card_draft_rejects_non_passed_validation_and_missing_stores(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    store, evidence_ref = _store_with_evidence(artifact_root)
    artifact_store = InMemoryResearchArtifactStore()
    validation_report = {
        **_persist_pairs_methodology_validation(artifact_store, evidence_ref),
        "status": "blocked",
        "valid": False,
        "blockers": ["missing evidence"],
    }

    blocked = create_rich_method_card_draft(
        artifact_root=artifact_root,
        methodology_candidate_validation_report=validation_report,
        knowledge_store=store,
        artifact_store=artifact_store,
    )
    no_knowledge_store = create_rich_method_card_draft(
        artifact_root=artifact_root,
        methodology_candidate_validation_report=validation_report,
        artifact_store=artifact_store,
    )

    assert blocked.ok is False
    assert "status=passed" in blocked.errors[0]["message"]
    assert no_knowledge_store.ok is False
    assert "knowledge store is required" in no_knowledge_store.errors[0]["message"]


def test_rich_method_card_draft_rejects_unsupported_identity_overrides(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    store, evidence_ref = _store_with_evidence(artifact_root)
    artifact_store = InMemoryResearchArtifactStore()
    validation_report = _persist_pairs_methodology_validation(artifact_store, evidence_ref)

    bad_method_id = create_rich_method_card_draft(
        artifact_root=artifact_root,
        methodology_candidate_validation_id=validation_report["validation_id"],
        method_id="rank_ic",
        title="Cointegration Pairs Method",
        family="statistical_arbitrage",
        knowledge_store=store,
        artifact_store=artifact_store,
    )
    bad_title = create_rich_method_card_draft(
        artifact_root=artifact_root,
        methodology_candidate_validation_id=validation_report["validation_id"],
        method_id="cointegration_pairs_method",
        title="Pairs Mean Reversion",
        family="statistical_arbitrage",
        knowledge_store=store,
        artifact_store=artifact_store,
    )
    bad_family = create_rich_method_card_draft(
        artifact_root=artifact_root,
        methodology_candidate_validation_id=validation_report["validation_id"],
        method_id="cointegration_pairs_method",
        title="Cointegration Pairs Method",
        family="technical_indicators",
        knowledge_store=store,
        artifact_store=artifact_store,
    )

    assert bad_method_id.ok is False
    assert "method_id must be derived" in bad_method_id.errors[0]["message"]
    assert bad_title.ok is False
    assert "title must be supported" in bad_title.errors[0]["message"]
    assert bad_family.ok is False
    assert "family override must match" in bad_family.errors[0]["message"]


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


def _persist_pairs_methodology_validation(
    artifact_store: InMemoryResearchArtifactStore,
    evidence_ref: dict[str, object],
) -> dict[str, object]:
    ref = EvidenceReference.from_dict(evidence_ref)

    def field(value: object) -> EvidenceBackedField:
        return EvidenceBackedField(value=value, evidence_refs=(ref,))

    candidate = MethodologyCandidate(
        methodology_candidate_id="methodology_candidate_pairs_card",
        title="Cointegration Pairs Method",
        families=("statistical_arbitrage",),
        status="extracted",
        source_ids=(str(evidence_ref["source_id"]),),
        chunk_ids=(str(evidence_ref["chunk_id"]),),
        core_fields={
            "identity": {"method_name": field("Cointegration Pairs Method")},
            "data_requirements": {"required_inputs": field(("price series",))},
            "signal_decision_logic": {
                "entry_rules": field("enter on spread z-score divergence"),
                "exit_rules": field("exit when spread mean reverts"),
            },
            "risk_validation": {
                "assumptions": field("spread is mean reverting after relationship validation"),
                "failure_modes": field("structural break in pair relationship"),
            },
        },
        extension_fields={
            "statistical_arbitrage": {
                "spread_definition": field("spread between two related assets"),
                "hedge_ratio_method": field("regression hedge ratio"),
                "cointegration_test": field("cointegration test evidence"),
                "entry_zscore": field("entry z-score threshold"),
                "exit_zscore": field("exit near zero z-score"),
            }
        },
        method_identity={
            "canonical_name": "Cointegration Pairs Method",
            "source_name": "Cointegration Pairs Method",
            "aliases": ["Cointegration Pairs Method"],
            "abbreviations": [],
            "identity_evidence_unit_ids": [str(evidence_ref["chunk_id"])],
        },
        lineage={"evidence_packet_id": "methodology_evidence_packet_pairs_card"},
    )
    candidate_record = artifact_store.save_artifact(
        artifact_type=METHODOLOGY_CANDIDATE,
        artifact_id=candidate.methodology_candidate_id,
        payload=candidate.to_dict(),
        status=candidate.status,
    )
    report = MethodologyCandidateValidationReport(
        validation_id="methodology_candidate_validation_pairs_card",
        methodology_candidate_id=candidate.methodology_candidate_id,
        status="passed",
        valid=True,
        candidate_ref=candidate_record.reference().to_dict(),
        checked_refs=(ref.to_dict(),),
        field_summary={"populated_field_count": 9},
        source_summary={"source_ids": [evidence_ref["source_id"]]},
        readiness_summary={
            "source": "methodology_evidence_packet",
            "family": "statistical_arbitrage",
            "evidence_packet_id": "methodology_evidence_packet_pairs_card",
            "descriptive": {"status": "passed", "required_roles": [], "missing_roles": []},
            "implementation": {"status": "passed", "required_roles": [], "missing_roles": []},
            "signal": {"status": "passed", "required_roles": [], "missing_roles": []},
            "strategy_template": {"status": "passed", "required_roles": [], "missing_roles": []},
        },
    )
    artifact_store.save_artifact(
        artifact_type=METHODOLOGY_CANDIDATE_VALIDATION_REPORT,
        artifact_id=report.validation_id,
        payload=report.to_dict(),
        status=report.status,
    )
    return report.to_dict()
