from __future__ import annotations

import json

import pytest

from trader_research.governance import (
    APPROVAL_REQUEST,
    DATA_QUALITY_REPORT,
    DATASET_MANIFEST,
    EXPERIMENT_PROTOCOL,
    RESEARCH_OBJECTIVE,
    Approval,
    ApprovalStatus,
    ArtifactCardinality,
    ArtifactSlot,
    ArtifactSlotStatus,
    CapabilityDefinition,
    CapabilitySideEffect,
    CostAssumption,
    DataRequirement,
    DatasetRole,
    ExperimentProtocol,
    ExperimentProtocolStatus,
    InitialPortfolio,
    MaterialAssumption,
    ObjectiveConstraint,
    OptimizationDirection,
    OptimizationProtocol,
    Prerequisite,
    PrerequisiteKind,
    PrerequisiteStatus,
    ProtocolDataset,
    ProtocolRiskManager,
    ProtocolStrategy,
    ResearchIssue,
    ResearchObjective,
    ResearchObjectiveStatus,
    RetryDisposition,
    RobustnessRequirement,
    TunableDimension,
    TunableValueType,
    WorkflowPlan,
    WorkflowPlanStatus,
    WorkflowStep,
    WorkflowStepResult,
    WorkflowStepStatus,
)
from trader_research.governance.handoffs import artifact_report_ref


def _data_requirement(*, start: str, end: str) -> DataRequirement:
    return DataRequirement(
        symbols=("EURUSD", "GBPUSD"),
        asset_class="forex",
        timeframe="1Hour",
        start=start,
        end=end,
        source="postgres",
    )


def _approved_protocol() -> ExperimentProtocol:
    assumption = MaterialAssumption(
        assumption_id="assumption_costs",
        category="transaction_costs",
        statement="Use five basis points of round-trip costs.",
        value={"round_trip_bps": 5.0},
    )
    approval = Approval(
        approval_id="approval_costs",
        subject_type=EXPERIMENT_PROTOCOL,
        subject_id="protocol_demo",
        assumption_id=assumption.assumption_id,
        requested_by="objective_demo",
        requested_from="operator:jared",
        status=ApprovalStatus.APPROVED,
        decided_by="operator:jared",
        rationale="Use the conservative supplied cost assumption.",
    )
    return ExperimentProtocol(
        protocol_id="protocol_demo",
        objective_id="objective_demo",
        strategy=ProtocolStrategy(
            implementation_ref=artifact_report_ref(
                "implementation_version",
                "implementation_strategy",
            ),
            parameters={"fast_window": 10},
            tunable_fields=("/strategy/parameters/fast_window",),
        ),
        risk_managers=(
            ProtocolRiskManager(
                implementation_ref=artifact_report_ref(
                    "implementation_version",
                    "implementation_risk",
                ),
                parameters={"max_orders": 10},
                tunable_fields=("/risk/0/parameters/max_orders",),
            ),
        ),
        datasets=(
            ProtocolDataset(
                requirement_id="selection",
                role=DatasetRole.SELECTION,
                requirement=_data_requirement(
                    start="2020-01-01T00:00:00Z",
                    end="2023-12-31T23:00:00Z",
                ),
                dataset_manifest_ref=artifact_report_ref(
                    DATASET_MANIFEST,
                    "selection_manifest",
                ),
                data_quality_report_ref=artifact_report_ref(
                    DATA_QUALITY_REPORT,
                    "selection_quality",
                ),
            ),
            ProtocolDataset(
                requirement_id="holdout",
                role=DatasetRole.HOLDOUT,
                requirement=_data_requirement(
                    start="2024-01-01T00:00:00Z",
                    end="2024-12-31T23:00:00Z",
                ),
                dataset_manifest_ref=artifact_report_ref(
                    DATASET_MANIFEST,
                    "holdout_manifest",
                ),
                data_quality_report_ref=artifact_report_ref(
                    DATA_QUALITY_REPORT,
                    "holdout_quality",
                ),
                sealed=True,
            ),
        ),
        costs=(CostAssumption(name="fees.bps", value=5.0, unit="bps"),),
        initial_portfolio=InitialPortfolio(cash=100_000.0, currency="USD"),
        optimization=OptimizationProtocol(
            objective_validation_ref=(
                "research://postgres/implementation_validation_report/"
                "objective_validation_demo"
            ),
            direction=OptimizationDirection.MAXIMIZE,
            trial_budget=20,
            seed=7,
            dimensions=(
                TunableDimension(
                    dimension_id="fast_window",
                    target_path="/strategy/parameters/fast_window",
                    value_type=TunableValueType.INTEGER,
                    lower=5,
                    upper=20,
                    step=1,
                ),
            ),
        ),
        robustness_requirements=(
            RobustnessRequirement(
                requirement_id="cost_sensitivity",
                attack_type="cost_sensitivity",
                claim="Performance survives materially higher costs.",
                configuration={"multipliers": [1.5, 2.0]},
            ),
        ),
        evaluation_questions=(
            "Does untouched-holdout performance remain positive after costs?",
        ),
        falsification_criteria=(
            "Reject if holdout return is non-positive after declared costs.",
        ),
        material_assumptions=(assumption,),
        approvals=(approval,),
        requested_by="objective_demo",
        proposed_by="experiment_design_agent",
        status=ExperimentProtocolStatus.APPROVED,
    )


def _slot(
    slot_id: str,
    artifact_type: str,
    domain_owner: str,
    *,
    status: ArtifactSlotStatus = ArtifactSlotStatus.EMPTY,
) -> ArtifactSlot:
    refs = (
        (artifact_report_ref(artifact_type, f"{artifact_type}_demo"),)
        if status is ArtifactSlotStatus.RESOLVED
        else ()
    )
    return ArtifactSlot(
        slot_id=slot_id,
        artifact_type=artifact_type,
        domain_owner=domain_owner,
        cardinality=ArtifactCardinality.EXACTLY_ONE,
        required=True,
        status=status,
        artifact_refs=refs,
    )


def _ready_plan() -> WorkflowPlan:
    capability = CapabilityDefinition(
        capability_id="summarize_data_quality",
        version="1",
        description="Produce bounded data-quality evidence.",
        domain_owner="Data",
        producer_tool="data_summarize_quality",
        side_effect=CapabilitySideEffect.READ_ONLY,
        input_slots=(_slot("dataset", DATASET_MANIFEST, "Data"),),
        output_slots=(_slot("quality", DATA_QUALITY_REPORT, "Data"),),
        policy_gates=("data_read_allowed",),
        configuration_keys=("minimum_coverage",),
    )
    approval = Approval(
        approval_id="approval_costs",
        subject_type=EXPERIMENT_PROTOCOL,
        subject_id="protocol_demo",
        assumption_id="assumption_costs",
        requested_by="objective_demo",
        requested_from="operator:jared",
        status=ApprovalStatus.APPROVED,
        decided_by="operator:jared",
        rationale="Approved for this protocol.",
    )
    prerequisite = Prerequisite(
        prerequisite_id="data_read_policy",
        kind=PrerequisiteKind.POLICY_GATE,
        target="data_read_allowed",
        description="Data reads are enabled.",
        status=PrerequisiteStatus.SATISFIED,
        satisfied_by=("policy://data_read_allowed/enabled",),
    )
    return WorkflowPlan(
        plan_id="workflow_demo",
        objective_ref=artifact_report_ref(RESEARCH_OBJECTIVE, "objective_demo"),
        protocol_ref=artifact_report_ref(EXPERIMENT_PROTOCOL, "protocol_demo"),
        template_id="supplied_implementation_evidence",
        template_version="1",
        capabilities=(capability,),
        artifact_slots=(
            _slot(
                "dataset_input",
                DATASET_MANIFEST,
                "Data",
                status=ArtifactSlotStatus.RESOLVED,
            ),
            _slot("quality_output", DATA_QUALITY_REPORT, "Data"),
        ),
        prerequisites=(prerequisite,),
        approvals=(approval,),
        steps=(
            WorkflowStep(
                step_id="quality",
                capability_id=capability.capability_id,
                input_bindings={"dataset": "dataset_input"},
                output_bindings={"quality": "quality_output"},
                prerequisite_ids=(prerequisite.prerequisite_id,),
                approval_ids=(approval.approval_id,),
                configuration={"minimum_coverage": 0.99},
            ),
        ),
        requested_by="objective_demo",
        actor="research_coordinator",
        status=WorkflowPlanStatus.READY,
    )


def test_research_objective_and_approved_protocol_round_trip_json() -> None:
    objective = ResearchObjective(
        objective_id="objective_demo",
        statement="Evaluate a supplied strategy and risk implementation.",
        success_criteria=("Produce holdout and robustness evidence.",),
        constraints=(
            ObjectiveConstraint(
                key="live_trading",
                value=False,
                description="Research only.",
            ),
        ),
        supplied_artifact_refs=(
            artifact_report_ref(
                "implementation_version",
                "implementation_strategy",
            ),
        ),
        requested_by="operator_request_demo",
        actor="operator:jared",
        status=ResearchObjectiveStatus.APPROVED,
    )
    protocol = _approved_protocol()

    objective_payload = objective.to_dict()
    protocol_payload = protocol.to_dict()

    assert ResearchObjective.from_dict(objective_payload) == objective
    assert ExperimentProtocol.from_dict(protocol_payload) == protocol
    assert objective_payload["artifact_type"] == RESEARCH_OBJECTIVE
    assert protocol_payload["artifact_type"] == EXPERIMENT_PROTOCOL
    assert protocol_payload["datasets"][1]["sealed"] is True
    assert protocol_payload["approvals"][0]["status"] == "approved"
    json.dumps({"objective": objective_payload, "protocol": protocol_payload})


def test_approved_protocol_rejects_unresolved_assumptions_and_unsealed_holdout() -> None:
    protocol = _approved_protocol()
    payload = protocol.to_dict()
    payload["approvals"][0] = {
        **payload["approvals"][0],
        "status": "requested",
        "decided_by": None,
        "rationale": None,
    }
    with pytest.raises(ValueError, match="unresolved approvals"):
        ExperimentProtocol.from_dict(payload)

    payload = protocol.to_dict()
    payload["datasets"][1]["sealed"] = False
    with pytest.raises(ValueError, match="holdout dataset requirements must be sealed"):
        ExperimentProtocol.from_dict(payload)

    payload = protocol.to_dict()
    payload["datasets"] = payload["datasets"][:1]
    with pytest.raises(
        ValueError,
        match="optimization requires selection and sealed holdout",
    ):
        ExperimentProtocol.from_dict(payload)

    payload = protocol.to_dict()
    payload["datasets"][1]["requirement"]["start"] = "2023-12-31T23:00:00Z"
    with pytest.raises(ValueError, match="holdout must begin after"):
        ExperimentProtocol.from_dict(payload)


def test_protocol_rejects_invalid_or_undeclared_tunable_paths() -> None:
    payload = _approved_protocol().to_dict()
    payload["risk_managers"][0]["tunable_fields"] = [
        "/risk/managers/0/parameters/max_orders"
    ]
    with pytest.raises(ValueError, match="risk tunable fields must target"):
        ExperimentProtocol.from_dict(payload)

    payload = _approved_protocol().to_dict()
    payload["risk_managers"][0]["tunable_fields"] = [
        "/risk/1/parameters/max_orders"
    ]
    with pytest.raises(ValueError, match="risk manager 0 tunable fields"):
        ExperimentProtocol.from_dict(payload)

    payload = _approved_protocol().to_dict()
    payload["optimization"]["dimensions"][0]["target_path"] = (
        "/strategy/parameters/undeclared"
    )
    with pytest.raises(ValueError, match="not declared tunable"):
        ExperimentProtocol.from_dict(payload)


def test_workflow_plan_round_trip_validates_capabilities_slots_and_readiness() -> None:
    plan = _ready_plan()
    payload = plan.to_dict()

    assert WorkflowPlan.from_dict(payload) == plan
    assert payload["capabilities"][0]["producer_tool"] == "data_summarize_quality"
    assert payload["artifact_slots"][0]["status"] == "resolved"
    assert payload["status"] == "ready"
    assert "service" not in payload["capabilities"][0]
    assert "callable" not in payload["capabilities"][0]
    json.dumps(payload)


def test_workflow_plan_rejects_invented_capabilities_bad_bindings_and_cycles() -> None:
    payload = _ready_plan().to_dict()
    payload["steps"][0]["capability_id"] = "invented_tool"
    with pytest.raises(ValueError, match="uses unknown capability invented_tool"):
        WorkflowPlan.from_dict(payload)

    payload = _ready_plan().to_dict()
    payload["steps"][0]["output_bindings"]["quality"] = "dataset_input"
    with pytest.raises(ValueError, match="does not match slot dataset_input"):
        WorkflowPlan.from_dict(payload)

    payload = _ready_plan().to_dict()
    payload["steps"].append(
        {
            **payload["steps"][0],
            "step_id": "second_quality",
            "depends_on": ["quality"],
        }
    )
    payload["steps"][0]["depends_on"] = ["second_quality"]
    with pytest.raises(ValueError, match="dependencies contain a cycle"):
        WorkflowPlan.from_dict(payload)


def test_ready_workflow_rejects_unresolved_prerequisites_and_approvals() -> None:
    payload = _ready_plan().to_dict()
    payload["prerequisites"][0] = {
        **payload["prerequisites"][0],
        "status": "unresolved",
        "satisfied_by": [],
    }
    with pytest.raises(ValueError, match="ready workflow plans require satisfied"):
        WorkflowPlan.from_dict(payload)

    payload = _ready_plan().to_dict()
    payload["approvals"][0] = {
        **payload["approvals"][0],
        "status": "requested",
        "decided_by": None,
        "rationale": None,
    }
    with pytest.raises(ValueError, match="ready workflow plans require satisfied"):
        WorkflowPlan.from_dict(payload)

    payload = _ready_plan().to_dict()
    payload["artifact_slots"][0] = {
        **payload["artifact_slots"][0],
        "status": "empty",
        "artifact_refs": [],
    }
    with pytest.raises(ValueError, match="and input slots"):
        WorkflowPlan.from_dict(payload)

    payload = _ready_plan().to_dict()
    payload["prerequisites"][0]["target"] = "invented_policy_gate"
    with pytest.raises(ValueError, match="targets unknown policy_gate"):
        WorkflowPlan.from_dict(payload)


def test_workflow_step_result_is_bounded_json_and_requires_explicit_retry() -> None:
    succeeded = WorkflowStepResult(
        result_id="result_demo",
        plan_id="workflow_demo",
        step_id="quality",
        attempt=1,
        command="data_summarize_quality",
        side_effect=CapabilitySideEffect.READ_ONLY,
        status=WorkflowStepStatus.SUCCEEDED,
        requested_by="workflow_demo",
        actor="research_coordinator",
        idempotency_key="workflow_demo:quality:1",
        produced_artifact_refs=(
            artifact_report_ref(DATA_QUALITY_REPORT, "quality_demo"),
        ),
        public_data={"coverage": 1.0},
    )
    payload = succeeded.to_dict()

    assert WorkflowStepResult.from_dict(payload) == succeeded
    assert payload["retry"] == "not_applicable"
    assert "raw_tool_payload" not in payload
    json.dumps(payload)

    with pytest.raises(ValueError, match="require a retry disposition"):
        WorkflowStepResult(
            result_id="result_blocked",
            plan_id="workflow_demo",
            step_id="quality",
            attempt=1,
            command="data_summarize_quality",
            side_effect=CapabilitySideEffect.READ_ONLY,
            status=WorkflowStepStatus.BLOCKED,
            requested_by="workflow_demo",
            actor="research_coordinator",
            idempotency_key="workflow_demo:quality:1",
            blockers=(
                ResearchIssue(
                    code="data_unavailable",
                    message="Dataset is not available.",
                ),
            ),
            retry=RetryDisposition.NOT_APPLICABLE,
        )


def test_approval_contract_is_canonical_and_decisions_are_explicit() -> None:
    requested = Approval(
        approval_id="approval_demo",
        subject_type=EXPERIMENT_PROTOCOL,
        subject_id="protocol_demo",
        assumption_id="assumption_demo",
        requested_by="workflow_demo",
        requested_from="operator:jared",
    )

    assert requested.to_dict()["artifact_type"] == APPROVAL_REQUEST
    assert Approval.from_dict(requested.to_dict()) == requested
    with pytest.raises(ValueError, match="cannot contain decision fields"):
        Approval(
            approval_id="approval_demo",
            subject_type=EXPERIMENT_PROTOCOL,
            subject_id="protocol_demo",
            assumption_id="assumption_demo",
            requested_by="workflow_demo",
            requested_from="operator:jared",
            rationale="Not decided yet.",
        )


def test_capabilities_reject_runtime_state_and_non_research_side_effects() -> None:
    payload = _ready_plan().capabilities[0].to_dict()
    payload["input_slots"][0] = {
        **payload["input_slots"][0],
        "status": "resolved",
        "artifact_refs": [
            artifact_report_ref(DATASET_MANIFEST, "dataset_demo").to_dict()
        ],
    }
    with pytest.raises(ValueError, match="slot declarations must be empty"):
        CapabilityDefinition.from_dict(payload)

    payload = _ready_plan().capabilities[0].to_dict()
    payload["side_effect"] = "broker_mutating"
    with pytest.raises(ValueError, match="unsupported capability side_effect"):
        CapabilityDefinition.from_dict(payload)
