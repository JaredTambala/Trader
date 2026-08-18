"""Contract and policy tests for bounded Research Coordinator decisions."""

from __future__ import annotations

from dataclasses import replace

import anyio
import pytest

from trader_agents import (
    WORKFLOW_TEMPLATE_ID,
    WORKFLOW_TEMPLATE_VERSION,
    CoordinationDecision,
    CoordinatorAction,
    RegisteredWorkflowTemplate,
    WorkflowTemplateCatalog,
    WorkflowTemplateDescriptor,
    build_research_coordinator_graph,
    build_research_coordinator_initial_state,
    compile_coordination_decision,
    compile_supplied_implementation_workflow,
    coordinate_research,
)
from trader_research.foundation import (
    InMemoryResearchArtifactStore,
    UnavailableResearchArtifactStore,
)
from trader_research.governance import (
    DATASET_MANIFEST,
    DATA_QUALITY_REPORT,
    EXPERIMENT_PROTOCOL,
    RESEARCH_OBJECTIVE,
    DOMAIN_OWNER_BY_ARTIFACT_TYPE,
    DataRequirement,
    DatasetRole,
    ExperimentProtocol,
    ExperimentProtocolStatus,
    InitialPortfolio,
    ProtocolDataset,
    ProtocolRiskManager,
    ProtocolStrategy,
    ResearchObjective,
    ResearchObjectiveStatus,
    RobustnessRequirement,
    WorkflowOutcome,
    WorkflowOutcomeStatus,
    artifact_report_ref,
)
from trader_research.governance.artifacts import IMPLEMENTATION_VERSION


def test_coordinator_selects_and_compiles_only_registered_workflow() -> None:
    store = _artifact_store()
    objective = _objective()
    protocol = _protocol()

    result = coordinate_research(
        objective=objective,
        protocol=protocol,
        artifact_store=store,
    )

    assert result.decision.action is CoordinatorAction.EXECUTE_REGISTERED_WORKFLOW
    assert result.decision.template_id == WORKFLOW_TEMPLATE_ID
    assert result.decision.template_version == WORKFLOW_TEMPLATE_VERSION
    assert result.compiled_workflow is not None
    assert result.decision.plan_id == result.compiled_workflow.plan.plan_id
    assert result.compiled_workflow.protocol == protocol

    recompiled = compile_coordination_decision(
        decision=result.decision,
        objective=objective,
        protocol=protocol,
        artifact_store=store,
    )
    assert recompiled.plan == result.compiled_workflow.plan


def test_coordinator_requests_missing_protocol_from_its_owner() -> None:
    result = coordinate_research(
        objective=_objective(),
        protocol=None,
        artifact_store=InMemoryResearchArtifactStore(),
    )

    assert result.decision.action is CoordinatorAction.REQUEST_PREREQUISITE
    assert [item.target for item in result.decision.prerequisites] == [
        EXPERIMENT_PROTOCOL
    ]
    assert result.compiled_workflow is None


def test_coordinator_requests_objective_and_protocol_approvals() -> None:
    draft = coordinate_research(
        objective=_objective(status=ResearchObjectiveStatus.DRAFT),
        protocol=None,
        artifact_store=InMemoryResearchArtifactStore(),
    )
    proposed_protocol = coordinate_research(
        objective=_objective(),
        protocol=_protocol(status=ExperimentProtocolStatus.PROPOSED),
        artifact_store=InMemoryResearchArtifactStore(),
    )

    assert draft.decision.action is CoordinatorAction.REQUEST_APPROVAL
    assert [item.target for item in draft.decision.prerequisites] == ["objective_demo"]
    assert proposed_protocol.decision.action is CoordinatorAction.REQUEST_APPROVAL
    assert [item.target for item in proposed_protocol.decision.prerequisites] == [
        "protocol_demo"
    ]


def test_coordinator_turns_unresolved_canonical_input_into_prerequisite() -> None:
    result = coordinate_research(
        objective=_objective(),
        protocol=_protocol(),
        artifact_store=InMemoryResearchArtifactStore(),
    )

    assert result.decision.action is CoordinatorAction.REQUEST_PREREQUISITE
    assert [item.target for item in result.decision.prerequisites] == [
        "research://postgres/implementation_version/strategy_demo"
    ]
    assert result.compiled_workflow is None


def test_coordinator_blocks_when_canonical_store_is_unavailable() -> None:
    result = coordinate_research(
        objective=_objective(),
        protocol=_protocol(),
        artifact_store=UnavailableResearchArtifactStore("database unavailable"),
    )

    assert result.decision.action is CoordinatorAction.BLOCK
    assert result.decision.blockers[0].code == "workflow_input_store_unavailable"
    assert result.compiled_workflow is None


def test_coordinator_blocks_unmatched_and_ambiguous_templates() -> None:
    unmatched = coordinate_research(
        objective=_objective(),
        protocol=_protocol(robustness=True),
        artifact_store=_artifact_store(),
    )
    ambiguous_catalog = WorkflowTemplateCatalog(
        (
            _registration("first_template"),
            _registration("second_template"),
        )
    )
    ambiguous = coordinate_research(
        objective=_objective(),
        protocol=_protocol(),
        artifact_store=_artifact_store(),
        catalog=ambiguous_catalog,
    )

    assert unmatched.decision.action is CoordinatorAction.BLOCK
    assert unmatched.decision.blockers[0].code == "no_registered_workflow_template"
    assert ambiguous.decision.action is CoordinatorAction.BLOCK
    assert (
        ambiguous.decision.blockers[0].code == "ambiguous_registered_workflow_template"
    )


def test_coordination_contract_rejects_hidden_scope_and_unknown_templates() -> None:
    with pytest.raises(ValueError, match="unknown fields: tool_name"):
        CoordinationDecision.from_dict(
            {
                "action": "request_prerequisite",
                "objective_id": "objective_demo",
                "prerequisites": [
                    {
                        "prerequisite_id": "data_required",
                        "kind": "artifact",
                        "target": DATASET_MANIFEST,
                        "description": "Resolve Data evidence.",
                        "required": True,
                        "status": "unresolved",
                        "satisfied_by": [],
                        "blockers": [],
                    }
                ],
                "tool_name": "invented_tool",
            }
        )

    with pytest.raises(ValueError, match="coordination prerequisite.*tool_name"):
        CoordinationDecision.from_dict(
            {
                "action": "request_prerequisite",
                "objective_id": "objective_demo",
                "prerequisites": [
                    {
                        "prerequisite_id": "data_required",
                        "kind": "artifact",
                        "target": DATASET_MANIFEST,
                        "description": "Resolve Data evidence.",
                        "required": True,
                        "status": "unresolved",
                        "satisfied_by": [],
                        "blockers": [],
                        "tool_name": "invented_tool",
                    }
                ],
            }
        )

    invented = CoordinationDecision(
        action=CoordinatorAction.EXECUTE_REGISTERED_WORKFLOW,
        objective_id="objective_demo",
        protocol_id="protocol_demo",
        template_id="invented_template",
        template_version="1",
        plan_id="invented_plan",
    )
    with pytest.raises(ValueError, match="not registered"):
        compile_coordination_decision(
            decision=invented,
            objective=_objective(),
            protocol=_protocol(),
            artifact_store=_artifact_store(),
        )

    selected = coordinate_research(
        objective=_objective(),
        protocol=_protocol(),
        artifact_store=_artifact_store(),
    ).decision
    with pytest.raises(ValueError, match="plan does not match"):
        compile_coordination_decision(
            decision=selected,
            objective=_objective(),
            protocol=replace(_protocol(), deterministic_seed=99),
            artifact_store=_artifact_store(),
        )


def test_coordinator_reports_only_matching_terminal_outcome() -> None:
    objective = _objective()
    protocol = _protocol()
    outcome = WorkflowOutcome(
        outcome_id="outcome_demo",
        workflow_id="workflow_demo",
        plan_id="plan_demo",
        objective_ref=artifact_report_ref(RESEARCH_OBJECTIVE, objective.objective_id),
        protocol_ref=artifact_report_ref(EXPERIMENT_PROTOCOL, protocol.protocol_id),
        status=WorkflowOutcomeStatus.COMPLETED,
        produced_artifact_refs=(),
        review_verdict_refs=(),
        requested_by="operator:jared",
        actor="research_coordinator",
        next_permitted_actions=("request_human_review",),
    )

    result = coordinate_research(
        objective=objective,
        protocol=protocol,
        outcome=outcome,
        artifact_store=InMemoryResearchArtifactStore(),
    )

    assert result.decision.action is CoordinatorAction.REPORT_TERMINAL_STATE
    assert result.decision.outcome_id == "outcome_demo"
    assert result.decision.next_permitted_actions == ("request_human_review",)


def test_research_coordinator_graph_projects_bounded_public_state() -> None:
    async def run() -> None:
        objective = _objective()
        protocol = _protocol()
        graph = build_research_coordinator_graph(artifact_store=_artifact_store())

        state = await graph.ainvoke(
            build_research_coordinator_initial_state(
                objective=objective,
                protocol=protocol,
            )
        )

        assert state["status"] == "completed"
        assert state["public_status"] == "ready_for_execution"
        assert state["decision"]["action"] == "execute_registered_workflow"
        assert state["workflow_plan"]["plan_id"] == state["decision"]["plan_id"]
        assert "tool_name" not in state["decision"]
        assert state["errors"] == []

    anyio.run(run)


def test_research_coordinator_graph_rejects_artifact_ownership_violation() -> None:
    async def run() -> None:
        state = build_research_coordinator_initial_state(
            objective=_objective(),
            protocol=_protocol(),
        )
        protocol = state["protocol"]
        datasets = protocol["datasets"]
        datasets[0]["dataset_manifest_ref"]["domain_owner"] = "Experiments"
        graph = build_research_coordinator_graph(artifact_store=_artifact_store())

        result = await graph.ainvoke(state)

        assert result["status"] == "failed"
        assert result["public_status"] == "failed_validation"
        assert result["errors"][0]["code"] == "invalid_coordination_input"
        assert result["decision"] == {}

    anyio.run(run)


def _objective(
    *,
    status: ResearchObjectiveStatus = ResearchObjectiveStatus.APPROVED,
) -> ResearchObjective:
    return ResearchObjective(
        objective_id="objective_demo",
        statement="Evaluate the supplied strategy and risk implementation.",
        success_criteria=("Produce reproducible baseline evidence.",),
        requested_by="operator:jared",
        actor="operator:jared",
        status=status,
    )


def _protocol(
    *,
    status: ExperimentProtocolStatus = ExperimentProtocolStatus.APPROVED,
    robustness: bool = False,
) -> ExperimentProtocol:
    return ExperimentProtocol(
        protocol_id="protocol_demo",
        objective_id="objective_demo",
        strategy=ProtocolStrategy(
            implementation_ref=artifact_report_ref(
                IMPLEMENTATION_VERSION,
                "strategy_demo",
            ),
            parameters={"period": 10},
        ),
        risk_managers=(
            ProtocolRiskManager(
                implementation_ref=artifact_report_ref(
                    IMPLEMENTATION_VERSION,
                    "risk_demo",
                ),
                parameters={"max_orders": 5},
            ),
        ),
        datasets=(
            ProtocolDataset(
                requirement_id="baseline",
                role=DatasetRole.BASELINE,
                requirement=DataRequirement(
                    symbols=("DEMO",),
                    asset_class="stocks",
                    timeframe="1Min",
                    start="2026-01-01T00:00:00Z",
                    end="2026-01-31T23:59:00Z",
                ),
                dataset_manifest_ref=artifact_report_ref(
                    DATASET_MANIFEST,
                    "manifest_demo",
                ),
                data_quality_report_ref=artifact_report_ref(
                    DATA_QUALITY_REPORT,
                    "quality_demo",
                ),
            ),
        ),
        costs=(),
        initial_portfolio=InitialPortfolio(cash=100_000.0, currency="USD"),
        robustness_requirements=(
            (
                RobustnessRequirement(
                    requirement_id="cost_stress",
                    attack_type="cost_sensitivity",
                    claim="The result survives higher costs.",
                    configuration={"multipliers": [2.0]},
                ),
            )
            if robustness
            else ()
        ),
        evaluation_questions=("Is the baseline result reproducible?",),
        falsification_criteria=("Reject if the run cannot be reproduced.",),
        material_assumptions=(),
        approvals=(),
        requested_by="objective_demo",
        proposed_by="experiment_design_agent",
        status=status,
    )


def _artifact_store() -> InMemoryResearchArtifactStore:
    store = InMemoryResearchArtifactStore()
    for artifact_type, artifact_id in (
        (IMPLEMENTATION_VERSION, "strategy_demo"),
        (IMPLEMENTATION_VERSION, "risk_demo"),
        (DATASET_MANIFEST, "manifest_demo"),
        (DATA_QUALITY_REPORT, "quality_demo"),
    ):
        store.save_artifact(
            artifact_type=artifact_type,
            artifact_id=artifact_id,
            domain_owner=DOMAIN_OWNER_BY_ARTIFACT_TYPE[artifact_type],
            producer_tool="test_fixture",
            payload={"artifact_type": artifact_type, "artifact_id": artifact_id},
            status="ready",
        )
    return store


def _registration(template_id: str) -> RegisteredWorkflowTemplate:
    return RegisteredWorkflowTemplate(
        descriptor=WorkflowTemplateDescriptor(
            template_id=template_id,
            version="1",
            description=f"Test registration {template_id}.",
        ),
        is_eligible=lambda objective, protocol: True,
        compiler=compile_supplied_implementation_workflow,
    )
