from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from trader.risk import RiskContext, RiskManager
from trader_research.domain import RISK_MANAGER_CANDIDATE, RISK_MANAGER_IMPLEMENTATION, RiskManagerCandidateManifest
from trader_research.knowledge.domain import EvidenceBackedField, EvidenceReference, RichMethodCard
from trader_research.method_implementations.manifest import INDICATOR_RUNTIME_CONTRACT
from trader_research.methods.packages import MethodPackageManifest, method_package_path
from trader_research.risk_managers import (
    RESEARCH_CREATE_RISK_MANAGER_CANDIDATE,
    RESEARCH_LIST_RISK_MANAGER_TEMPLATES,
    SUPPORTED_RISK_MANAGER_FAMILIES,
    create_risk_manager_candidate,
    list_risk_manager_templates,
    risk_manager_candidate_path,
    validate_risk_manager_candidate,
)


def test_list_risk_manager_templates_returns_deterministic_catalog() -> None:
    envelope = list_risk_manager_templates()
    payload = envelope.to_dict()

    assert payload["ok"] is True
    assert payload["command"] == RESEARCH_LIST_RISK_MANAGER_TEMPLATES
    assert payload["agent_owner"] == "Quant Research Supervisor Agent"
    assert payload["side_effect"] == "read_only"
    assert payload["data"]["supported_risk_manager_families"] == list(SUPPORTED_RISK_MANAGER_FAMILIES)
    assert payload["data"]["template_count"] == 5
    assert [item["template_family"] for item in payload["data"]["templates"]] == list(
        SUPPORTED_RISK_MANAGER_FAMILIES
    )

    gross_exposure = payload["data"]["templates"][0]
    assert gross_exposure["template_family"] == "gross_exposure_cap"
    assert gross_exposure["runtime_contract"] == "trader.risk.RiskManager"
    assert gross_exposure["parameters"][0]["name"] == "max_gross_exposure"
    assert gross_exposure["validation_requirements"]["requires_strategy_risk_stack_validation"] is True


def test_list_risk_manager_templates_rejects_unknown_family() -> None:
    payload = list_risk_manager_templates(families=["unknown"]).to_dict()

    assert payload["ok"] is False
    assert payload["errors"][0]["code"] == "unsupported_risk_manager_template"
    assert payload["data"]["supported_risk_manager_families"] == list(SUPPORTED_RISK_MANAGER_FAMILIES)


def test_create_risk_manager_candidate_writes_importable_source(tmp_path: Path) -> None:
    envelope = create_risk_manager_candidate(
        artifact_root=tmp_path,
        template_family="gross_exposure_cap",
        parameters={"max_gross_exposure": 100_000.0},
    )
    payload = envelope.to_dict()

    assert payload["ok"] is True
    assert payload["command"] == RESEARCH_CREATE_RISK_MANAGER_CANDIDATE
    assert payload["agent_owner"] == "Quant Research Supervisor Agent"
    assert payload["side_effect"] == "local_mutating"

    manifest = payload["data"]["risk_manager_candidate_manifest"]
    persisted_path = risk_manager_candidate_path(tmp_path, manifest["candidate_id"])
    source_path = Path(manifest["risk_manager_source"]["path"])
    assert persisted_path.exists()
    assert source_path.exists()
    assert payload["artifacts"]["risk_manager_candidate"]["artifact_type"] == RISK_MANAGER_CANDIDATE
    assert payload["artifacts"]["risk_manager_candidate"]["path"] == str(persisted_path)
    assert payload["artifacts"]["risk_manager_source"]["artifact_type"] == RISK_MANAGER_IMPLEMENTATION
    assert manifest["artifact_type"] == RISK_MANAGER_CANDIDATE
    assert manifest["template_family"] == "gross_exposure_cap"
    assert manifest["risk_manager_source"]["runtime_contract"] == "trader.risk.RiskManager"
    assert manifest["execution_assumptions"]["backtest_only"] is True
    assert manifest["execution_assumptions"]["live_trading_allowed"] is False
    assert "symbols" not in manifest
    assert "timeframe" not in manifest
    assert RiskManagerCandidateManifest.from_dict(manifest).to_dict() == manifest

    module = _load_module(source_path)
    manager = module.build_risk_manager()
    assert isinstance(manager, RiskManager)
    approved, rejected = manager.evaluate(
        [{"symbol": "BTC/USD", "qty": 1.0, "side": "buy"}],
        RiskContext(
            positions={},
            open_orders=[],
            price_lookup={"BTC/USD": 100.0},
            run_id="run_demo",
            cycle_id="cycle_demo",
            decision_ts=datetime(2026, 1, 1, tzinfo=timezone.utc),
        ),
    )
    assert approved == [{"symbol": "BTC/USD", "qty": 1.0, "side": "buy"}]
    assert rejected == []


def test_create_risk_manager_candidate_uses_package_refs_and_deterministic_ids(tmp_path: Path) -> None:
    package = _indicator_package("method_package_risk_measure")
    package_path = method_package_path(tmp_path, package["package_id"])
    package_path.parent.mkdir(parents=True, exist_ok=True)
    package_path.write_text(json.dumps(package, indent=2, sort_keys=True), encoding="utf-8")

    by_inline = create_risk_manager_candidate(
        artifact_root=tmp_path,
        template_family="var_cvar_limit",
        parameters={"max_var_fraction": 0.05, "max_cvar_fraction": 0.08},
        method_package_refs=[{"role": "risk_measure", "package_manifest": package}],
    ).to_dict()
    by_id = create_risk_manager_candidate(
        artifact_root=tmp_path,
        template_family="var_cvar_limit",
        parameters={"max_var_fraction": 0.05, "max_cvar_fraction": 0.08},
        method_package_refs=[{"role": "risk_measure", "package_id": package["package_id"]}],
    ).to_dict()

    inline_manifest = by_inline["data"]["risk_manager_candidate_manifest"]
    id_manifest = by_id["data"]["risk_manager_candidate_manifest"]
    assert by_inline["ok"] is True
    assert by_id["ok"] is True
    assert inline_manifest["candidate_id"] == id_manifest["candidate_id"]
    assert inline_manifest["method_package_refs"][0]["role"] == "risk_measure"
    assert id_manifest["method_package_refs"][0]["path"] == str(package_path)


def test_create_risk_manager_candidate_maps_approved_rich_risk_card_thresholds(tmp_path: Path) -> None:
    rich_card = _approved_var_rich_card()
    created = create_risk_manager_candidate(
        artifact_root=tmp_path,
        template_family="var_cvar_limit",
        rich_method_card=rich_card.to_dict(),
    ).to_dict()
    manifest = created["data"]["risk_manager_candidate_manifest"]
    validated = validate_risk_manager_candidate(
        artifact_root=tmp_path,
        risk_manager_candidate_manifest=manifest,
    ).to_dict()

    assert created["ok"] is True
    assert manifest["parameters"]["max_var_fraction"] == 0.05
    assert manifest["parameters"]["max_cvar_fraction"] == 0.08
    assert manifest["parameters"]["confidence_level"] == 0.99
    assert manifest["parameters"]["lookback_period"] == 100
    assert manifest["methodology_refs"][0]["artifact_id"] == rich_card.method_card_id
    assert manifest["methodology_refs"][0]["metadata"]["family"] == "risk_models"
    assert validated["ok"] is True
    assert validated["data"]["risk_manager_candidate_validation_report"]["status"] == "passed"


def test_risk_rich_card_mapping_fails_closed_without_numeric_thresholds(tmp_path: Path) -> None:
    bad_card = _approved_var_rich_card(limit_thresholds="tight VaR and CVaR limits")
    payload = create_risk_manager_candidate(
        artifact_root=tmp_path,
        template_family="var_cvar_limit",
        rich_method_card=bad_card.to_dict(),
    ).to_dict()

    assert payload["ok"] is False
    blockers = "\n".join(payload["data"]["blockers"])
    assert "limit_thresholds must provide numeric max_var_fraction and max_cvar_fraction" in blockers


def _approved_var_rich_card(*, limit_thresholds: object | None = None) -> RichMethodCard:
    ref = EvidenceReference(
        source_id="knowledge_source_risk",
        chunk_id="knowledge_chunk_risk_1",
        locator={"heading": "VaR Limits", "page": 4},
        claim="source supports VaR and CVaR limit methodology",
    )
    field = _risk_evidenced_field(ref)
    thresholds = (
        {"max_var_fraction": 0.05, "max_cvar_fraction": 0.08}
        if limit_thresholds is None
        else limit_thresholds
    )
    return RichMethodCard(
        method_card_id="method_card_var_cvar_limit_v1",
        method_id="var_cvar_limit",
        title="VaR/CVaR Limit",
        family="risk_models",
        status="approved",
        assumptions=("portfolio tail risk estimates are monitored against explicit thresholds",),
        inputs=("portfolio returns",),
        outputs=("VaR and CVaR breach decisions",),
        failure_modes=("tail estimate instability",),
        evidence_refs=(ref,),
        extension_fields={
            "risk_models": {
                "risk_measure": field("VaR and CVaR"),
                "limit_thresholds": field(thresholds),
                "confidence_level": field(0.99),
                "lookback_window": field(100),
            }
        },
        source_methodology_candidate_id="methodology_candidate_var",
        validation_refs=({"artifact_type": "methodology_candidate_validation_report", "status": "passed"},),
        lineage={
            "readiness_summary": {
                "family": "risk_models",
                "evidence_packet_id": "methodology_evidence_packet_var",
                "risk_manager": {"status": "passed", "required_roles": [], "missing_roles": []},
            }
        },
    )


def _risk_evidenced_field(ref: EvidenceReference):
    def _factory(value: object) -> EvidenceBackedField:
        return EvidenceBackedField(value=value, evidence_refs=(ref,))

    return _factory


def _indicator_package(package_id: str) -> dict[str, Any]:
    return MethodPackageManifest(
        package_id=package_id,
        method_id=f"method_{package_id}",
        runtime_contract=INDICATOR_RUNTIME_CONTRACT,
        implementation_id=f"implementation_{package_id}",
        entrypoint=f"trader_standard.indicators:{package_id}",
        class_name="DemoIndicator",
        source_path=f"src/trader_standard/indicators/{package_id}.py",
        source_hash=f"hash_{package_id}",
        source_provenance={"kind": "validated_fixture"},
        constructor_kwargs={},
        method_contract={"method_id": f"method_{package_id}"},
        method_card_ids=("method_card_risk_measure",),
        validation_report_ref={
            "artifact_type": "indicator_validation_report",
            "validation_id": f"validation_{package_id}",
            "status": "passed",
            "path": f"artifacts/research/validations/{package_id}.json",
        },
        validation_summary={"status": "passed", "fixture_count": 1},
        safety_profile={"imports": "static_allowlist"},
        dependency_allowlist=("trader", "trader_standard"),
    ).to_dict()


@pytest.mark.parametrize(
    ("request_payload", "expected"),
    [
        (
            {
                "template_family": "gross_exposure_cap",
                "parameters": {"max_gross_exposure": [100_000.0, 200_000.0]},
            },
            "parameter grid",
        ),
        (
            {"template_family": "gross_exposure_cap", "parameters": {"max_gross_exposure": 0.0}},
            "max_gross_exposure must be > 0.0",
        ),
        (
            {
                "template_family": "gross_exposure_cap",
                "parameters": {"max_gross_exposure": 100_000.0, "symbols": ["BTC/USD"]},
            },
            "unknown risk-manager template parameter: symbols",
        ),
        (
            {
                "template_family": "var_cvar_limit",
                "parameters": {"max_var_fraction": 0.10, "max_cvar_fraction": 0.08},
            },
            "max_cvar_fraction must be at least max_var_fraction",
        ),
        (
            {
                "template_family": "gross_exposure_cap",
                "parameters": {"max_gross_exposure": 100_000.0},
                "execution_assumptions": {"live_trading_allowed": True},
            },
            "execution_assumptions.live_trading_allowed must remain false",
        ),
        (
            {
                "template_family": "drawdown_guard",
                "parameters": {"max_drawdown_fraction": 0.10},
                "method_package_refs": [{"role": "unknown", "package_manifest": _indicator_package("method_pkg")}],
            },
            "unknown method package role",
        ),
        (
            {
                "template_family": "drawdown_guard",
                "parameters": {"max_drawdown_fraction": 0.10},
                "method_package_refs": [
                    {"role": "risk_measure", "package_manifest": {"artifact_type": "method_implementation_manifest"}}
                ],
            },
            "raw method_implementation_manifest inputs are not accepted",
        ),
    ],
)
def test_create_risk_manager_candidate_rejects_invalid_inputs(
    tmp_path: Path,
    request_payload: dict[str, Any],
    expected: str,
) -> None:
    payload = create_risk_manager_candidate(artifact_root=tmp_path, **request_payload).to_dict()

    assert payload["ok"] is False
    assert payload["errors"][0]["code"] == "invalid_risk_manager_candidate"
    assert expected in "\n".join(payload["data"]["blockers"])


def test_create_risk_manager_candidate_rejects_unsupported_template(tmp_path: Path) -> None:
    payload = create_risk_manager_candidate(
        artifact_root=tmp_path,
        template_family="unsupported",
        parameters={"max_gross_exposure": 100_000.0},
    ).to_dict()

    assert payload["ok"] is False
    assert payload["errors"][0]["code"] == "unsupported_risk_manager_template"
    assert payload["data"]["supported_risk_manager_families"] == list(SUPPORTED_RISK_MANAGER_FAMILIES)


def _load_module(source_path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location("_risk_manager_candidate_test", source_path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"Could not load generated source: {source_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
