"""Contracts for the maintained computational-method catalogue and validation.

Subject: Public method discovery and validation of parameters, invariants, and evidence requirements.
Level: In-process unit contract.
Collaborators: Maintained method definitions and an injected approved-card read port.
Guarantees: Known methods are listed and invalid parameters or missing evidence fail closed.
Non-goals: Implementation registration, fixture execution, packaging, diagnostics, or provider access.
"""

from __future__ import annotations

from pathlib import Path

from trader_research.knowledge.approved_cards import StoreBackedApprovedMethodCardReader
from trader_research.knowledge.domain import EvidenceReference, MethodCard
from trader_research.knowledge.store import JsonKnowledgeStore
from trader_research.methodology import (
    math_list_method_contracts,
    math_validate_method_contract,
)


def test_math_list_method_contracts_includes_core_and_planned_methods() -> None:
    """The public catalogue exposes every maintained and explicitly planned method contract."""
    result = math_list_method_contracts()

    assert result.ok is True
    method_ids = {method["method_id"] for method in result.data["methods"]}
    assert {"sma", "ema", "rsi", "rolling_volatility", "z_score", "rank_ic"}.issubset(
        method_ids
    )


def test_math_validate_method_contract_checks_parameters_and_evidence(
    tmp_path: Path,
) -> None:
    """Contract validation accepts sound parameters and enforces required approved evidence."""
    artifact_root = tmp_path / "artifacts"
    valid_sma = math_validate_method_contract(
        artifact_root=artifact_root,
        method_contract={
            "method_id": "sma",
            "parameters": {"period": 20},
            "no_lookahead": True,
        },
    )
    invalid_sma = math_validate_method_contract(
        artifact_root=artifact_root,
        method_contract={"method_id": "sma", "parameters": {"period": 1}},
    )
    missing_evidence = math_validate_method_contract(
        artifact_root=artifact_root,
        method_contract={"method_id": "rank_ic", "parameters": {"horizon": 5}},
    )
    store = JsonKnowledgeStore(artifact_root)
    store.save_method_card(
        MethodCard(
            method_card_id="method_card_rank_ic_validated_v1",
            method_card_set_id="method_card_set_rank_ic_test",
            revision_number=1,
            method_id="rank_ic",
            title="Rank IC",
            family="signal_diagnostic",
            status="approved",
            assumptions=("signals and labels are aligned",),
            inputs=("signals", "forward returns"),
            outputs=("rank correlation",),
            failure_modes=("small sample",),
            evidence_refs=(
                EvidenceReference(source_id="source_test", chunk_id="chunk_test"),
            ),
            source_methodology_candidate_id="methodology_candidate_rank_ic_test",
            validation_refs=(
                {
                    "artifact_type": "methodology_candidate_validation_report",
                    "artifact_id": "validation_rank_ic_test",
                },
            ),
        )
    )
    valid_rank_ic = math_validate_method_contract(
        artifact_root=artifact_root,
        method_contract={
            "method_id": "rank_ic",
            "parameters": {"horizon": 5},
            "knowledge_evidence_refs": [
                {"method_card_id": "method_card_rank_ic_validated_v1"}
            ],
        },
        approved_card_reader=StoreBackedApprovedMethodCardReader(store),
    )

    assert valid_sma.ok is True
    assert (
        valid_sma.data["method_validation_report"]["fixture_status"]
        == "not_run_in_slice_5_core"
    )
    assert invalid_sma.ok is False
    assert (
        "below minimum" in invalid_sma.data["method_validation_report"]["blockers"][0]
    )
    assert missing_evidence.ok is False
    assert (
        "approved method-card evidence is required"
        in missing_evidence.data["method_validation_report"]["blockers"]
    )
    assert valid_rank_ic.ok is True
