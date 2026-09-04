"""Unit contracts for the closed research artifact-authority vocabulary.

Subject: Governance ownership of supported artifact types and canonical artifact references.
Level: In-process unit contract.
Collaborators: Real governance registries and foundation identity helpers; no store or external service.
Guarantees: Retired types stay absent and every supported reference resolves to one bounded context.
Non-goals: Specialist handoff payloads, persistence, workflow execution, or MCP tool authorization.
"""

from __future__ import annotations

import json

import trader_research.governance.artifacts as research_artifacts
from trader_research.foundation import SUPPORTED_DOMAIN_OWNERS
from trader_research.governance.artifacts import (
    BACKTEST_RUN,
    BACKTEST_SPECIFICATION,
    BACKTEST_SPECIFICATION_VALIDATION_REPORT,
    COMPARISON_REPORT,
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
from trader_research.governance.handoffs import artifact_report_ref


def test_retired_candidate_domain_contracts_are_absent() -> None:
    """Removed candidate-era names cannot silently re-enter the public artifact vocabulary."""
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
    """Every supported artifact type maps exhaustively to one approved domain owner."""
    assert set(research_artifacts.DOMAIN_OWNER_BY_ARTIFACT_TYPE.values()) == set(
        SUPPORTED_DOMAIN_OWNERS
    )
    assert set(research_artifacts.SUPPORTED_ARTIFACT_TYPES) == set(
        research_artifacts.DOMAIN_OWNER_BY_ARTIFACT_TYPE
    )
    assert not hasattr(research_artifacts, "OWNER_BY_ARTIFACT_TYPE")


def test_planned_artifact_reference_types_are_json_safe() -> None:
    """Planned artifact references serialize safely and retain their authoritative domain owners."""
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
        item["uri"].startswith(f"research://postgres/{item['artifact_type']}/")
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
