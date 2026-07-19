"""Canonical method-card fixtures shared by methodology tests."""

from pathlib import Path

from trader_research.knowledge.approved_cards import StoreBackedApprovedMethodCardReader
from trader_research.knowledge.domain import EvidenceReference, MethodCard
from trader_research.knowledge.store import JsonKnowledgeStore


def approved_method_card_reader(
    artifact_root: Path,
    *,
    method_id: str,
    method_card_id: str,
    family: str,
) -> StoreBackedApprovedMethodCardReader:
    """Persist one canonical approved card and return its narrow read adapter."""
    store = JsonKnowledgeStore(artifact_root)
    store.save_method_card(
        MethodCard(
            method_card_id=method_card_id,
            method_card_set_id=f"method_card_set_{method_id}_test",
            revision_number=1,
            method_id=method_id,
            title=method_id.replace("_", " ").title(),
            family=family,
            status="approved",
            assumptions=("declared assumptions hold",),
            inputs=("declared inputs",),
            outputs=("declared outputs",),
            failure_modes=("declared assumptions fail",),
            evidence_refs=(EvidenceReference(source_id="source_test", chunk_id="chunk_test"),),
            source_methodology_candidate_id=f"methodology_candidate_{method_id}_test",
            validation_refs=(
                {
                    "artifact_type": "methodology_candidate_validation_report",
                    "artifact_id": f"validation_{method_id}_test",
                },
            ),
        )
    )
    return StoreBackedApprovedMethodCardReader(store)
