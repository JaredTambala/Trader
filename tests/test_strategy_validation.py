from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

import pytest

from trader_research.contracts import SideEffect
from trader_research.domain import STRATEGY_CANDIDATE_VALIDATION_REPORT
from trader_research.method_implementations.io import file_sha256
from trader_research.method_implementations.manifest import SIGNAL_RUNTIME_CONTRACT
from trader_research.method_packages import MethodPackageManifest
from trader_research.strategies import create_strategy_candidate, strategy_candidate_path
from trader_research.strategy_validation import (
    RESEARCH_VALIDATE_STRATEGY_CANDIDATE,
    strategy_candidate_validation_report_path,
    validate_strategy_candidate,
)


def test_valid_strategy_candidate_validates_and_writes_report(tmp_path: Path) -> None:
    manifest = _strategy_candidate_manifest(tmp_path)

    envelope = validate_strategy_candidate(
        artifact_root=tmp_path,
        strategy_candidate_manifest=manifest,
    )
    payload = envelope.to_dict()

    assert payload["ok"] is True
    assert payload["command"] == RESEARCH_VALIDATE_STRATEGY_CANDIDATE
    assert payload["agent_owner"] == "Quant Research Supervisor Agent"
    assert payload["side_effect"] == SideEffect.LOCAL_MUTATING.value
    report = payload["data"]["strategy_candidate_validation_report"]
    report_path = strategy_candidate_validation_report_path(tmp_path, report["validation_id"])
    assert report_path.exists()
    assert json.loads(report_path.read_text(encoding="utf-8")) == report
    assert payload["artifacts"]["strategy_candidate_validation_report"]["artifact_type"] == (
        STRATEGY_CANDIDATE_VALIDATION_REPORT
    )
    assert report["status"] == "passed"
    assert report["candidate_id"] == manifest["candidate_id"]
    assert report["template_family"] == "bollinger_band"
    assert report["runtime_builder_path"] == "trader_standard.strategies:build_bollinger_band_strategy"
    assert report["runtime_strategy_id"] == "bollinger_band"
    assert report["strategy_info"]["strategy_id"] == manifest["candidate_id"]
    assert report["fixture_summary"]["status"] == "passed"
    assert report["fixture_summary"]["fixture_context"] == {
        "asset_class": "stocks",
        "symbols": ["SYNTH"],
        "timeframe": "1Min",
    }
    assert report["fixture_summary"]["bar_count_per_symbol"] == 160
    assert {check["name"] for check in report["checks"]} >= {
        "manifest_integrity",
        "method_package_refs",
        "parameters",
        "sizing",
        "execution_assumptions",
        "strategy_source",
        "strategy_source_instantiation",
        "fixture_smoke",
    }
    assert report["blockers"] == []


def test_strategy_candidate_validation_resolves_id_path_and_inline_manifest(tmp_path: Path) -> None:
    manifest = _strategy_candidate_manifest(tmp_path)
    persisted_path = strategy_candidate_path(tmp_path, manifest["candidate_id"])

    inline = validate_strategy_candidate(
        artifact_root=tmp_path,
        strategy_candidate_manifest=manifest,
    ).to_dict()
    by_path = validate_strategy_candidate(
        artifact_root=tmp_path,
        path=persisted_path,
    ).to_dict()
    by_id = validate_strategy_candidate(
        artifact_root=tmp_path,
        candidate_id=manifest["candidate_id"],
    ).to_dict()

    assert inline["ok"] is True
    assert by_path["ok"] is True
    assert by_id["ok"] is True
    assert (
        inline["data"]["strategy_candidate_validation_report"]["validation_id"]
        == by_path["data"]["strategy_candidate_validation_report"]["validation_id"]
        == by_id["data"]["strategy_candidate_validation_report"]["validation_id"]
    )


def test_strategy_candidate_validation_ids_are_deterministic(tmp_path: Path) -> None:
    manifest = _strategy_candidate_manifest(tmp_path)

    first = validate_strategy_candidate(artifact_root=tmp_path, strategy_candidate_manifest=manifest).to_dict()
    second = validate_strategy_candidate(artifact_root=tmp_path, strategy_candidate_manifest=manifest).to_dict()

    assert first["ok"] is True
    assert second["ok"] is True
    assert (
        first["data"]["strategy_candidate_validation_report"]["validation_id"]
        == second["data"]["strategy_candidate_validation_report"]["validation_id"]
    )


@pytest.mark.parametrize(
    ("kwargs", "expected_message"),
    [
        ({}, "exactly one of candidate_id, path, or strategy_candidate_manifest is required"),
        (
            {"candidate_id": "missing_candidate"},
            "strategy candidate manifest not found",
        ),
        (
            {"path": "missing_strategy_candidate.json"},
            "strategy candidate manifest not found",
        ),
    ],
)
def test_strategy_candidate_validation_rejects_unresolved_inputs(
    tmp_path: Path,
    kwargs: Mapping[str, Any],
    expected_message: str,
) -> None:
    payload = validate_strategy_candidate(artifact_root=tmp_path, **kwargs).to_dict()

    assert payload["ok"] is False
    assert payload["errors"][0]["code"] == "strategy_candidate_resolution_failed"
    assert expected_message in payload["errors"][0]["message"]
    assert payload["artifacts"] == {}


@pytest.mark.parametrize(
    ("mutator", "expected_blocker"),
    [
        (lambda manifest: {**manifest, "template_family": "noop"}, "Unsupported strategy family"),
        (
            lambda manifest: {
                **manifest,
                "blockers": [{"code": "blocked", "message": "candidate is blocked", "details": {}}],
            },
            "candidate manifest blocker: candidate is blocked",
        ),
        (
            lambda manifest: {**manifest, "method_package_refs": []},
            "missing required method package role: bollinger_band_signal",
        ),
        (
            lambda manifest: {
                **manifest,
                "method_package_refs": [
                    *manifest["method_package_refs"],
                    {**manifest["method_package_refs"][0]},
                ],
            },
            "duplicate method package role: bollinger_band_signal",
        ),
        (
            lambda manifest: {
                **manifest,
                "method_package_refs": [{**manifest["method_package_refs"][0], "role": "unknown_signal"}],
            },
            "unknown method package role: unknown_signal",
        ),
        (
            lambda manifest: {
                **manifest,
                "method_package_refs": [
                    {
                        **manifest["method_package_refs"][0],
                        "metadata": {**manifest["method_package_refs"][0]["metadata"], "source_hash": ""},
                    }
                ],
            },
            "package ref metadata.source_hash is required",
        ),
        (
            lambda manifest: {**manifest, "sizing": {**manifest["sizing"], "model": "risk_parity"}},
            "candidate sizing.model must be fixed_quantity",
        ),
        (
            lambda manifest: {
                **manifest,
                "execution_assumptions": {**manifest["execution_assumptions"], "live_trading_allowed": True},
            },
            "candidate execution_assumptions.live_trading_allowed must remain false",
        ),
        (
            lambda manifest: {**manifest, "parameters": {**manifest["parameters"], "period": "bad"}},
            "parameters.period must be an integer",
        ),
        (
            lambda manifest: {**manifest, "strategy_source": None},
            "candidate strategy_source is required",
        ),
        (
            lambda manifest: {
                **manifest,
                "strategy_source": {**manifest["strategy_source"], "source_hash": "tampered_hash"},
            },
            "strategy_source source_hash does not match current source file",
        ),
    ],
)
def test_strategy_candidate_validation_fails_closed_and_persists_failed_report(
    tmp_path: Path,
    mutator: Any,
    expected_blocker: str,
) -> None:
    manifest = mutator(_strategy_candidate_manifest(tmp_path))

    payload = validate_strategy_candidate(
        artifact_root=tmp_path,
        strategy_candidate_manifest=manifest,
    ).to_dict()

    assert payload["ok"] is False
    report = payload["data"]["strategy_candidate_validation_report"]
    assert report["status"] == "failed"
    assert any(expected_blocker in blocker for blocker in report["blockers"])
    assert Path(payload["artifacts"]["strategy_candidate_validation_report"]["path"]).exists()


def test_strategy_candidate_validation_reports_source_instantiation_failure(tmp_path: Path) -> None:
    manifest = _strategy_candidate_manifest(tmp_path)
    source_path = Path(manifest["strategy_source"]["path"])
    source_path.write_text(
        '''"""Broken generated strategy source for validation tests."""

from __future__ import annotations

from typing import Sequence

from trader.strategies import Strategy


class BrokenStrategyCandidate:
    """Deliberately does not implement Strategy."""


def build_strategy(*, symbols: Sequence[str], asset_class: str, timeframe: str) -> Strategy:
    del symbols, asset_class, timeframe
    raise RuntimeError("strategy source unavailable")
''',
        encoding="utf-8",
    )
    manifest = {
        **manifest,
        "strategy_source": {
            **manifest["strategy_source"],
            "class_name": "BrokenStrategyCandidate",
            "source_hash": file_sha256(source_path),
        },
    }

    payload = validate_strategy_candidate(
        artifact_root=tmp_path,
        strategy_candidate_manifest=manifest,
    ).to_dict()

    assert payload["ok"] is False
    report = payload["data"]["strategy_candidate_validation_report"]
    assert report["status"] == "failed"
    assert any("strategy source instantiation failed: strategy source unavailable" in item for item in report["blockers"])


def _strategy_candidate_manifest(tmp_path: Path) -> dict[str, Any]:
    result = create_strategy_candidate(
        artifact_root=tmp_path,
        template_family="bollinger_band",
        method_package_refs=[
            {"role": "bollinger_band_signal", "package_manifest": _signal_package("method_package_bollinger")}
        ],
        parameters={"period": 20, "stddev_multiplier": 2.0},
        sizing={"target_qty_when_long": 1.0, "max_position_qty": 5.0},
    ).to_dict()
    assert result["ok"] is True
    return result["data"]["strategy_candidate_manifest"]


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
