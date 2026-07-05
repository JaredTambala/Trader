from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

import pytest

from trader_research.contracts import SideEffect, write_json_artifact
from trader_research.domain import (
    STRATEGY_CANDIDATE,
    STRATEGY_IMPLEMENTATION,
    ResearchIssue,
    StrategyCandidateArtifactLink,
    StrategyCandidateManifest,
    StrategyCandidateRiskAssumption,
    StrategyCandidateSizing,
    StrategyCandidateSourceRef,
)
from trader_research.method_implementations.manifest import INDICATOR_RUNTIME_CONTRACT, SIGNAL_RUNTIME_CONTRACT
from trader_research.method_packages import MethodPackageManifest, method_package_path
import trader_research.suites as suites
from trader_research.strategies import (
    METHOD_PACKAGE_MANIFEST,
    RESEARCH_CREATE_STRATEGY_CANDIDATE,
    SUPPORTED_STRATEGY_FAMILIES,
    create_strategy_candidate,
    list_strategy_templates,
    strategy_candidate_path,
)


def _signal_package(
    package_id: str,
    *,
    runtime_contract: str = SIGNAL_RUNTIME_CONTRACT,
    status: str = "validated",
    blockers: tuple[str, ...] = (),
    method_card_ids: tuple[str, ...] = ("method_card_bollinger_band",),
) -> dict[str, Any]:
    return MethodPackageManifest(
        package_id=package_id,
        method_id=f"method_{package_id}",
        runtime_contract=runtime_contract,
        implementation_id=f"implementation_{package_id}",
        entrypoint=f"trader_standard.signals:{package_id}",
        class_name="DemoSignal",
        source_path=f"src/trader_standard/signals/{package_id}.py",
        source_hash=f"hash_{package_id}",
        source_provenance={"kind": "validated_fixture"},
        constructor_kwargs={},
        method_contract={"method_id": f"method_{package_id}"},
        method_card_ids=method_card_ids,
        validation_report_ref={
            "artifact_type": "signal_implementation_validation_report",
            "validation_id": f"validation_{package_id}",
            "status": "passed",
            "path": f"artifacts/research/validations/{package_id}.json",
        },
        validation_summary={"status": "passed", "fixture_count": 1},
        safety_profile={"imports": "static_allowlist"},
        dependency_allowlist=("trader", "trader_standard"),
        blockers=blockers,
        status=status,
    ).to_dict()


def test_strategy_template_catalog_returns_maintained_families() -> None:
    envelope = list_strategy_templates()
    payload = envelope.to_dict()

    assert payload["ok"] is True
    assert payload["command"] == "research_list_strategy_templates"
    assert payload["agent_owner"] == "Quant Research Supervisor Agent"
    assert payload["side_effect"] == SideEffect.READ_ONLY.value
    assert payload["data"]["template_count"] == 3
    templates = payload["data"]["templates"]

    assert [template["template_family"] for template in templates] == list(SUPPORTED_STRATEGY_FAMILIES)
    assert payload["data"]["supported_strategy_families"] == list(SUPPORTED_STRATEGY_FAMILIES)

    trend = templates[0]
    assert trend["template_family"] == "trend_following"
    assert trend["runtime_builder_path"] == "trader_standard.strategies:build_trend_following_strategy"
    assert trend["runtime_strategy_id"] == "trend_following"
    assert trend["required_artifact_types"] == [METHOD_PACKAGE_MANIFEST]
    assert trend["entry_semantics"]["condition"] == "any_positive"
    assert trend["exit_semantics"]["condition"] == "any_negative"
    assert trend["sizing"]["model"] == "fixed_quantity"
    assert trend["risk_assumptions"]["stop_policy"] == "not_exposed_in_v1_catalog"
    assert trend["backtest_context_requirements"]["market_data"] == "event_store_bars"
    assert trend["backtest_context_requirements"]["required_backtest_fields"] == [
        "symbols",
        "asset_class",
        "timeframe",
        "start",
        "end",
    ]
    assert trend["constraints"]["arbitrary_strategy_code_allowed"] is False

    parameter_by_name = {parameter["name"]: parameter for parameter in trend["parameters"]}
    assert "symbols" not in parameter_by_name
    assert "asset_class" not in parameter_by_name
    assert "timeframe" not in parameter_by_name
    assert parameter_by_name["ema_fast_period"]["default"] == 12
    assert parameter_by_name["ema_slow_period"]["constraints"]["must_exceed"] == "ema_fast_period"


def test_strategy_template_filter_normalizes_and_fails_closed() -> None:
    envelope = list_strategy_templates(families=("mean-reversion", "mean_reversion"))
    payload = envelope.to_dict()

    assert payload["ok"] is True
    assert payload["data"]["template_count"] == 1
    assert payload["data"]["templates"][0]["template_family"] == "mean_reversion"
    assert payload["data"]["templates"][0]["entry_semantics"]["condition"] == "all_positive"

    bad_payload = list_strategy_templates(families=("noop",)).to_dict()
    assert bad_payload["ok"] is False
    assert bad_payload["errors"] == [
        {
            "code": "unsupported_strategy_template",
            "message": "Unsupported strategy family: noop",
        }
    ]
    assert bad_payload["data"]["supported_strategy_families"] == list(SUPPORTED_STRATEGY_FAMILIES)


def test_suite_expansion_uses_strategy_catalog_family_source() -> None:
    assert suites.SUPPORTED_STRATEGY_FAMILIES is SUPPORTED_STRATEGY_FAMILIES


def test_create_bollinger_strategy_candidate_from_inline_signal_package(tmp_path) -> None:
    envelope = create_strategy_candidate(
        artifact_root=tmp_path,
        template_family="bollinger_band",
        method_package_refs=[
            {"role": "bollinger_band_signal", "package_manifest": _signal_package("method_package_bollinger")}
        ],
        parameters={"period": 20, "stddev_multiplier": 2.0},
        sizing={"target_qty_when_long": 2.0, "max_position_qty": 5.0},
        risk_assumptions={"review_note": "bounded v1 candidate"},
        execution_assumptions={"runtime_instantiation": "deferred_to_task_27"},
    )
    payload = envelope.to_dict()

    assert payload["ok"] is True
    assert payload["command"] == RESEARCH_CREATE_STRATEGY_CANDIDATE
    assert payload["agent_owner"] == "Quant Research Supervisor Agent"
    assert payload["side_effect"] == SideEffect.LOCAL_MUTATING.value

    manifest = payload["data"]["strategy_candidate_manifest"]
    persisted_path = strategy_candidate_path(tmp_path, manifest["candidate_id"])
    assert persisted_path.exists()
    assert json.loads(persisted_path.read_text(encoding="utf-8")) == manifest
    assert payload["artifacts"]["strategy_candidate"]["artifact_type"] == STRATEGY_CANDIDATE
    assert payload["artifacts"]["strategy_candidate"]["path"] == str(persisted_path)
    assert payload["artifacts"]["strategy_source"]["artifact_type"] == STRATEGY_IMPLEMENTATION

    assert manifest["artifact_type"] == STRATEGY_CANDIDATE
    assert manifest["template_family"] == "bollinger_band"
    assert "symbols" not in manifest["parameters"]
    assert "asset_class" not in manifest["parameters"]
    assert "timeframe" not in manifest["parameters"]
    assert manifest["parameters"]["target_qty_when_long"] == 2.0
    assert manifest["method_package_refs"][0]["artifact_type"] == METHOD_PACKAGE_MANIFEST
    assert manifest["method_package_refs"][0]["role"] == "bollinger_band_signal"
    assert manifest["signal_refs"][0]["artifact_type"] == "signal_implementation_validation_report"
    assert manifest["signal_refs"][0]["role"] == "bollinger_band_signal"
    assert manifest["entry_semantics"]["condition"] == "all_positive"
    assert manifest["exit_semantics"]["condition"] == "all_negative"
    assert manifest["sizing"]["target_qty_when_long"] == 2.0
    assert manifest["sizing"]["max_position_qty"] == 5.0
    assert "data_requirements" not in manifest
    source_ref = manifest["strategy_source"]
    source_path = Path(source_ref["path"])
    assert source_ref["artifact_type"] == STRATEGY_IMPLEMENTATION
    assert source_ref["runtime_contract"] == "trader.strategies.Strategy"
    assert source_ref["class_name"] == "BollingerBandResearchStrategy"
    assert source_ref["factory_name"] == "build_strategy"
    assert source_ref["metadata"]["runtime_builder_path"] == "trader_standard.strategies:build_bollinger_band_strategy"
    assert source_path.exists()
    assert payload["artifacts"]["strategy_source"]["path"] == str(source_path)
    assert payload["artifacts"]["strategy_source"]["metadata"]["class_name"] == "BollingerBandResearchStrategy"
    assert payload["artifacts"]["strategy_source"]["metadata"]["sha256"] == source_ref["source_hash"]
    source_text = source_path.read_text(encoding="utf-8")
    assert "class BollingerBandResearchStrategy(Strategy):" in source_text
    assert f'CANDIDATE_ID = "{manifest["candidate_id"]}"' in source_text
    compile(source_text, str(source_path), "exec")
    assert manifest["execution_assumptions"]["runtime_instantiation"] == "deferred_to_task_27"
    assert manifest["execution_assumptions"]["live_trading_allowed"] is False
    assert {item["name"] for item in manifest["risk_assumptions"]} >= {"order_type", "review_note"}
    assert manifest["warnings"] == []
    assert manifest["blockers"] == []


def test_create_strategy_candidate_resolves_package_ids_and_paths(tmp_path) -> None:
    package = _signal_package("method_package_bollinger")
    persisted_path = write_json_artifact(package, method_package_path(tmp_path, package["package_id"]))
    from_id = create_strategy_candidate(
        artifact_root=tmp_path,
        template_family="bollinger_band",
        method_package_refs=[{"role": "bollinger_band_signal", "package_id": package["package_id"]}],
    ).to_dict()
    from_path = create_strategy_candidate(
        artifact_root=tmp_path,
        template_family="bollinger_band",
        method_package_refs=[{"role": "bollinger_band_signal", "path": str(persisted_path)}],
    ).to_dict()

    assert from_id["ok"] is True
    assert from_path["ok"] is True
    assert (
        from_id["data"]["strategy_candidate_manifest"]["candidate_id"]
        == from_path["data"]["strategy_candidate_manifest"]["candidate_id"]
    )
    assert from_id["data"]["strategy_candidate_manifest"]["method_package_refs"][0]["path"] == str(persisted_path)


def test_create_strategy_candidate_ids_are_deterministic_for_role_order(tmp_path) -> None:
    packages = {
        "rsi_threshold_signal": _signal_package("method_package_rsi_threshold"),
        "rsi_recovery_signal": _signal_package("method_package_rsi_recovery"),
        "sma_stretch_signal": _signal_package("method_package_sma_stretch"),
    }
    first = create_strategy_candidate(
        artifact_root=tmp_path,
        template_family="mean_reversion",
        method_package_refs=[
            {"role": "sma_stretch_signal", "package_manifest": packages["sma_stretch_signal"]},
            {"role": "rsi_threshold_signal", "package_manifest": packages["rsi_threshold_signal"]},
            {"role": "rsi_recovery_signal", "package_manifest": packages["rsi_recovery_signal"]},
        ],
    ).to_dict()
    second = create_strategy_candidate(
        artifact_root=tmp_path,
        template_family="mean_reversion",
        method_package_refs=[
            {"role": "rsi_recovery_signal", "package_manifest": packages["rsi_recovery_signal"]},
            {"role": "sma_stretch_signal", "package_manifest": packages["sma_stretch_signal"]},
            {"role": "rsi_threshold_signal", "package_manifest": packages["rsi_threshold_signal"]},
        ],
    ).to_dict()

    assert first["ok"] is True
    assert second["ok"] is True
    assert (
        first["data"]["strategy_candidate_manifest"]["candidate_id"]
        == second["data"]["strategy_candidate_manifest"]["candidate_id"]
    )
    assert [ref["role"] for ref in first["data"]["strategy_candidate_manifest"]["method_package_refs"]] == [
        "rsi_threshold_signal",
        "rsi_recovery_signal",
        "sma_stretch_signal",
    ]


def test_create_strategy_candidate_rejects_unsupported_template(tmp_path) -> None:
    payload = create_strategy_candidate(
        artifact_root=tmp_path,
        template_family="noop",
        method_package_refs=[],
    ).to_dict()

    assert payload["ok"] is False
    assert payload["errors"] == [
        {
            "code": "unsupported_strategy_template",
            "message": "Unsupported strategy family: noop",
        }
    ]


@pytest.mark.parametrize(
    ("method_package_refs", "expected_blocker"),
    [
        ([], "method_package_refs are required"),
        (
            [{"role": "unknown_signal", "package_manifest": _signal_package("method_package_unknown")}],
            "unknown method package role",
        ),
        (
            [
                {"role": "bollinger_band_signal", "package_manifest": _signal_package("method_package_a")},
                {"role": "bollinger_band_signal", "package_manifest": _signal_package("method_package_b")},
            ],
            "duplicate method package role",
        ),
        (
            [{"role": "bollinger_band_signal", "package_manifest": _signal_package("method_package_draft", status="draft")}],
            "status=validated",
        ),
        (
            [
                {
                    "role": "bollinger_band_signal",
                    "package_manifest": _signal_package(
                        "method_package_blocked",
                        blockers=("fixture failed",),
                    ),
                }
            ],
            "blockers must be empty",
        ),
        (
            [
                {
                    "role": "bollinger_band_signal",
                    "package_manifest": _signal_package("method_package_no_cards", method_card_ids=()),
                }
            ],
            "method-card refs",
        ),
        (
            [
                {
                    "role": "bollinger_band_signal",
                    "package_manifest": _signal_package(
                        "method_package_indicator",
                        runtime_contract=INDICATOR_RUNTIME_CONTRACT,
                    ),
                }
            ],
            "runtime_contract must be trader.signals.Signal",
        ),
        (
            [
                {
                    "role": "bollinger_band_signal",
                    "package_manifest": {"artifact_type": "method_implementation_manifest"},
                }
            ],
            "raw method_implementation_manifest inputs are not accepted",
        ),
    ],
)
def test_create_strategy_candidate_rejects_invalid_method_package_refs(
    tmp_path,
    method_package_refs: list[Mapping[str, Any]],
    expected_blocker: str,
) -> None:
    payload = create_strategy_candidate(
        artifact_root=tmp_path,
        template_family="bollinger_band",
        method_package_refs=method_package_refs,
    ).to_dict()

    assert payload["ok"] is False
    assert any(expected_blocker in blocker for blocker in payload["data"]["blockers"])


@pytest.mark.parametrize(
    ("kwargs", "expected_blocker"),
    [
        ({"parameters": {"period": [10, 20]}}, "period must be a single scalar value"),
        ({"parameters": {"not_a_parameter": 1}}, "unknown strategy template parameter"),
        ({"parameters": {"period": 0}}, "period must be >= 1"),
        ({"parameters": {"stddev_multiplier": -1.0}}, "stddev_multiplier must be >= 0.0"),
        (
            {"parameters": {"target_qty_when_long": 1.0}, "sizing": {"target_qty_when_long": 2.0}},
            "target_qty_when_long cannot conflict",
        ),
        ({"sizing": {"target_qty_when_long": -1.0}}, "target_qty_when_long must be non-negative"),
        ({"sizing": {"model": "risk_parity"}}, "sizing.model=fixed_quantity"),
        ({"parameters": {"symbols": ["SPY"]}}, "unknown strategy template parameter: symbols"),
        (
            {"execution_assumptions": {"live_trading_allowed": True}},
            "execution_assumptions.live_trading_allowed must remain false",
        ),
    ],
)
def test_create_strategy_candidate_rejects_invalid_bounds_and_assumptions(
    tmp_path,
    kwargs: Mapping[str, Any],
    expected_blocker: str,
) -> None:
    request: dict[str, Any] = {
        "artifact_root": tmp_path,
        "template_family": "bollinger_band",
        "method_package_refs": [
            {"role": "bollinger_band_signal", "package_manifest": _signal_package("method_package_bollinger")}
        ],
    }
    request.update(kwargs)

    payload = create_strategy_candidate(**request).to_dict()

    assert payload["ok"] is False
    assert any(expected_blocker in blocker for blocker in payload["data"]["blockers"])


def test_strategy_candidate_manifest_round_trips_json_payload() -> None:
    manifest = StrategyCandidateManifest(
        candidate_id="strategy_candidate_demo",
        template_family="trend_following",
        method_package_refs=(
            StrategyCandidateArtifactLink(
                artifact_id="method_package_ema",
                artifact_type=METHOD_PACKAGE_MANIFEST,
                role="ema_crossover_signal",
                path="artifacts/research/method_package_ema.json",
                agent_owner="Quantitative Methods Agent",
                status="validated",
                metadata={"runtime_contract": "trader.signals.Signal"},
            ),
        ),
        signal_refs=(
            StrategyCandidateArtifactLink(
                artifact_id="signal_validation_ema",
                artifact_type="signal_implementation_validation_report",
                role="ema_crossover_signal",
                status="validated",
            ),
        ),
        parameters={"ema_fast_period": 12, "ema_slow_period": 26, "target_qty_when_long": 2.0},
        entry_semantics={"condition": "any_positive"},
        exit_semantics={"condition": "any_negative"},
        sizing=StrategyCandidateSizing(
            target_qty_when_long=2.0,
            max_position_qty=5.0,
            metadata={"unit": "shares"},
        ),
        risk_assumptions=(
            StrategyCandidateRiskAssumption(
                name="order_type",
                value="market",
                description="Maintained v1 templates use market orders.",
            ),
        ),
        execution_assumptions={
            "broker_mutation_allowed": False,
            "live_trading_allowed": False,
            "runtime_instantiation": "deferred_to_validation",
        },
        strategy_source=StrategyCandidateSourceRef(
            artifact_id="strategy_candidate_demo",
            path="artifacts/research/strategy_candidates/source/strategy_candidate_demo.py",
            source_hash="strategy_source_hash",
            class_name="TrendFollowingResearchStrategy",
        ),
        warnings=(ResearchIssue(code="observational_only", message="Package validation is deferred."),),
        blockers=(ResearchIssue(code="missing_method_package", message="MACD package is not attached."),),
    )

    payload = manifest.to_dict()

    assert payload["artifact_type"] == STRATEGY_CANDIDATE
    assert payload["template_family"] == "trend_following"
    assert payload["method_package_refs"][0]["status"] == "validated"
    assert payload["signal_refs"][0]["artifact_type"] == "signal_implementation_validation_report"
    assert payload["strategy_source"]["runtime_contract"] == "trader.strategies.Strategy"
    assert payload["sizing"]["max_position_qty"] == 5.0
    assert payload["risk_assumptions"][0]["name"] == "order_type"
    assert payload["execution_assumptions"]["live_trading_allowed"] is False
    assert payload["warnings"][0]["code"] == "observational_only"
    assert payload["blockers"][0]["code"] == "missing_method_package"
    json.dumps(payload)

    assert StrategyCandidateManifest.from_dict(payload).to_dict() == payload
