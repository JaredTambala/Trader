from __future__ import annotations

import json

import pytest

from trader_research.contracts import SideEffect
from trader_research.domain import (
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
    METHOD_PACKAGE_MANIFEST,
    MODEL_CARD,
    MULTIPLE_TESTING_REPORT,
    ROBUSTNESS_REPORT,
    SIGNAL_DIAGNOSTIC_REPORT,
    STATISTICAL_TEST_REPORT,
    STRATEGY_CANDIDATE,
    BoundedResearchRequest,
    DataRequirement,
    ResearchIssue,
    SpecialistHandoff,
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
        artifact_report_ref(EVALUATION_REPORT, "eval_demo"),
        artifact_report_ref(ROBUSTNESS_REPORT, "robust_demo"),
    ]

    payload = [ref.to_dict() for ref in refs]

    assert payload[0]["agent_owner"] == "Hypothesis Agent"
    assert payload[1]["agent_owner"] == "Quantitative Methods Agent"
    assert payload[2]["agent_owner"] == "Quantitative Methods Agent"
    assert payload[3]["agent_owner"] == "Quantitative Methods Agent"
    assert payload[4]["agent_owner"] == "Quantitative Methods Agent"
    assert payload[5]["agent_owner"] == "Quantitative Methods Agent"
    assert payload[6]["agent_owner"] == "Quantitative Methods Agent"
    assert payload[7]["agent_owner"] == "Quantitative Methods Agent"
    assert payload[8]["agent_owner"] == "Quantitative Methods Agent"
    assert payload[10]["agent_owner"] == "ML Agent"
    assert payload[12]["agent_owner"] == "Quant Research Supervisor Agent"
    assert payload[13]["agent_owner"] == "Evaluation Agent"
    assert payload[14]["agent_owner"] == "Adversarial Agent"
    json.dumps(payload)
