from __future__ import annotations

import json

import pytest

from trader_research.contracts import SideEffect
from trader_research.domain import (
    BACKTEST_RUN_REF,
    COMPARISON_REPORT,
    DATA_QUALITY_REPORT,
    DATASET_MANIFEST,
    CITATION_VALIDATION_REPORT,
    CXX_KERNEL_MANIFEST,
    EVIDENCE_RETRIEVAL_REPORT,
    EVALUATION_REPORT,
    FEATURE_MANIFEST,
    HYPOTHESIS_CARD,
    INDICATOR_METADATA,
    METHOD_CARD,
    METHODOLOGY_CANDIDATE,
    METHODOLOGY_CANDIDATE_VALIDATION_REPORT,
    METHODOLOGY_FIELD_EXTRACTION_REPORT,
    METHOD_PACKAGE_MANIFEST,
    MODEL_CARD,
    MULTIPLE_TESTING_REPORT,
    PORTFOLIO_BACKTEST_RUN_REF,
    RISK_MANAGER_CANDIDATE,
    RISK_MANAGER_CANDIDATE_VALIDATION_REPORT,
    RISK_MANAGER_IMPLEMENTATION,
    ROBUSTNESS_REPORT,
    SIGNAL_DIAGNOSTIC_REPORT,
    STATISTICAL_TEST_REPORT,
    STRATEGY_CANDIDATE,
    STRATEGY_IMPLEMENTATION,
    STRATEGY_CANDIDATE_VALIDATION_REPORT,
    STRATEGY_RISK_STACK,
    STRATEGY_RISK_STACK_VALIDATION_REPORT,
    BoundedResearchRequest,
    DataRequirement,
    PortfolioBacktestRunRef,
    ResearchIssue,
    RiskManagerCandidateManifest,
    RiskManagerCandidateSourceRef,
    SpecialistHandoff,
    StrategyCandidateArtifactLink,
    StrategyCandidateManifest,
    StrategyRiskStackManifest,
    StrategyRiskStackValidationReport,
    artifact_report_ref,
    stable_research_id,
)


def _data_requirement() -> DataRequirement:
    return DataRequirement(
        symbols=("DEMO",),
        asset_class="stocks",
        timeframe="1Min",
        start="2026-01-20T12:00:00Z",
        end="2026-01-20T12:11:00Z",
    )


def test_research_request_and_handoff_round_trip_json() -> None:
    request = BoundedResearchRequest(
        request_id=stable_research_id("research_request", {"objective": "demo"}),
        objective="Evaluate a demo strategy.",
        data_requirement=_data_requirement(),
    )
    warning = ResearchIssue(code="data_agent_warning", message="Partial coverage.")
    handoff = SpecialistHandoff(
        handoff_id="handoff_demo",
        agent_owner="Data Agent",
        artifact_type=DATASET_MANIFEST,
        payload={
            "dataset_id": "dataset_demo",
            "symbols": ["DEMO"],
            "asset_class": "stocks",
            "timeframe": "1Min",
            "requested_window": {
                "start": "2026-01-20T12:00:00Z",
                "end": "2026-01-20T12:11:00Z",
            },
            "complete": True,
        },
        source_request=request.data_requirement.to_dict(),
        provenance_refs={"envelope_id": "env_demo"},
        warnings=(warning,),
        side_effect=SideEffect.READ_ONLY,
    )

    request_payload = request.to_dict()
    handoff_payload = handoff.to_dict()

    assert BoundedResearchRequest.from_dict(request_payload).to_dict() == request_payload
    assert SpecialistHandoff.from_dict(handoff_payload).to_dict() == handoff_payload
    assert handoff_payload["agent_owner"] == "Data Agent"
    assert handoff_payload["side_effect"] == "read_only"
    assert handoff_payload["warnings"] == [{"code": "data_agent_warning", "message": "Partial coverage.", "details": {}}]
    json.dumps({"request": request_payload, "handoff": handoff_payload})


def test_domain_validation_rejects_missing_bounds_and_bad_handoffs() -> None:
    with pytest.raises(ValueError, match="symbols are required"):
        DataRequirement(symbols=(), asset_class="stocks", timeframe="1Min", start="s", end="e")
    with pytest.raises(ValueError, match="agent_owner is required"):
        SpecialistHandoff(handoff_id="handoff", agent_owner="", artifact_type=DATASET_MANIFEST, payload={"ok": True})
    with pytest.raises(ValueError, match="unsupported artifact type"):
        SpecialistHandoff(handoff_id="handoff", agent_owner="Data Agent", artifact_type="raw_bars", payload={"ok": True})
    with pytest.raises(ValueError, match="must be owned by Data Agent"):
        SpecialistHandoff(
            handoff_id="handoff",
            agent_owner="Quant Research Supervisor Agent",
            artifact_type=DATA_QUALITY_REPORT,
            payload={"complete": True},
        )


def test_planned_artifact_reference_types_are_json_safe() -> None:
    refs = [
        artifact_report_ref(HYPOTHESIS_CARD, "hypothesis_demo"),
        artifact_report_ref(METHODOLOGY_CANDIDATE, "methodology_candidate_demo"),
        artifact_report_ref(METHODOLOGY_FIELD_EXTRACTION_REPORT, "methodology_field_extraction_demo"),
        artifact_report_ref(METHODOLOGY_CANDIDATE_VALIDATION_REPORT, "methodology_validation_demo"),
        artifact_report_ref(METHOD_CARD, "method_card_demo"),
        artifact_report_ref(METHOD_PACKAGE_MANIFEST, "method_package_demo"),
        artifact_report_ref(EVIDENCE_RETRIEVAL_REPORT, "evidence_demo"),
        artifact_report_ref(CITATION_VALIDATION_REPORT, "citation_demo"),
        artifact_report_ref(SIGNAL_DIAGNOSTIC_REPORT, "signal_diag_demo"),
        artifact_report_ref(MULTIPLE_TESTING_REPORT, "multi_demo"),
        artifact_report_ref(CXX_KERNEL_MANIFEST, "cxx_demo"),
        artifact_report_ref(INDICATOR_METADATA, "indicator_demo"),
        artifact_report_ref(STATISTICAL_TEST_REPORT, "stat_demo"),
        artifact_report_ref(FEATURE_MANIFEST, "feature_demo"),
        artifact_report_ref(MODEL_CARD, "model_demo"),
        artifact_report_ref(STRATEGY_CANDIDATE, "strategy_candidate_demo"),
        artifact_report_ref(STRATEGY_IMPLEMENTATION, "strategy_implementation_demo"),
        artifact_report_ref(STRATEGY_CANDIDATE_VALIDATION_REPORT, "strategy_candidate_validation_demo"),
        artifact_report_ref(RISK_MANAGER_CANDIDATE, "risk_manager_candidate_demo"),
        artifact_report_ref(RISK_MANAGER_IMPLEMENTATION, "risk_manager_implementation_demo"),
        artifact_report_ref(RISK_MANAGER_CANDIDATE_VALIDATION_REPORT, "risk_manager_validation_demo"),
        artifact_report_ref(STRATEGY_RISK_STACK, "strategy_risk_stack_demo"),
        artifact_report_ref(STRATEGY_RISK_STACK_VALIDATION_REPORT, "strategy_risk_stack_validation_demo"),
        artifact_report_ref(BACKTEST_RUN_REF, "backtest_run_demo"),
        artifact_report_ref(PORTFOLIO_BACKTEST_RUN_REF, "portfolio_backtest_run_demo"),
        artifact_report_ref(COMPARISON_REPORT, "comparison_demo"),
        artifact_report_ref(EVALUATION_REPORT, "eval_demo"),
        artifact_report_ref(ROBUSTNESS_REPORT, "robust_demo"),
    ]

    payload = [ref.to_dict() for ref in refs]
    owner_by_type = {item["artifact_type"]: item["agent_owner"] for item in payload}

    assert owner_by_type[HYPOTHESIS_CARD] == "Hypothesis Agent"
    for artifact_type in (
        METHODOLOGY_CANDIDATE,
        METHODOLOGY_FIELD_EXTRACTION_REPORT,
        METHODOLOGY_CANDIDATE_VALIDATION_REPORT,
        METHOD_CARD,
        METHOD_PACKAGE_MANIFEST,
        EVIDENCE_RETRIEVAL_REPORT,
        CITATION_VALIDATION_REPORT,
        SIGNAL_DIAGNOSTIC_REPORT,
        MULTIPLE_TESTING_REPORT,
        CXX_KERNEL_MANIFEST,
        INDICATOR_METADATA,
        STATISTICAL_TEST_REPORT,
    ):
        assert owner_by_type[artifact_type] == "Quantitative Methods Agent"
    assert owner_by_type[FEATURE_MANIFEST] == "ML Agent"
    assert owner_by_type[MODEL_CARD] == "ML Agent"
    for artifact_type in (
        STRATEGY_CANDIDATE,
        STRATEGY_IMPLEMENTATION,
        STRATEGY_CANDIDATE_VALIDATION_REPORT,
        RISK_MANAGER_CANDIDATE,
        RISK_MANAGER_IMPLEMENTATION,
        RISK_MANAGER_CANDIDATE_VALIDATION_REPORT,
        STRATEGY_RISK_STACK,
        STRATEGY_RISK_STACK_VALIDATION_REPORT,
        BACKTEST_RUN_REF,
        PORTFOLIO_BACKTEST_RUN_REF,
        COMPARISON_REPORT,
    ):
        assert owner_by_type[artifact_type] == "Quant Research Supervisor Agent"
    assert owner_by_type[EVALUATION_REPORT] == "Evaluation Agent"
    assert owner_by_type[ROBUSTNESS_REPORT] == "Adversarial Agent"
    json.dumps(payload)


def test_strategy_candidate_manifest_preserves_execution_assumptions() -> None:
    manifest = StrategyCandidateManifest(
        candidate_id="strategy_candidate_execution_demo",
        template_family="bollinger_band",
        execution_assumptions={
            "broker_mutation_allowed": False,
            "live_trading_allowed": False,
            "runtime_instantiation": "deferred_to_strategy_candidate_validation",
        },
    )

    payload = manifest.to_dict()

    assert payload["execution_assumptions"]["broker_mutation_allowed"] is False
    assert payload["execution_assumptions"]["runtime_instantiation"] == "deferred_to_strategy_candidate_validation"
    assert StrategyCandidateManifest.from_dict(payload).to_dict() == payload


def test_risk_and_portfolio_artifact_schemas_round_trip_json() -> None:
    risk_source = RiskManagerCandidateSourceRef(
        artifact_id="risk_manager_candidate_demo",
        path="artifacts/research/risk_managers/source/risk_manager_candidate_demo.py",
        source_hash="abc123",
        class_name="GrossExposureCapResearchRiskManager",
    )
    risk_manifest = RiskManagerCandidateManifest(
        candidate_id="risk_manager_candidate_demo",
        template_family="gross_exposure_cap",
        risk_manager_source=risk_source,
        parameters={"max_gross_exposure": 100_000.0},
        execution_assumptions={"backtest_only": True, "live_trading_allowed": False},
    )
    strategy_ref = StrategyCandidateArtifactLink(
        artifact_id="strategy_candidate_demo",
        artifact_type=STRATEGY_CANDIDATE,
        role="strategy",
        status="validated",
    )
    risk_ref = StrategyCandidateArtifactLink(
        artifact_id="risk_manager_candidate_demo",
        artifact_type=RISK_MANAGER_CANDIDATE,
        role="risk_manager_0",
        status="validated",
        metadata={"source_hash": "abc123"},
    )
    stack_manifest = StrategyRiskStackManifest(
        stack_id="strategy_risk_stack_demo",
        strategy_candidate_ref=strategy_ref,
        risk_manager_refs=(risk_ref,),
        execution_assumptions={"live_trading_allowed": False},
    )
    stack_report = StrategyRiskStackValidationReport(
        validation_id="strategy_risk_stack_validation_demo",
        stack_id="strategy_risk_stack_demo",
        status="passed",
        risk_manager_validation_refs=(
            StrategyCandidateArtifactLink(
                artifact_id="risk_manager_validation_demo",
                artifact_type=RISK_MANAGER_CANDIDATE_VALIDATION_REPORT,
                role="risk_manager_0_validation",
                status="passed",
            ),
        ),
    )
    portfolio_ref = PortfolioBacktestRunRef(
        run_id="portfolio_backtest_run_demo",
        strategy_risk_stack_id="strategy_risk_stack_demo",
        strategy_risk_stack_validation_id="strategy_risk_stack_validation_demo",
        dataset_id="dataset_multi_asset_demo",
        data_scope={"symbols": ["BTC/USD", "ETH/USD"], "timeframe": "1Hour"},
        symbol_metrics={"BTC/USD": {"total_return": 0.01}},
        exposure_summary={"gross_exposure_max": 12_000.0},
        risk_measure_summary={"var": 0.02, "cvar": 0.03},
    )

    assert RiskManagerCandidateManifest.from_dict(risk_manifest.to_dict()).to_dict() == risk_manifest.to_dict()
    assert StrategyRiskStackManifest.from_dict(stack_manifest.to_dict()).to_dict() == stack_manifest.to_dict()
    assert StrategyRiskStackValidationReport.from_dict(stack_report.to_dict()).to_dict() == stack_report.to_dict()
    assert PortfolioBacktestRunRef.from_dict(portfolio_ref.to_dict()).to_dict() == portfolio_ref.to_dict()
    json.dumps(
        {
            "portfolio_ref": portfolio_ref.to_dict(),
            "risk_manifest": risk_manifest.to_dict(),
            "stack_manifest": stack_manifest.to_dict(),
            "stack_report": stack_report.to_dict(),
        }
    )
