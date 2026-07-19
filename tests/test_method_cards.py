from __future__ import annotations

from pathlib import Path

from trader_research.foundation.artifacts import InMemoryResearchArtifactStore
from trader_research.governance.artifacts import (
    METHODOLOGY_CANDIDATE,
    METHODOLOGY_CANDIDATE_VALIDATION_REPORT,
    OWNER_BY_ARTIFACT_TYPE,
)
from trader_research.knowledge.approved_cards import StoreBackedApprovedMethodCardReader
from trader_research.knowledge.chunking import chunk_sections
from trader_research.knowledge.domain import (
    EvidenceBackedField,
    EvidenceReference,
    KnowledgeSourceManifest,
    MethodologyCandidate,
    MethodologyCandidateValidationReport,
)
from trader_research.knowledge.extractors import extract_text
from trader_research.knowledge.method_cards import (
    create_method_card_draft,
    get_method_card,
    get_method_card_set,
    list_method_card_sets,
    publish_method_card,
    search_method_cards,
    update_method_card_status,
)
from trader_research.knowledge.store import JsonKnowledgeStore


FIXTURE = Path("tests/fixtures/knowledge/sma_method.md")


def test_validated_candidate_creates_only_canonical_method_card_draft(tmp_path: Path) -> None:
    artifact_root, store, artifact_store, validation = _validated_pairs_context(tmp_path)

    draft = create_method_card_draft(
        artifact_root=artifact_root,
        methodology_candidate_validation_id=validation["validation_id"],
        method_id="cointegration_pairs_method",
        title="Cointegration Pairs Method",
        family="statistical_arbitrage",
        knowledge_store=store,
        artifact_store=artifact_store,
    )

    assert draft.ok is True
    payload = draft.data["method_card_draft"]
    assert payload["artifact_type"] == "method_card_draft"
    assert payload["source_methodology_candidate_id"] == "methodology_candidate_pairs_card"
    assert payload["validation_refs"]
    assert payload["evidence_refs"]
    assert "card_format" not in payload
    assert "core_fields" in payload
    assert "extension_fields" in payload

    summary = search_method_cards(
        artifact_root,
        "Cointegration",
        include_drafts=True,
        knowledge_store=store,
    )[0]
    assert summary.to_dict()["read_model"] == "method_card_summary"
    assert "core_fields" not in summary.to_dict()


def test_publish_preserves_complete_card_and_approved_reader_is_read_only(tmp_path: Path) -> None:
    artifact_root, store, artifact_store, validation = _validated_pairs_context(tmp_path)
    draft = _create_pairs_draft(artifact_root, store, artifact_store, validation)
    draft_id = draft.data["method_card_draft"]["method_card_id"]

    published = publish_method_card(
        artifact_root=artifact_root,
        draft_method_card_id=draft_id,
        approved_method_card_id="method_card_pairs_v1",
        approved_by="tester",
        approval_note="reviewed methodology evidence",
        approve=True,
        knowledge_store=store,
    )
    duplicate = publish_method_card(
        artifact_root=artifact_root,
        draft_method_card_id=draft_id,
        approved_method_card_id="method_card_pairs_v1",
        approved_by="tester",
        approval_note="reviewed methodology evidence",
        approve=True,
        knowledge_store=store,
    )

    assert published.ok is True
    assert duplicate.ok is True
    assert duplicate.data["idempotent"] is True
    card = get_method_card(artifact_root, "method_card_pairs_v1", knowledge_store=store)
    assert card is not None
    assert card.extension_fields["statistical_arbitrage"]["spread_definition"].value
    reader = StoreBackedApprovedMethodCardReader(store)
    assert reader.has_approved_method_card(("method_card_pairs_v1",), method_id="cointegration_pairs_method")
    assert not hasattr(reader, "save_method_card")


def test_method_card_lifecycle_and_revision_set_keep_complete_lineage(tmp_path: Path) -> None:
    artifact_root, store, artifact_store, validation = _validated_pairs_context(tmp_path)
    draft_v1 = _create_pairs_draft(artifact_root, store, artifact_store, validation, version=1)
    publish_v1 = publish_method_card(
        artifact_root=artifact_root,
        draft_method_card_id=draft_v1.data["method_card_draft"]["method_card_id"],
        approved_method_card_id="method_card_pairs_v1",
        approved_by="tester",
        approval_note="reviewed v1",
        approve=True,
        knowledge_store=store,
    )
    draft_v2 = _create_pairs_draft(artifact_root, store, artifact_store, validation, version=2)
    publish_v2 = publish_method_card(
        artifact_root=artifact_root,
        draft_method_card_id=draft_v2.data["method_card_draft"]["method_card_id"],
        approved_method_card_id="method_card_pairs_v2",
        approved_by="tester",
        approval_note="reviewed v2",
        approve=True,
        knowledge_store=store,
    )

    assert publish_v1.ok is True
    assert publish_v2.ok is True
    set_id = publish_v2.data["method_card"]["method_card_set_id"]
    detail = get_method_card_set(
        artifact_root,
        method_card_set_id=set_id,
        knowledge_store=store,
    )
    listing = list_method_card_sets(
        artifact_root,
        method_id="cointegration_pairs_method",
        include_retired=True,
        knowledge_store=store,
    )
    persisted = {card.method_card_id: card for card in store.list_persisted_method_cards()}
    assert persisted["method_card_pairs_v1"].status == "superseded"
    assert persisted["method_card_pairs_v1"].extension_fields["statistical_arbitrage"]
    assert persisted["method_card_pairs_v2"].status == "approved"
    assert detail.ok is True
    assert detail.data["revision_count"] == 4
    assert listing.data["method_card_sets"][0]["current_approved_method_card_id"] == "method_card_pairs_v2"


def test_retired_card_is_hidden_but_remains_auditable(tmp_path: Path) -> None:
    artifact_root, store, artifact_store, validation = _validated_pairs_context(tmp_path)
    draft = _create_pairs_draft(artifact_root, store, artifact_store, validation)
    publish_method_card(
        artifact_root=artifact_root,
        draft_method_card_id=draft.data["method_card_draft"]["method_card_id"],
        approved_method_card_id="method_card_pairs_v1",
        approved_by="tester",
        approval_note="reviewed",
        approve=True,
        knowledge_store=store,
    )

    retired = update_method_card_status(
        artifact_root=artifact_root,
        method_card_id="method_card_pairs_v1",
        status="superseded",
        updated_by="tester",
        note="newer validated card exists",
        superseded_by_method_card_id="method_card_pairs_v2",
        knowledge_store=store,
    )

    assert retired.ok is True
    assert get_method_card(
        artifact_root,
        "method_card_pairs_v1",
        include_drafts=True,
        knowledge_store=store,
    ) is None
    stored = {card.method_card_id: card for card in store.list_persisted_method_cards()}
    assert stored["method_card_pairs_v1"].status == "superseded"
    assert stored["method_card_pairs_v1"].lineage["superseded_by_method_card_id"] == "method_card_pairs_v2"


def test_draft_creation_fails_closed_for_invalid_lineage_and_missing_stores(tmp_path: Path) -> None:
    artifact_root, store, artifact_store, validation = _validated_pairs_context(tmp_path)
    blocked_validation = {
        **validation,
        "status": "blocked",
        "valid": False,
        "blockers": ["missing evidence"],
    }

    blocked = create_method_card_draft(
        artifact_root=artifact_root,
        methodology_candidate_validation_report=blocked_validation,
        knowledge_store=store,
        artifact_store=artifact_store,
    )
    no_knowledge_store = create_method_card_draft(
        artifact_root=artifact_root,
        methodology_candidate_validation_report=validation,
        artifact_store=artifact_store,
    )
    no_artifact_store = create_method_card_draft(
        artifact_root=artifact_root,
        methodology_candidate_validation_report=validation,
        knowledge_store=store,
    )

    assert blocked.ok is False
    assert "status=passed" in blocked.errors[0]["message"]
    assert "knowledge store is required" in no_knowledge_store.errors[0]["message"]
    assert "research artifact store is required" in no_artifact_store.errors[0]["message"]


def test_draft_creation_rejects_semantically_unsupported_overrides(tmp_path: Path) -> None:
    artifact_root, store, artifact_store, validation = _validated_pairs_context(tmp_path)

    result = create_method_card_draft(
        artifact_root=artifact_root,
        methodology_candidate_validation_id=validation["validation_id"],
        method_id="rank_ic",
        title="Unrelated Method",
        family="technical_indicators",
        knowledge_store=store,
        artifact_store=artifact_store,
    )

    assert result.ok is False
    message = result.errors[0]["message"]
    assert "method_id must be derived" in message
    assert "title must be supported" in message
    assert "family override must match" in message


def _create_pairs_draft(
    artifact_root: Path,
    store: JsonKnowledgeStore,
    artifact_store: InMemoryResearchArtifactStore,
    validation: dict[str, object],
    *,
    version: int = 1,
):
    return create_method_card_draft(
        artifact_root=artifact_root,
        methodology_candidate_validation_id=str(validation["validation_id"]),
        method_id="cointegration_pairs_method",
        title="Cointegration Pairs Method",
        family="statistical_arbitrage",
        version=version,
        knowledge_store=store,
        artifact_store=artifact_store,
    )


def _validated_pairs_context(
    tmp_path: Path,
) -> tuple[Path, JsonKnowledgeStore, InMemoryResearchArtifactStore, dict[str, object]]:
    artifact_root = tmp_path / "artifacts"
    store, evidence_ref = _store_with_evidence(artifact_root)
    artifact_store = InMemoryResearchArtifactStore()
    validation = _persist_pairs_methodology_validation(artifact_store, evidence_ref)
    return artifact_root, store, artifact_store, validation


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
    return store, {
        "source_id": source.source_id,
        "chunk_id": chunks[0].chunk_id,
        "locator": dict(chunks[0].locator),
    }


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
        agent_owner=OWNER_BY_ARTIFACT_TYPE[METHODOLOGY_CANDIDATE],
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
        agent_owner=OWNER_BY_ARTIFACT_TYPE[METHODOLOGY_CANDIDATE_VALIDATION_REPORT],
        artifact_type=METHODOLOGY_CANDIDATE_VALIDATION_REPORT,
        artifact_id=report.validation_id,
        payload=report.to_dict(),
        status=report.status,
    )
    return report.to_dict()
