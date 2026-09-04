"""Contracts for supplied computational-method registration and fixture validation.

Subject: Method implementation provenance, runtime conformance, registration, and deterministic fixtures.
Level: In-process application contract.
Collaborators: Maintained Trader interfaces, standard implementations, JSON cards, and temporary source files.
Guarantees: Accepted implementations match runtime contracts and produce inspectable fixture evidence.
Non-goals: Candidate code authoring, package admission, C++ compilation, experiments, or agent decisions.
"""

from __future__ import annotations

from pathlib import Path

from trader.signals import Signal
from trader_standard.signals import BollingerBwmaActionSignal

from trader_research.knowledge.approved_cards import StoreBackedApprovedMethodCardReader
from trader_research.knowledge.domain import EvidenceReference, MethodCard
from trader_research.knowledge.store import JsonKnowledgeStore
from trader_research.methodology import (
    math_list_method_contracts,
    math_register_method_implementation,
    math_run_indicator_fixtures,
    math_run_signal_fixtures,
    math_validate_method_contract,
)


METHODS = {
    "sma": {"period": 3},
    "ema": {"period": 3},
    "rsi": {"period": 5},
    "rolling_volatility": {"window": 3, "ddof": 1},
    "z_score": {"window": 3},
}


def test_maintained_indicator_registration_is_knowledge_provenance_neutral(
    tmp_path: Path,
) -> None:
    """Maintained indicators validate without fabricated knowledge provenance or method-card lineage."""
    artifact_root = tmp_path / "artifacts"

    for method_id, parameters in METHODS.items():
        registered = math_register_method_implementation(
            artifact_root=artifact_root,
            method_id=method_id,
            method_card_ids=[],
            method_contract=_contract(method_id, parameters),
        )

        assert registered.ok is True, registered.to_dict()
        manifest = registered.data["method_implementation_manifest"]
        assert manifest["method_card_ids"] == []
        assert manifest["source_provenance"]["validated"] is True
        validated = math_run_indicator_fixtures(
            artifact_root=artifact_root,
            implementation_manifest=manifest,
        )
        assert validated.ok is True, validated.to_dict()
        assert validated.data["indicator_validation_report"]["status"] == "passed"


def test_maintained_method_contract_catalog_is_immutable_and_store_independent(
    tmp_path: Path,
) -> None:
    """The maintained catalogue validates independently and cannot be mutated through knowledge storage."""
    store = JsonKnowledgeStore(tmp_path / "artifacts")
    listed = math_list_method_contracts()
    valid = math_validate_method_contract(
        artifact_root=tmp_path / "artifacts",
        method_contract={
            "method_id": "sma",
            "parameters": {"period": 5},
            "no_lookahead": True,
        },
    )
    invalid = math_validate_method_contract(
        artifact_root=tmp_path / "artifacts",
        method_contract={
            "method_id": "sma",
            "parameters": {"period": 1},
            "no_lookahead": True,
        },
    )

    assert listed.ok is True
    assert "sma" in {method["method_id"] for method in listed.data["methods"]}
    assert valid.ok is True
    assert invalid.data["method_validation_report"]["blockers"] == [
        "parameter period is below minimum 2.0"
    ]
    assert not hasattr(store, "save_method_contract")


def test_evidence_required_indicator_uses_approved_card_read_port(
    tmp_path: Path,
) -> None:
    """Evidence-gated indicators register and validate through the approved-card read port."""
    artifact_root = tmp_path / "artifacts"
    method_id = "bollinger_wma_band_rule"
    method_card_id = "method_card_bollinger_wma_band_rule_algorithmic_trading_v1"
    reader = _approved_reader(
        artifact_root, method_id, method_card_id, family="indicator"
    )

    registered = math_register_method_implementation(
        artifact_root=artifact_root,
        method_id=method_id,
        method_card_ids=[method_card_id],
        method_contract=_contract(
            method_id,
            {"period": 3, "stddev_multiplier": 2.0},
            method_card_id,
        ),
        approved_card_reader=reader,
    )

    assert registered.ok is True, registered.to_dict()
    validated = math_run_indicator_fixtures(
        artifact_root=artifact_root,
        implementation_manifest=registered.data["method_implementation_manifest"],
        approved_card_reader=reader,
    )
    assert validated.ok is True, validated.to_dict()
    assert (
        validated.data["indicator_validation_report"]["fixture_results"][0]["actual"][
            2
        ]["middle"]
        == 2.0
    )


def test_evidence_required_signal_registers_and_validates(tmp_path: Path) -> None:
    """Evidence-gated signals conform to Trader contracts and pass deterministic fixtures."""
    artifact_root = tmp_path / "artifacts"
    method_id = "bollinger_bwma_action_signal"
    method_card_id = "method_card_bollinger_bwma_action_signal_algorithmic_trading_v1"
    reader = _approved_reader(artifact_root, method_id, method_card_id, family="signal")
    assert isinstance(
        BollingerBwmaActionSignal(period=20, stddev_multiplier=2.0), Signal
    )

    registered = math_register_method_implementation(
        artifact_root=artifact_root,
        method_id=method_id,
        method_card_ids=[method_card_id],
        method_contract=_contract(
            method_id,
            {"period": 20, "stddev_multiplier": 2.0},
            method_card_id,
        ),
        approved_card_reader=reader,
    )
    validated = math_run_signal_fixtures(
        artifact_root=artifact_root,
        implementation_manifest=registered.data["method_implementation_manifest"],
        approved_card_reader=reader,
    )

    assert registered.ok is True, registered.to_dict()
    assert validated.ok is True, validated.to_dict()
    assert [
        row["actual"]
        for row in validated.data["signal_implementation_validation_report"][
            "fixture_results"
        ]
    ] == [
        1.0,
        -1.0,
        0.0,
    ]


def test_signal_fixture_failure_remains_inspectable(tmp_path: Path) -> None:
    """A failing signal fixture retains explicit status and result evidence."""
    artifact_root = tmp_path / "artifacts"
    method_id = "bollinger_bwma_action_signal"
    method_card_id = "method_card_bollinger_bwma_action_signal_algorithmic_trading_v1"
    reader = _approved_reader(artifact_root, method_id, method_card_id, family="signal")
    registered = math_register_method_implementation(
        artifact_root=artifact_root,
        method_id=method_id,
        method_card_ids=[method_card_id],
        method_contract=_contract(
            method_id,
            {"period": 20, "stddev_multiplier": 2.0},
            method_card_id,
        ),
        approved_card_reader=reader,
    )

    result = math_run_signal_fixtures(
        artifact_root=artifact_root,
        implementation_manifest=registered.data["method_implementation_manifest"],
        fixtures=[
            {"fixture_id": "insufficient_bars", "closes": [10.0] * 19, "expected": 0.0}
        ],
        approved_card_reader=reader,
    )

    assert result.ok is False
    report = result.data["signal_implementation_validation_report"]
    assert report["status"] == "failed"
    assert report["fixture_results"][0]["status"] == "failed"


def test_registration_rejects_runtime_contract_mismatch_after_evidence_check(
    tmp_path: Path,
) -> None:
    """Registration rejects source classes that violate the declared Trader runtime contract."""
    artifact_root = tmp_path / "artifacts"
    source = tmp_path / "plain.py"
    source.write_text(GENERATED_PLAIN_SOURCE, encoding="utf-8")
    reader = _approved_reader(
        artifact_root, "sma", "method_card_sma_validated_v1", family="indicator"
    )

    result = math_register_method_implementation(
        artifact_root=artifact_root,
        method_id="sma",
        method_card_ids=["method_card_sma_validated_v1"],
        method_contract=_contract("sma", {"period": 3}, "method_card_sma_validated_v1"),
        entrypoint=f"{source}:PlainImplementation",
        source_path=source,
        class_name="PlainImplementation",
        implementation_kind="generated",
        approved_card_reader=reader,
    )

    assert result.ok is False
    assert (
        "entrypoint is not a trader.indicators.Indicator subclass"
        in result.data["blockers"]
    )


def test_registration_rejects_unknown_card_and_source_hash_drift(
    tmp_path: Path,
) -> None:
    """Registration rejects unavailable approved cards and unexpected source-content changes."""
    artifact_root = tmp_path / "artifacts"
    reader = _approved_reader(
        artifact_root, "sma", "method_card_sma_validated_v1", family="indicator"
    )
    unknown = math_register_method_implementation(
        artifact_root=artifact_root,
        method_id="sma",
        method_card_ids=["method_card_missing"],
        method_contract=_contract("sma", {"period": 3}, "method_card_missing"),
        implementation_kind="generated",
        approved_card_reader=reader,
    )
    drift = math_register_method_implementation(
        artifact_root=artifact_root,
        method_id="sma",
        method_card_ids=[],
        method_contract=_contract("sma", {"period": 3}),
        expected_source_hash="not-the-real-hash",
    )

    assert any(
        "approved method-card evidence does not match" in blocker
        for blocker in unknown.data["blockers"]
    )
    assert "source hash does not match expected_source_hash" in drift.data["blockers"]


def _approved_reader(
    artifact_root: Path,
    method_id: str,
    method_card_id: str,
    *,
    family: str,
) -> StoreBackedApprovedMethodCardReader:
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
            assumptions=("ordered observations",),
            inputs=("price series",),
            outputs=("derived values",),
            failure_modes=("insufficient warmup",),
            evidence_refs=(
                EvidenceReference(source_id="source_test", chunk_id="chunk_test"),
            ),
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


def _contract(
    method_id: str,
    parameters: dict[str, object],
    method_card_id: str | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "method_id": method_id,
        "parameters": parameters,
        "no_lookahead": True,
    }
    if method_card_id is not None:
        payload["knowledge_evidence_refs"] = [{"method_card_id": method_card_id}]
    return payload


GENERATED_PLAIN_SOURCE = '''"""Citation-backed simple moving average implementation.

Source reference:
- Approved method card: ``method_card_sma_validated_v1``.
- Registry method: ``sma``.

Implements:
- Entrypoint ``PlainImplementation``.
- Trader runtime contract ``trader.indicators.Indicator``.
- Warmup behavior is one complete trailing period.
- No lookahead: every output uses only its trailing window.
"""


class PlainImplementation:
    pass
'''
