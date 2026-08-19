"""Conformance tests for bounded specialist contracts and graph execution."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
import json
from typing import Any

import pytest

from trader_agents import (
    RegisteredSpecialistAction,
    SpecialistActionCatalog,
    SpecialistActionOutcome,
    SpecialistActionStatus,
    SpecialistDecision,
    SpecialistPolicyAction,
    SpecialistPolicyContext,
    SpecialistResult,
    SpecialistResultStatus,
    SpecialistTask,
    build_specialist_graph,
    build_specialist_initial_state,
    specialist_public_state,
)
from trader_research.foundation import research_artifact_uri
from trader_research.governance import (
    DATASET_MANIFEST,
    DATA_QUALITY_REPORT,
    EXPERIMENT_PROTOCOL,
    ArtifactCardinality,
    ArtifactSlot,
    ArtifactSlotStatus,
    CapabilityDefinition,
    CapabilitySideEffect,
    Prerequisite,
    PrerequisiteKind,
    ResearchIssue,
    ResearchObjective,
    ResearchObjectiveStatus,
    SpecialistHandoff,
)


class InventoryPolicy:
    """Select one inventory action and complete after its handoff is accepted."""

    async def decide(
        self,
        context: SpecialistPolicyContext,
    ) -> SpecialistDecision:
        if not context.action_summaries:
            return SpecialistDecision(
                action=SpecialistPolicyAction.RUN_REGISTERED_ACTION,
                task_id=context.task.task_id,
                authority_key=context.task.authority_key,
                reason="Resolve the requested dataset manifest.",
                action_id="inspect_market_data_inventory",
                action_version="1",
                output_bindings={"manifest": "requested_manifest"},
            )
        return SpecialistDecision(
            action=SpecialistPolicyAction.COMPLETE,
            task_id=context.task.task_id,
            authority_key=context.task.authority_key,
            reason="The requested Data artifact is available.",
        )


class InventoryHandler:
    """Return a canonical Data Agent handoff for a registered inventory action."""

    def __init__(self, *, actor: str = "Data Agent") -> None:
        self.actor = actor
        self.calls = 0

    async def run(
        self,
        *,
        context: SpecialistPolicyContext,
        decision: SpecialistDecision,
    ) -> SpecialistActionOutcome:
        del decision
        self.calls += 1
        handoff = SpecialistHandoff(
            handoff_id="handoff_dataset_demo",
            domain_owner="Data",
            producer_tool="data_get_inventory",
            requested_by=context.task.requested_by,
            actor=self.actor,
            artifact_type=DATASET_MANIFEST,
            artifact_uri=research_artifact_uri(
                DATASET_MANIFEST,
                "dataset_manifest_demo",
            ),
            source_request=context.task.specialist_input,
            provenance_refs={"task_id": context.task.task_id},
        )
        return SpecialistActionOutcome(
            action_id="inspect_market_data_inventory",
            action_version="1",
            status=SpecialistActionStatus.SUCCEEDED,
            outputs={"manifest": (handoff,)},
        )


class StaticPolicy:
    """Return the same supplied decision for each policy call."""

    def __init__(self, decision: SpecialistDecision | Mapping[str, Any]) -> None:
        self.decision = decision
        self.calls = 0

    async def decide(
        self,
        context: SpecialistPolicyContext,
    ) -> SpecialistDecision | Mapping[str, Any]:
        del context
        self.calls += 1
        return self.decision


class EmptyActionHandler:
    """Return a successful action outcome without producing an artifact."""

    def __init__(self) -> None:
        self.calls = 0

    async def run(
        self,
        *,
        context: SpecialistPolicyContext,
        decision: SpecialistDecision,
    ) -> SpecialistActionOutcome:
        del context, decision
        self.calls += 1
        return SpecialistActionOutcome(
            action_id="inspect_without_output",
            action_version="1",
            status=SpecialistActionStatus.SUCCEEDED,
        )


def test_specialist_task_and_result_round_trip_strict_json() -> None:
    task = _task()

    assert SpecialistTask.from_dict(task.to_dict()).to_dict() == task.to_dict()
    json.dumps(task.to_dict())

    payload = task.to_dict()
    payload["tool_name"] = "place_order"
    with pytest.raises(ValueError, match="unknown fields: tool_name"):
        SpecialistTask.from_dict(payload)

    with pytest.raises(ValueError, match="non-JSON value"):
        SpecialistTask(
            **{
                **_task_kwargs(),
                "specialist_input": {"unsafe": object()},
            }
        )


def test_specialist_task_rejects_wrong_artifact_authority() -> None:
    with pytest.raises(ValueError, match="cannot produce artifacts"):
        SpecialistTask(
            **{
                **_task_kwargs(),
                "requested_outputs": (
                    _empty_slot(
                        "protocol",
                        EXPERIMENT_PROTOCOL,
                        "Experiments",
                    ),
                ),
            }
        )

    with pytest.raises(ValueError, match="approved research objective"):
        SpecialistTask(
            **{
                **_task_kwargs(),
                "objective": ResearchObjective(
                    objective_id="research_objective_draft",
                    statement="Inspect bounded AAPL market data.",
                    success_criteria=("Return a canonical dataset manifest.",),
                    requested_by="operator_demo",
                    actor="operator_demo",
                ),
            }
        )


def test_registered_data_action_completes_through_shared_shell() -> None:
    handler = InventoryHandler()
    graph = build_specialist_graph(
        catalog=_inventory_catalog(handler),
        policy=InventoryPolicy(),
    )

    output = asyncio.run(graph.ainvoke(build_specialist_initial_state(_task())))
    result = SpecialistResult.from_dict(output["result"])
    public = specialist_public_state(output)

    assert handler.calls == 1
    assert output["status"] == "completed"
    assert output["public_status"] == "completed"
    assert output["decision_count"] == 2
    assert result.status is SpecialistResultStatus.COMPLETED
    assert result.actor == "Data Agent"
    assert result.output_bindings == {"requested_manifest": ("handoff_dataset_demo",)}
    assert result.handoffs[0].producer_tool == "data_get_inventory"
    assert output["action_summaries"] == [
        {
            "action_id": "inspect_market_data_inventory",
            "action_version": "1",
            "status": "succeeded",
            "handoff_ids": ["handoff_dataset_demo"],
            "warnings": [],
            "blockers": [],
            "errors": [],
        }
    ]
    assert "next_route" not in public
    serialized = json.dumps(public)
    for forbidden in ("structuredContent", "scratchpad", "prompt", "tool_arguments"):
        assert forbidden not in serialized


def test_specialist_rejects_action_summary_that_conflicts_with_accepted_digest() -> (
    None
):
    handler = InventoryHandler()
    graph = build_specialist_graph(
        catalog=_inventory_catalog(handler),
        policy=InventoryPolicy(),
    )
    completed = asyncio.run(graph.ainvoke(build_specialist_initial_state(_task())))
    forged = dict(completed)
    forged["action_summaries"] = [
        {
            **completed["action_summaries"][0],
            "handoff_ids": ["forged_handoff"],
        }
    ]

    output = asyncio.run(graph.ainvoke(forged))

    assert output["status"] == "failed"
    assert output["errors"][0]["code"] == "invalid_specialist_state"
    assert "conflicts with its accepted digest" in output["errors"][0]["message"]
    assert handler.calls == 1


def test_unregistered_action_fails_before_handler_execution() -> None:
    handler = InventoryHandler()
    policy = StaticPolicy(
        SpecialistDecision(
            action=SpecialistPolicyAction.RUN_REGISTERED_ACTION,
            task_id="specialist_task_demo",
            authority_key="data_agent",
            reason="Try an invented action.",
            action_id="invented_research_action",
            action_version="1",
        )
    )
    graph = build_specialist_graph(
        catalog=_inventory_catalog(handler),
        policy=policy,
    )

    output = asyncio.run(graph.ainvoke(build_specialist_initial_state(_task())))

    assert output["status"] == "failed"
    assert output["errors"][0]["code"] == "invalid_registered_action"
    assert "not registered" in output["errors"][0]["message"]
    assert handler.calls == 0


def test_action_policy_gate_and_side_effect_are_enforced_before_execution() -> None:
    handler = InventoryHandler()
    capability = _inventory_capability(
        side_effect=CapabilitySideEffect.LOCAL_MUTATING,
        policy_gates=("allow_data_loading",),
    )
    catalog = SpecialistActionCatalog(
        authority_key="data_agent",
        actions=(RegisteredSpecialistAction(capability, handler),),
    )
    graph = build_specialist_graph(catalog=catalog, policy=InventoryPolicy())

    output = asyncio.run(graph.ainvoke(build_specialist_initial_state(_task())))

    assert output["status"] == "failed"
    assert "does not permit local_mutating" in output["errors"][0]["message"]
    assert handler.calls == 0

    gated_task = SpecialistTask(
        **{
            **_task_kwargs(),
            "permitted_side_effects": (
                CapabilitySideEffect.READ_ONLY,
                CapabilitySideEffect.LOCAL_MUTATING,
            ),
        }
    )
    gated_output = asyncio.run(
        graph.ainvoke(build_specialist_initial_state(gated_task))
    )

    assert gated_output["status"] == "failed"
    assert "unapproved policy gates" in gated_output["errors"][0]["message"]
    assert handler.calls == 0


def test_action_rejects_unavailable_canonical_input_before_execution() -> None:
    handler = InventoryHandler()
    capability = CapabilityDefinition(
        capability_id="inspect_market_data_inventory",
        version="1",
        description="Inspect a bounded market-data inventory.",
        domain_owner="Data",
        producer_tool="data_get_inventory",
        side_effect=CapabilitySideEffect.READ_ONLY,
        input_slots=(_empty_slot("quality", DATA_QUALITY_REPORT, "Data"),),
        output_slots=(_empty_slot("manifest", DATASET_MANIFEST, "Data"),),
    )
    catalog = SpecialistActionCatalog(
        authority_key="data_agent",
        actions=(RegisteredSpecialistAction(capability, handler),),
    )
    policy = StaticPolicy(
        SpecialistDecision(
            action=SpecialistPolicyAction.RUN_REGISTERED_ACTION,
            task_id="specialist_task_demo",
            authority_key="data_agent",
            reason="Use a ref that was not supplied.",
            action_id="inspect_market_data_inventory",
            action_version="1",
            input_bindings={
                "quality": (
                    research_artifact_uri(
                        DATA_QUALITY_REPORT,
                        "data_quality_report_missing",
                    ),
                )
            },
            output_bindings={"manifest": "requested_manifest"},
        )
    )
    graph = build_specialist_graph(catalog=catalog, policy=policy)

    output = asyncio.run(graph.ainvoke(build_specialist_initial_state(_task())))

    assert output["status"] == "failed"
    assert "input is not available" in output["errors"][0]["message"]
    assert handler.calls == 0


def test_forged_handoff_actor_fails_closed() -> None:
    handler = InventoryHandler(actor="Research Coordinator")
    graph = build_specialist_graph(
        catalog=_inventory_catalog(handler),
        policy=InventoryPolicy(),
    )

    output = asyncio.run(graph.ainvoke(build_specialist_initial_state(_task())))

    assert output["status"] == "failed"
    assert output["errors"][0]["code"] == "invalid_specialist_action_outcome"
    assert "wrong actor" in output["errors"][0]["message"]
    assert handler.calls == 1


def test_forged_specialist_identity_fails_before_policy_or_action() -> None:
    handler = InventoryHandler()
    policy = InventoryPolicy()
    state = build_specialist_initial_state(_task())
    state["identity"] = {
        **state["identity"],
        "display_name": "Research Coordinator",
    }
    graph = build_specialist_graph(
        catalog=_inventory_catalog(handler),
        policy=policy,
    )

    output = asyncio.run(graph.ainvoke(state))

    assert output["status"] == "failed"
    assert output["errors"][0]["code"] == "invalid_specialist_state"
    assert handler.calls == 0


def test_specialist_can_request_a_prerequisite_without_calling_an_action() -> None:
    handler = InventoryHandler()
    prerequisite = Prerequisite(
        prerequisite_id="prerequisite_dataset_scope",
        kind=PrerequisiteKind.ARTIFACT,
        target=DATASET_MANIFEST,
        description="A bounded dataset scope is required.",
    )
    policy = StaticPolicy(
        SpecialistDecision(
            action=SpecialistPolicyAction.REQUEST_PREREQUISITE,
            task_id="specialist_task_demo",
            authority_key="data_agent",
            reason="The Data scope is incomplete.",
            prerequisites=(prerequisite,),
        )
    )
    graph = build_specialist_graph(
        catalog=_inventory_catalog(handler),
        policy=policy,
    )

    output = asyncio.run(graph.ainvoke(build_specialist_initial_state(_task())))
    result = SpecialistResult.from_dict(output["result"])

    assert output["status"] == "blocked"
    assert output["public_status"] == "awaiting_prerequisite"
    assert result.status is SpecialistResultStatus.AWAITING_PREREQUISITE
    assert result.prerequisites == (prerequisite,)
    assert handler.calls == 0


def test_specialist_can_return_a_domain_blocker_without_calling_an_action() -> None:
    handler = InventoryHandler()
    blocker = ResearchIssue(
        code="unsupported_market_scope",
        message="The requested market scope is not supported.",
    )
    policy = StaticPolicy(
        SpecialistDecision(
            action=SpecialistPolicyAction.BLOCK,
            task_id="specialist_task_demo",
            authority_key="data_agent",
            reason="The requested scope cannot be inspected safely.",
            blockers=(blocker,),
        )
    )
    graph = build_specialist_graph(
        catalog=_inventory_catalog(handler),
        policy=policy,
    )

    output = asyncio.run(graph.ainvoke(build_specialist_initial_state(_task())))
    result = SpecialistResult.from_dict(output["result"])

    assert output["status"] == "blocked"
    assert result.status is SpecialistResultStatus.BLOCKED
    assert result.blockers == (blocker,)
    assert handler.calls == 0


def test_specialist_policy_loop_budget_fails_closed() -> None:
    handler = EmptyActionHandler()
    capability = CapabilityDefinition(
        capability_id="inspect_without_output",
        version="1",
        description="Inspect bounded state without producing an artifact.",
        domain_owner="Data",
        producer_tool="data_get_inventory",
        side_effect=CapabilitySideEffect.READ_ONLY,
        input_slots=(),
        output_slots=(),
    )
    catalog = SpecialistActionCatalog(
        authority_key="data_agent",
        actions=(RegisteredSpecialistAction(capability, handler),),
    )
    policy = StaticPolicy(
        SpecialistDecision(
            action=SpecialistPolicyAction.RUN_REGISTERED_ACTION,
            task_id="specialist_task_demo",
            authority_key="data_agent",
            reason="Repeat the bounded inspection.",
            action_id="inspect_without_output",
            action_version="1",
        )
    )
    graph = build_specialist_graph(
        catalog=catalog,
        policy=policy,
        max_policy_decisions=2,
        max_action_attempts=4,
    )

    output = asyncio.run(graph.ainvoke(build_specialist_initial_state(_task())))

    assert output["status"] == "failed"
    assert output["errors"][0]["code"] == "specialist_policy_loop_limit_exceeded"
    assert handler.calls == 2
    assert policy.calls == 2


def test_policy_mapping_rejects_tool_and_argument_injection() -> None:
    handler = InventoryHandler()
    policy = StaticPolicy(
        {
            "action": "run_registered_action",
            "task_id": "specialist_task_demo",
            "authority_key": "data_agent",
            "reason": "Attempt to bypass the registered action.",
            "action_id": "inspect_market_data_inventory",
            "action_version": "1",
            "input_bindings": {},
            "output_bindings": {"manifest": "requested_manifest"},
            "prerequisites": [],
            "blockers": [],
            "tool_name": "place_order",
            "arguments": {"symbol": "AAPL"},
        }
    )
    graph = build_specialist_graph(
        catalog=_inventory_catalog(handler),
        policy=policy,
    )

    output = asyncio.run(graph.ainvoke(build_specialist_initial_state(_task())))

    assert output["status"] == "failed"
    assert output["errors"][0]["code"] == "invalid_specialist_decision"
    assert "arguments, tool_name" in output["errors"][0]["message"]
    assert handler.calls == 0


def test_specialist_catalog_rejects_action_outside_authority_domain() -> None:
    handler = InventoryHandler()
    capability = CapabilityDefinition(
        capability_id="author_experiment_protocol",
        version="1",
        description="Attempt to produce an Experiment artifact as Data Agent.",
        domain_owner="Experiments",
        producer_tool="research_register_experiment_protocol",
        side_effect=CapabilitySideEffect.LOCAL_MUTATING,
        input_slots=(),
        output_slots=(_empty_slot("protocol", EXPERIMENT_PROTOCOL, "Experiments"),),
    )

    with pytest.raises(ValueError, match="cannot register an action"):
        SpecialistActionCatalog(
            authority_key="data_agent",
            actions=(RegisteredSpecialistAction(capability, handler),),
        )


def test_specialist_catalog_requires_injected_configuration_and_idempotency() -> None:
    handler = InventoryHandler()
    configured = CapabilityDefinition.from_dict(
        {
            **_inventory_capability().to_dict(),
            "configuration_keys": ["data_reader"],
        }
    )

    with pytest.raises(ValueError, match="unavailable configuration: data_reader"):
        SpecialistActionCatalog(
            authority_key="data_agent",
            actions=(RegisteredSpecialistAction(configured, handler),),
        )

    catalog = SpecialistActionCatalog(
        authority_key="data_agent",
        actions=(RegisteredSpecialistAction(configured, handler),),
        available_configuration_keys=("data_reader",),
    )
    assert catalog.capabilities == (configured,)

    non_idempotent = CapabilityDefinition.from_dict(
        {
            **_inventory_capability().to_dict(),
            "idempotent": False,
        }
    )
    with pytest.raises(ValueError, match="must be idempotent"):
        SpecialistActionCatalog(
            authority_key="data_agent",
            actions=(RegisteredSpecialistAction(non_idempotent, handler),),
        )


def test_specialist_result_rejects_unbound_handoff() -> None:
    handoff = SpecialistHandoff(
        handoff_id="handoff_dataset_demo",
        domain_owner="Data",
        producer_tool="data_get_inventory",
        requested_by="workflow_demo",
        actor="Data Agent",
        artifact_type=DATASET_MANIFEST,
        artifact_uri=research_artifact_uri(
            DATASET_MANIFEST,
            "dataset_manifest_demo",
        ),
    )

    with pytest.raises(ValueError, match="cover every handoff"):
        SpecialistResult(
            task_id="specialist_task_demo",
            authority_key="data_agent",
            status=SpecialistResultStatus.COMPLETED,
            requested_by="workflow_demo",
            actor="Data Agent",
            handoffs=(handoff,),
        )


def _task() -> SpecialistTask:
    return SpecialistTask(**_task_kwargs())


def _task_kwargs() -> dict[str, Any]:
    return {
        "task_id": "specialist_task_demo",
        "authority_key": "data_agent",
        "objective": ResearchObjective(
            objective_id="research_objective_demo",
            statement="Inspect bounded AAPL market data.",
            success_criteria=("Return a canonical dataset manifest.",),
            requested_by="operator_demo",
            actor="operator_demo",
            status=ResearchObjectiveStatus.APPROVED,
        ),
        "requested_outputs": (
            _empty_slot(
                "requested_manifest",
                DATASET_MANIFEST,
                "Data",
            ),
        ),
        "input_refs": (),
        "requested_by": "workflow_demo",
        "actor": "Research Coordinator",
        "specialist_input": {
            "symbols": ["AAPL"],
            "timeframe": "1Min",
            "start": "2025-01-01T00:00:00Z",
            "end": "2025-01-02T00:00:00Z",
        },
    }


def _inventory_catalog(handler: InventoryHandler) -> SpecialistActionCatalog:
    return SpecialistActionCatalog(
        authority_key="data_agent",
        actions=(
            RegisteredSpecialistAction(
                capability=_inventory_capability(),
                handler=handler,
            ),
        ),
    )


def _inventory_capability(
    *,
    side_effect: CapabilitySideEffect = CapabilitySideEffect.READ_ONLY,
    policy_gates: tuple[str, ...] = (),
) -> CapabilityDefinition:
    return CapabilityDefinition(
        capability_id="inspect_market_data_inventory",
        version="1",
        description="Inspect a bounded market-data inventory.",
        domain_owner="Data",
        producer_tool="data_get_inventory",
        side_effect=side_effect,
        input_slots=(),
        output_slots=(_empty_slot("manifest", DATASET_MANIFEST, "Data"),),
        policy_gates=policy_gates,
    )


def _empty_slot(
    slot_id: str,
    artifact_type: str,
    domain_owner: str,
) -> ArtifactSlot:
    return ArtifactSlot(
        slot_id=slot_id,
        artifact_type=artifact_type,
        domain_owner=domain_owner,
        cardinality=ArtifactCardinality.EXACTLY_ONE,
        required=True,
        status=ArtifactSlotStatus.EMPTY,
    )
