from __future__ import annotations

import json

from trader_research.contracts import SideEffect
from trader_research.domain import (
    STRATEGY_CANDIDATE,
    DataRequirement,
    ResearchIssue,
    StrategyCandidateArtifactLink,
    StrategyCandidateManifest,
    StrategyCandidateRiskAssumption,
    StrategyCandidateSizing,
)
import trader_research.suites as suites
from trader_research.strategies import (
    METHOD_PACKAGE_MANIFEST,
    SUPPORTED_STRATEGY_FAMILIES,
    list_strategy_templates,
)


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
    assert trend["data_requirements"]["market_data"] == "event_store_bars"
    assert trend["constraints"]["arbitrary_strategy_code_allowed"] is False

    parameter_by_name = {parameter["name"]: parameter for parameter in trend["parameters"]}
    assert parameter_by_name["symbols"]["required"] is True
    assert parameter_by_name["symbols"]["constraints"] == {"min_items": 1, "max_items": 20}
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
        data_requirements=(
            DataRequirement(
                symbols=("DEMO",),
                asset_class="stocks",
                timeframe="1Min",
                start="2026-01-01T00:00:00Z",
                end="2026-01-02T00:00:00Z",
            ),
        ),
        warnings=(ResearchIssue(code="observational_only", message="Package validation is deferred."),),
        blockers=(ResearchIssue(code="missing_method_package", message="MACD package is not attached."),),
    )

    payload = manifest.to_dict()

    assert payload["artifact_type"] == STRATEGY_CANDIDATE
    assert payload["template_family"] == "trend_following"
    assert payload["method_package_refs"][0]["status"] == "validated"
    assert payload["signal_refs"][0]["artifact_type"] == "signal_implementation_validation_report"
    assert payload["sizing"]["max_position_qty"] == 5.0
    assert payload["risk_assumptions"][0]["name"] == "order_type"
    assert payload["warnings"][0]["code"] == "observational_only"
    assert payload["blockers"][0]["code"] == "missing_method_package"
    json.dumps(payload)

    assert StrategyCandidateManifest.from_dict(payload).to_dict() == payload

