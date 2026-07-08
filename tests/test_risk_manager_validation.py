from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from trader_research.contracts import SideEffect
from trader_research.domain import RISK_MANAGER_CANDIDATE_VALIDATION_REPORT
from trader_research.method_implementations.io import file_sha256
from trader_research.risk_managers import (
    RESEARCH_VALIDATE_RISK_MANAGER_CANDIDATE,
    create_risk_manager_candidate,
    risk_manager_candidate_validation_report_path,
    validate_risk_manager_candidate,
)


def test_valid_risk_manager_candidate_validates_and_writes_report(tmp_path: Path) -> None:
    manifest = _risk_manager_candidate_manifest(tmp_path)

    envelope = validate_risk_manager_candidate(
        artifact_root=tmp_path,
        risk_manager_candidate_manifest=manifest,
    )
    payload = envelope.to_dict()

    assert payload["ok"] is True
    assert payload["command"] == RESEARCH_VALIDATE_RISK_MANAGER_CANDIDATE
    assert payload["agent_owner"] == "Quant Research Supervisor Agent"
    assert payload["side_effect"] == SideEffect.LOCAL_MUTATING.value
    report = payload["data"]["risk_manager_candidate_validation_report"]
    report_path = risk_manager_candidate_validation_report_path(tmp_path, report["validation_id"])
    assert report_path.exists()
    assert json.loads(report_path.read_text(encoding="utf-8")) == report
    assert payload["artifacts"]["risk_manager_candidate_validation_report"]["artifact_type"] == (
        RISK_MANAGER_CANDIDATE_VALIDATION_REPORT
    )
    assert report["status"] == "passed"
    assert report["candidate_id"] == manifest["candidate_id"]
    assert report["template_family"] == "gross_exposure_cap"
    assert report["runtime_contract"] == "trader.risk.RiskManager"
    assert report["fixture_summary"]["status"] == "passed"
    assert report["fixture_summary"]["symbols"] == ["SYNTH_A", "SYNTH_B", "SYNTH_C"]
    assert report["fixture_summary"]["orders_evaluated"] == 3
    assert report["telemetry_required"] == ["gross_exposure"]
    assert {check["name"] for check in report["checks"]} >= {
        "manifest_integrity",
        "execution_assumptions",
        "risk_manager_source",
        "risk_manager_source_instantiation",
        "fixture_smoke",
    }
    assert report["blockers"] == []


def test_risk_manager_candidate_validation_resolves_id_path_and_inline_manifest(tmp_path: Path) -> None:
    manifest = _risk_manager_candidate_manifest(tmp_path)

    inline = validate_risk_manager_candidate(
        artifact_root=tmp_path,
        risk_manager_candidate_manifest=manifest,
    ).to_dict()
    by_id = validate_risk_manager_candidate(
        artifact_root=tmp_path,
        candidate_id=manifest["candidate_id"],
    ).to_dict()
    by_path = validate_risk_manager_candidate(
        artifact_root=tmp_path,
        path=Path(tmp_path) / "risk_managers" / "manifests" / f"{manifest['candidate_id']}.json",
    ).to_dict()

    assert inline["ok"] is True
    assert by_id["ok"] is True
    assert by_path["ok"] is True
    assert (
        inline["data"]["risk_manager_candidate_validation_report"]["validation_id"]
        == by_id["data"]["risk_manager_candidate_validation_report"]["validation_id"]
        == by_path["data"]["risk_manager_candidate_validation_report"]["validation_id"]
    )


def test_risk_manager_candidate_validation_fails_closed_for_tampered_source(tmp_path: Path) -> None:
    manifest = _risk_manager_candidate_manifest(tmp_path)
    source_path = Path(manifest["risk_manager_source"]["path"])
    source_path.write_text(
        source_path.read_text(encoding="utf-8").replace("return list(orders), []", "return [], list(orders)"),
        encoding="utf-8",
    )
    manifest = {
        **manifest,
        "risk_manager_source": {
            **manifest["risk_manager_source"],
            "source_hash": "tampered_hash",
            "metadata": {
                **manifest["risk_manager_source"]["metadata"],
                "current_hash": file_sha256(source_path),
            },
        },
    }

    payload = validate_risk_manager_candidate(
        artifact_root=tmp_path,
        risk_manager_candidate_manifest=manifest,
    ).to_dict()

    assert payload["ok"] is False
    report = payload["data"]["risk_manager_candidate_validation_report"]
    assert report["status"] == "failed"
    assert any("risk_manager_source source_hash does not match current source file" in item for item in report["blockers"])


def _risk_manager_candidate_manifest(tmp_path: Path) -> dict[str, Any]:
    result = create_risk_manager_candidate(
        artifact_root=tmp_path,
        template_family="gross_exposure_cap",
        parameters={"max_gross_exposure": 100_000.0},
    ).to_dict()
    assert result["ok"] is True
    return result["data"]["risk_manager_candidate_manifest"]
