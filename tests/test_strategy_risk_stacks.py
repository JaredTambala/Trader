from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from trader_research.contracts import SideEffect
from trader_research.domain import STRATEGY_RISK_STACK, STRATEGY_RISK_STACK_VALIDATION_REPORT
from trader_research.method_implementations.manifest import SIGNAL_RUNTIME_CONTRACT
from trader_research.methods.packages import MethodPackageManifest
from trader_research.portfolio_stacks import (
    RESEARCH_CREATE_STRATEGY_RISK_STACK,
    RESEARCH_VALIDATE_STRATEGY_RISK_STACK,
    create_strategy_risk_stack,
    strategy_risk_stack_manifest_path,
    strategy_risk_stack_validation_report_path,
    validate_strategy_risk_stack,
)
from trader_research.risk_managers import create_risk_manager_candidate, validate_risk_manager_candidate
from trader_research.strategy_candidates import create_strategy_candidate, validate_strategy_candidate


def test_strategy_risk_stack_create_and_validate(tmp_path: Path) -> None:
    strategy_report = _strategy_validation_report(tmp_path)
    risk_report = _risk_manager_validation_report(tmp_path)

    created = create_strategy_risk_stack(
        artifact_root=tmp_path,
        strategy_candidate_validation_report=strategy_report,
        risk_manager_validation_refs=[{"risk_manager_candidate_validation_report": risk_report}],
    ).to_dict()

    assert created["ok"] is True
    assert created["command"] == RESEARCH_CREATE_STRATEGY_RISK_STACK
    assert created["agent_owner"] == "Quant Research Supervisor Agent"
    assert created["side_effect"] == SideEffect.LOCAL_MUTATING.value
    manifest = created["data"]["strategy_risk_stack_manifest"]
    manifest_path = strategy_risk_stack_manifest_path(tmp_path, manifest["stack_id"])
    assert manifest_path.exists()
    assert json.loads(manifest_path.read_text(encoding="utf-8")) == manifest
    assert created["artifacts"]["strategy_risk_stack"]["artifact_type"] == STRATEGY_RISK_STACK
    assert manifest["strategy_candidate_ref"]["status"] == "validated"
    assert manifest["strategy_validation_report_ref"]["status"] == "passed"
    assert manifest["risk_manager_refs"][0]["role"] == "risk_manager_0"
    assert manifest["risk_manager_refs"][0]["metadata"]["priority"] == 0
    assert manifest["risk_manager_refs"][0]["metadata"]["validation_report_ref"]["status"] == "passed"

    validated = validate_strategy_risk_stack(
        artifact_root=tmp_path,
        strategy_risk_stack_manifest=manifest,
    ).to_dict()

    assert validated["ok"] is True
    assert validated["command"] == RESEARCH_VALIDATE_STRATEGY_RISK_STACK
    report = validated["data"]["strategy_risk_stack_validation_report"]
    report_path = strategy_risk_stack_validation_report_path(tmp_path, report["validation_id"])
    assert report_path.exists()
    assert json.loads(report_path.read_text(encoding="utf-8")) == report
    assert validated["artifacts"]["strategy_risk_stack_validation_report"]["artifact_type"] == (
        STRATEGY_RISK_STACK_VALIDATION_REPORT
    )
    assert report["status"] == "passed"
    assert report["stack_id"] == manifest["stack_id"]
    assert report["fixture_summary"]["status"] == "passed"
    assert report["fixture_summary"]["symbol_count"] == 3
    assert report["fixture_summary"]["risk_manager_count"] == 1
    assert report["fixture_summary"]["risk_approved_orders"] >= 1
    assert report["fixture_summary"]["risk_telemetry_requirements"][0]["telemetry_required"] == ["gross_exposure"]
    assert {check["name"] for check in report["checks"]} >= {
        "manifest_integrity",
        "risk_manager_ordering",
        "runtime_contracts",
        "fixture_smoke",
        "risk_telemetry_hooks",
    }
    assert report["blockers"] == []


def test_strategy_risk_stack_creation_rejects_failed_risk_validation_report(tmp_path: Path) -> None:
    strategy_report = _strategy_validation_report(tmp_path)
    risk_report = {**_risk_manager_validation_report(tmp_path), "status": "failed"}

    payload = create_strategy_risk_stack(
        artifact_root=tmp_path,
        strategy_candidate_validation_report=strategy_report,
        risk_manager_validation_refs=[{"risk_manager_candidate_validation_report": risk_report}],
    ).to_dict()

    assert payload["ok"] is False
    assert payload["errors"][0]["code"] == "strategy_risk_stack_creation_failed"
    assert "risk-manager validation report 0 status must be passed" in payload["errors"][0]["message"]


def test_strategy_risk_stack_validation_rejects_bad_risk_ordering(tmp_path: Path) -> None:
    strategy_report = _strategy_validation_report(tmp_path)
    risk_report = _risk_manager_validation_report(tmp_path)
    manifest = create_strategy_risk_stack(
        artifact_root=tmp_path,
        strategy_candidate_validation_report=strategy_report,
        risk_manager_validation_refs=[{"risk_manager_candidate_validation_report": risk_report}],
    ).to_dict()["data"]["strategy_risk_stack_manifest"]
    manifest = {
        **manifest,
        "risk_manager_refs": [{**manifest["risk_manager_refs"][0], "role": "risk_manager_3"}],
    }

    payload = validate_strategy_risk_stack(
        artifact_root=tmp_path,
        strategy_risk_stack_manifest=manifest,
    ).to_dict()

    assert payload["ok"] is False
    report = payload["data"]["strategy_risk_stack_validation_report"]
    assert report["status"] == "failed"
    assert any("risk manager ref at index 0 must have role=risk_manager_0" in item for item in report["blockers"])


def _strategy_validation_report(tmp_path: Path) -> dict[str, Any]:
    candidate = create_strategy_candidate(
        artifact_root=tmp_path,
        template_family="bollinger_band",
        method_package_refs=[
            {"role": "bollinger_band_signal", "package_manifest": _signal_package("method_package_bollinger")}
        ],
        parameters={"period": 20, "stddev_multiplier": 2.0},
        sizing={"target_qty_when_long": 1.0, "max_position_qty": 5.0},
    ).to_dict()
    assert candidate["ok"] is True
    validation = validate_strategy_candidate(
        artifact_root=tmp_path,
        strategy_candidate_manifest=candidate["data"]["strategy_candidate_manifest"],
    ).to_dict()
    assert validation["ok"] is True
    return validation["data"]["strategy_candidate_validation_report"]


def _risk_manager_validation_report(tmp_path: Path) -> dict[str, Any]:
    candidate = create_risk_manager_candidate(
        artifact_root=tmp_path,
        template_family="gross_exposure_cap",
        parameters={"max_gross_exposure": 100_000.0},
    ).to_dict()
    assert candidate["ok"] is True
    validation = validate_risk_manager_candidate(
        artifact_root=tmp_path,
        risk_manager_candidate_manifest=candidate["data"]["risk_manager_candidate_manifest"],
    ).to_dict()
    assert validation["ok"] is True
    return validation["data"]["risk_manager_candidate_validation_report"]


def _signal_package(package_id: str) -> dict[str, Any]:
    return MethodPackageManifest(
        package_id=package_id,
        method_id=f"method_{package_id}",
        runtime_contract=SIGNAL_RUNTIME_CONTRACT,
        implementation_id=f"implementation_{package_id}",
        entrypoint=f"trader_standard.signals:{package_id}",
        class_name="DemoSignal",
        source_path=f"src/trader_standard/signals/{package_id}.py",
        source_hash=f"hash_{package_id}",
        source_provenance={"kind": "validated_fixture"},
        constructor_kwargs={},
        method_contract={"method_id": f"method_{package_id}"},
        method_card_ids=("method_card_bollinger_band",),
        validation_report_ref={
            "artifact_type": "signal_implementation_validation_report",
            "validation_id": f"validation_{package_id}",
            "status": "passed",
            "path": f"artifacts/research/validations/{package_id}.json",
        },
        validation_summary={"status": "passed", "fixture_count": 1},
        safety_profile={"imports": "static_allowlist"},
        dependency_allowlist=("trader", "trader_standard"),
    ).to_dict()
