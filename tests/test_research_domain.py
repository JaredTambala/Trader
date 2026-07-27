from __future__ import annotations

import json

import pytest

import trader_research.governance.artifacts as research_artifacts
from trader_research.foundation import SUPPORTED_DOMAIN_OWNERS, stable_research_id
from trader_research.governance.artifacts import (
    BACKTEST_RUN,
    BACKTEST_SPECIFICATION,
    BACKTEST_SPECIFICATION_VALIDATION_REPORT,
    COMPARISON_REPORT,
    DATA_QUALITY_REPORT,
    DATASET_MANIFEST,
    DOMAIN_OWNER_BY_ARTIFACT_TYPE,
    CITATION_VALIDATION_REPORT,
    CXX_KERNEL_MANIFEST,
    EVIDENCE_RETRIEVAL_REPORT,
    EVALUATION_REPORT,
    EXPERIMENT_TRACKING_PROJECTION_REPORT,
    EXPERIMENT_PROTOCOL,
    FEATURE_MANIFEST,
    HYPOTHESIS_CARD,
    INDICATOR_METADATA,
    IMPLEMENTATION_VALIDATION_REPORT,
    IMPLEMENTATION_VERSION,
    METHOD_CARD,
    METHODOLOGY_CANDIDATE,
    METHODOLOGY_CANDIDATE_VALIDATION_REPORT,
    METHODOLOGY_FIELD_EXTRACTION_REPORT,
    METHOD_PACKAGE_MANIFEST,
    MODEL_CARD,
    MULTIPLE_TESTING_REPORT,
    PARAMETER_OPTIMIZATION_AUDIT_PLAN,
    PARAMETER_OPTIMIZATION_EVALUATION_REPORT,
    PARAMETER_OPTIMIZATION_PLAN,
    PARAMETER_OPTIMIZATION_ROBUSTNESS_REPORT,
    PARAMETER_OPTIMIZATION_RUN,
    PARAMETER_OPTIMIZATION_TRIAL,
    ROBUSTNESS_REPORT,
    RESEARCH_OBJECTIVE,
    RISK_STACK_SPECIFICATION,
    RISK_STACK_SPECIFICATION_VALIDATION_REPORT,
    SIGNAL_DIAGNOSTIC_REPORT,
    STATISTICAL_TEST_REPORT,
    STRATEGY_SPECIFICATION,
    STRATEGY_SPECIFICATION_VALIDATION_REPORT,
    WORKFLOW_PLAN,
)
from trader_research.governance.handoffs import (
    BoundedResearchRequest,
    DataRequirement,
    ResearchIssue,
    SpecialistHandoff,
    artifact_report_ref,
)


def _data_requirement() -> DataRequirement:
    return DataRequirement(
        symbols=("DEMO",),
        asset_class="stocks",
        timeframe="1Min",
        start="2026-01-20T12:00:00Z",
        end="2026-01-20T12:11:00Z",
    )


def test_retired_candidate_domain_contracts_are_absent() -> None:
    retired_names = {
        "STRATEGY_CANDIDATE",
        "STRATEGY_CANDIDATE_VALIDATION_REPORT",
        "RISK_MANAGER_CANDIDATE",
        "RISK_MANAGER_CANDIDATE_VALIDATION_REPORT",
        "STRATEGY_RISK_STACK",
        "STRATEGY_RISK_STACK_VALIDATION_REPORT",
        "BACKTEST_RUN_REF",
        "PORTFOLIO_BACKTEST_RUN_REF",
        "StrategyCandidate",
        "StrategyCandidateManifest",
        "RiskManagerCandidateManifest",
        "StrategyRiskStackManifest",
        "BacktestRunRef",
        "PortfolioBacktestRunRef",
    }

    assert [
        name for name in sorted(retired_names) if hasattr(research_artifacts, name)
    ] == []


def test_artifact_domain_authority_registry_is_closed_and_exhaustive() -> None:
    assert set(research_artifacts.DOMAIN_OWNER_BY_ARTIFACT_TYPE.values()) == set(
        SUPPORTED_DOMAIN_OWNERS
    )
    assert set(research_artifacts.SUPPORTED_ARTIFACT_TYPES) == set(
        research_artifacts.DOMAIN_OWNER_BY_ARTIFACT_TYPE
    )
    assert not hasattr(research_artifacts, "OWNER_BY_ARTIFACT_TYPE")


def test_research_request_and_handoff_round_trip_json() -> None:
    request = BoundedResearchRequest(
        request_id=stable_research_id("research_request", {"objective": "demo"}),
        objective="Evaluate a demo strategy.",
        data_requirement=_data_requirement(),
    )
    warning = ResearchIssue(code="data_agent_warning", message="Partial coverage.")
    handoff = SpecialistHandoff(
        handoff_id="handoff_demo",
        domain_owner="Data",
        producer_tool="data_get_inventory",
        requested_by=request.request_id,
        actor="Data Agent",
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
    )

    request_payload = request.to_dict()
    handoff_payload = handoff.to_dict()

    assert (
        BoundedResearchRequest.from_dict(request_payload).to_dict() == request_payload
    )
    assert SpecialistHandoff.from_dict(handoff_payload).to_dict() == handoff_payload
    assert handoff_payload["domain_owner"] == "Data"
    assert handoff_payload["producer_tool"] == "data_get_inventory"
    assert handoff_payload["requested_by"] == request.request_id
    assert handoff_payload["actor"] == "Data Agent"
    assert "agent_owner" not in handoff_payload
    assert "artifact_path" not in handoff_payload
    assert handoff_payload["warnings"] == [
        {"code": "data_agent_warning", "message": "Partial coverage.", "details": {}}
    ]
    json.dumps({"request": request_payload, "handoff": handoff_payload})


def test_domain_validation_rejects_missing_bounds_and_bad_handoffs() -> None:
    with pytest.raises(ValueError, match="symbols are required"):
        DataRequirement(
            symbols=(), asset_class="stocks", timeframe="1Min", start="s", end="e"
        )
    with pytest.raises(ValueError, match="domain_owner is required"):
        SpecialistHandoff(
            handoff_id="handoff",
            domain_owner="",
            producer_tool="data_get_inventory",
            requested_by="request_demo",
            actor="Data Agent",
            artifact_type=DATASET_MANIFEST,
            payload={"ok": True},
        )
    with pytest.raises(ValueError, match="unsupported artifact type"):
        SpecialistHandoff(
            handoff_id="handoff",
            domain_owner="Data",
            producer_tool="data_get_inventory",
            requested_by="request_demo",
            actor="Data Agent",
            artifact_type="raw_bars",
            payload={"ok": True},
        )
    with pytest.raises(ValueError, match="must be owned by the Data domain"):
        SpecialistHandoff(
            handoff_id="handoff",
            domain_owner="Experiments",
            producer_tool="data_summarize_quality",
            requested_by="request_demo",
            actor="Quant Research Supervisor Agent",
            artifact_type=DATA_QUALITY_REPORT,
            payload={"complete": True},
        )
    with pytest.raises(ValueError, match="artifact_uri type backtest_run"):
        SpecialistHandoff(
            handoff_id="handoff",
            domain_owner="Data",
            producer_tool="data_get_inventory",
            requested_by="request_demo",
            actor="Data Agent",
            artifact_type=DATASET_MANIFEST,
            artifact_uri="research://postgres/backtest_run/run_demo",
        )


def test_planned_artifact_reference_types_are_json_safe() -> None:
    refs = [
        artifact_report_ref(HYPOTHESIS_CARD, "hypothesis_demo"),
        artifact_report_ref(METHODOLOGY_CANDIDATE, "methodology_candidate_demo"),
        artifact_report_ref(
            METHODOLOGY_FIELD_EXTRACTION_REPORT, "methodology_field_extraction_demo"
        ),
        artifact_report_ref(
            METHODOLOGY_CANDIDATE_VALIDATION_REPORT, "methodology_validation_demo"
        ),
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
        artifact_report_ref(RESEARCH_OBJECTIVE, "objective_demo"),
        artifact_report_ref(EXPERIMENT_PROTOCOL, "protocol_demo"),
        artifact_report_ref(WORKFLOW_PLAN, "workflow_demo"),
        artifact_report_ref(IMPLEMENTATION_VERSION, "implementation_demo"),
        artifact_report_ref(
            IMPLEMENTATION_VALIDATION_REPORT, "implementation_validation_demo"
        ),
        artifact_report_ref(STRATEGY_SPECIFICATION, "strategy_specification_demo"),
        artifact_report_ref(
            STRATEGY_SPECIFICATION_VALIDATION_REPORT,
            "strategy_specification_validation_demo",
        ),
        artifact_report_ref(RISK_STACK_SPECIFICATION, "risk_stack_specification_demo"),
        artifact_report_ref(
            RISK_STACK_SPECIFICATION_VALIDATION_REPORT,
            "risk_stack_specification_validation_demo",
        ),
        artifact_report_ref(BACKTEST_SPECIFICATION, "backtest_specification_demo"),
        artifact_report_ref(
            BACKTEST_SPECIFICATION_VALIDATION_REPORT, "backtest_validation_demo"
        ),
        artifact_report_ref(BACKTEST_RUN, "backtest_run_demo"),
        artifact_report_ref(PARAMETER_OPTIMIZATION_PLAN, "optimization_plan_demo"),
        artifact_report_ref(PARAMETER_OPTIMIZATION_RUN, "optimization_run_demo"),
        artifact_report_ref(PARAMETER_OPTIMIZATION_TRIAL, "optimization_trial_demo"),
        artifact_report_ref(
            EXPERIMENT_TRACKING_PROJECTION_REPORT, "tracking_projection_demo"
        ),
        artifact_report_ref(
            PARAMETER_OPTIMIZATION_EVALUATION_REPORT, "optimization_evaluation_demo"
        ),
        artifact_report_ref(
            PARAMETER_OPTIMIZATION_AUDIT_PLAN, "optimization_audit_plan_demo"
        ),
        artifact_report_ref(
            PARAMETER_OPTIMIZATION_ROBUSTNESS_REPORT, "optimization_robustness_demo"
        ),
        artifact_report_ref(COMPARISON_REPORT, "comparison_demo"),
        artifact_report_ref(EVALUATION_REPORT, "eval_demo"),
        artifact_report_ref(ROBUSTNESS_REPORT, "robust_demo"),
    ]

    payload = [ref.to_dict() for ref in refs]
    assert all(
        item["uri"].startswith(
            f"research://postgres/{item['artifact_type']}/"
        )
        for item in payload
    )
    assert all("path" not in item for item in payload)
    owner_by_type = {item["artifact_type"]: item["domain_owner"] for item in payload}

    assert owner_by_type[HYPOTHESIS_CARD] == "Experiments"
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
        assert owner_by_type[artifact_type] == "Knowledge/Methodology"
    assert owner_by_type[FEATURE_MANIFEST] == "ML"
    assert owner_by_type[MODEL_CARD] == "ML"
    for artifact_type in (
        IMPLEMENTATION_VERSION,
        IMPLEMENTATION_VALIDATION_REPORT,
        STRATEGY_SPECIFICATION,
        STRATEGY_SPECIFICATION_VALIDATION_REPORT,
        RISK_STACK_SPECIFICATION,
        RISK_STACK_SPECIFICATION_VALIDATION_REPORT,
        BACKTEST_SPECIFICATION,
        BACKTEST_SPECIFICATION_VALIDATION_REPORT,
        BACKTEST_RUN,
        PARAMETER_OPTIMIZATION_PLAN,
        PARAMETER_OPTIMIZATION_RUN,
        PARAMETER_OPTIMIZATION_TRIAL,
        EXPERIMENT_TRACKING_PROJECTION_REPORT,
        COMPARISON_REPORT,
    ):
        assert owner_by_type[artifact_type] == "Experiments"
    for artifact_type in (
        EVALUATION_REPORT,
        PARAMETER_OPTIMIZATION_EVALUATION_REPORT,
        ROBUSTNESS_REPORT,
        PARAMETER_OPTIMIZATION_AUDIT_PLAN,
        PARAMETER_OPTIMIZATION_ROBUSTNESS_REPORT,
    ):
        assert owner_by_type[artifact_type] == "Review"
    assert owner_by_type == {
        artifact_type: DOMAIN_OWNER_BY_ARTIFACT_TYPE[artifact_type]
        for artifact_type in owner_by_type
    }
    json.dumps(payload)
