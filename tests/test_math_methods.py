from __future__ import annotations

from pathlib import Path

from trader_research.math_tools import math_list_method_contracts, math_validate_method_contract


def test_math_list_method_contracts_includes_core_and_planned_methods() -> None:
    result = math_list_method_contracts()

    assert result.ok is True
    method_ids = {method["method_id"] for method in result.data["methods"]}
    assert {"sma", "ema", "rsi", "rolling_volatility", "z_score", "rank_ic"}.issubset(method_ids)


def test_math_validate_method_contract_checks_parameters_and_evidence(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    valid_sma = math_validate_method_contract(
        artifact_root=artifact_root,
        method_contract={"method_id": "sma", "parameters": {"period": 20}, "no_lookahead": True},
    )
    invalid_sma = math_validate_method_contract(
        artifact_root=artifact_root,
        method_contract={"method_id": "sma", "parameters": {"period": 1}},
    )
    missing_evidence = math_validate_method_contract(
        artifact_root=artifact_root,
        method_contract={"method_id": "rank_ic", "parameters": {"horizon": 5}},
    )
    valid_rank_ic = math_validate_method_contract(
        artifact_root=artifact_root,
        method_contract={
            "method_id": "rank_ic",
            "parameters": {"horizon": 5},
            "knowledge_evidence_refs": [{"method_card_id": "method_card_rank_ic_seed_v1"}],
        },
    )

    assert valid_sma.ok is True
    assert valid_sma.data["method_validation_report"]["fixture_status"] == "not_run_in_slice_5_core"
    assert invalid_sma.ok is False
    assert "below minimum" in invalid_sma.data["method_validation_report"]["blockers"][0]
    assert missing_evidence.ok is False
    assert "approved method-card evidence is required" in missing_evidence.data["method_validation_report"]["blockers"]
    assert valid_rank_ic.ok is True
