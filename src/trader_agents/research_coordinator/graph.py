"""Expose bounded Research Coordinator policy through a thin LangGraph graph.

The graph normalizes JSON-compatible objective, protocol, and outcome payloads
into immutable contracts before invoking the deterministic policy. It publishes
only the bounded decision and compiler-produced workflow plan; it calls no MCP
tools, persists no artifacts, and stores no hidden model reasoning.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Literal, TypedDict

from langgraph.graph import END, START, StateGraph

from trader_research.foundation import ResearchArtifactStore
from trader_research.governance import (
    ExperimentProtocol,
    ResearchIssue,
    ResearchObjective,
    WorkflowOutcome,
    get_decision_authority,
)
from trader_agents.specialists import (
    AcceptedSpecialistResult,
    SpecialistRouteCatalog,
    SpecialistTask,
)

from .catalog import WorkflowTemplateCatalog
from .domain import CoordinatorAction
from .policy import coordinate_research


CoordinatorGraphStatus = Literal["ready", "completed", "blocked", "failed"]
"""Lifecycle values exposed by the Research Coordinator graph."""


class ResearchCoordinatorState(TypedDict, total=False):
    """JSON-safe state for one bounded coordination decision.

    Attributes:
        identity: Stable Research Coordinator authority metadata.
        objective: Validated research-objective payload.
        protocol: Optional validated experiment-protocol payload.
        workflow_outcome: Optional canonical terminal-outcome payload.
        specialist_tasks: Ordered explicit specialist task payloads.
        accepted_specialist_results: Validated completed-task receipts.
        decision: Bounded next action selected by policy.
        workflow_plan: Compiler-produced ready plan when execution is permitted.
        status: Graph lifecycle status.
        public_status: Operator-facing bounded status.
        prerequisites: Typed unresolved prerequisite payloads.
        blockers: Structured issues preventing progression.
        errors: Boundary-validation failures.
    """

    identity: dict[str, Any]
    objective: dict[str, Any]
    protocol: dict[str, Any]
    workflow_outcome: dict[str, Any]
    specialist_tasks: list[dict[str, Any]]
    accepted_specialist_results: list[dict[str, Any]]
    decision: dict[str, Any]
    workflow_plan: dict[str, Any]
    status: CoordinatorGraphStatus
    public_status: str
    prerequisites: list[dict[str, Any]]
    blockers: list[dict[str, Any]]
    errors: list[dict[str, Any]]


def build_research_coordinator_initial_state(
    *,
    objective: ResearchObjective,
    protocol: ExperimentProtocol | None = None,
    outcome: WorkflowOutcome | None = None,
    specialist_tasks: Sequence[SpecialistTask] = (),
    accepted_specialist_results: Sequence[AcceptedSpecialistResult] = (),
) -> ResearchCoordinatorState:
    """Build validated JSON-safe input state for the coordinator graph.

    Args:
        objective: Research objective to coordinate.
        protocol: Optional experiment protocol for the objective.
        outcome: Optional canonical terminal workflow outcome to report.
        specialist_tasks: Ordered caller-built specialist tasks to consider.
        accepted_specialist_results: Previously validated completed-task receipts.

    Returns:
        Initial graph state containing only public governance contracts.
    """
    authority = get_decision_authority("research_coordinator")
    return {
        "identity": {
            "authority_key": authority.key,
            "display_name": authority.display_name,
            "decision": authority.decision,
            "artifact_domains": list(authority.artifact_domains),
            "prohibited_authority": list(authority.prohibited_authority),
        },
        "objective": objective.to_dict(),
        "protocol": protocol.to_dict() if protocol is not None else {},
        "workflow_outcome": outcome.to_dict() if outcome is not None else {},
        "specialist_tasks": [task.to_dict() for task in specialist_tasks],
        "accepted_specialist_results": [
            result.to_dict() for result in accepted_specialist_results
        ],
        "decision": {},
        "workflow_plan": {},
        "status": "ready",
        "public_status": "ready",
        "prerequisites": [],
        "blockers": [],
        "errors": [],
    }


def build_research_coordinator_graph(
    *,
    artifact_store: ResearchArtifactStore,
    catalog: WorkflowTemplateCatalog | None = None,
    specialist_catalog: SpecialistRouteCatalog | None = None,
) -> Any:
    """Build a one-decision Research Coordinator graph.

    The injected artifact store is read only by the selected deterministic
    compiler. The graph neither invokes the workflow executor nor calls MCP
    tools; callers may pass the returned plan through the existing execution
    boundary after inspecting the public decision.

    Args:
        artifact_store: Canonical artifact reader used for template readiness.
        catalog: Optional injected code-owned template catalog.
        specialist_catalog: Optional injected code-owned specialist routes.

    Returns:
        Compiled LangGraph that emits one bounded coordination decision.
    """

    async def select_action(
        state: ResearchCoordinatorState,
    ) -> ResearchCoordinatorState:
        return _select_action(
            state,
            artifact_store=artifact_store,
            catalog=catalog,
            specialist_catalog=specialist_catalog,
        )

    graph = StateGraph(ResearchCoordinatorState)
    graph.add_node("select_research_action", select_action)
    graph.add_edge(START, "select_research_action")
    graph.add_edge("select_research_action", END)
    return graph.compile()


def _select_action(
    state: ResearchCoordinatorState,
    *,
    artifact_store: ResearchArtifactStore,
    catalog: WorkflowTemplateCatalog | None,
    specialist_catalog: SpecialistRouteCatalog | None,
) -> ResearchCoordinatorState:
    identity = _mapping(state.get("identity"))
    authority = get_decision_authority("research_coordinator")
    if (
        identity.get("authority_key") != authority.key
        or identity.get("display_name") != authority.display_name
    ):
        return _failed_state(
            state,
            code="unexpected_coordinator_identity",
            message="State identity is not the registered Research Coordinator.",
        )
    try:
        objective = ResearchObjective.from_dict(_mapping(state.get("objective")))
        protocol_payload = _mapping(state.get("protocol"))
        protocol = (
            ExperimentProtocol.from_dict(protocol_payload) if protocol_payload else None
        )
        outcome_payload = _mapping(state.get("workflow_outcome"))
        outcome = (
            WorkflowOutcome.from_dict(outcome_payload) if outcome_payload else None
        )
        specialist_tasks = tuple(
            SpecialistTask.from_dict(item)
            for item in _strict_mapping_sequence(
                state.get("specialist_tasks"),
                "specialist_tasks",
            )
        )
        accepted_specialist_results = tuple(
            AcceptedSpecialistResult.from_dict(item)
            for item in _strict_mapping_sequence(
                state.get("accepted_specialist_results"),
                "accepted_specialist_results",
            )
        )
        result = coordinate_research(
            objective=objective,
            protocol=protocol,
            outcome=outcome,
            artifact_store=artifact_store,
            catalog=catalog,
            specialist_tasks=specialist_tasks,
            accepted_specialist_results=accepted_specialist_results,
            specialist_catalog=specialist_catalog,
        )
    except (TypeError, ValueError) as exc:
        return _failed_state(
            state,
            code="invalid_coordination_input",
            message=str(exc),
        )
    decision = result.decision
    graph_status, public_status = _public_status(decision.action)
    workflow_plan = (
        result.compiled_workflow.plan.to_dict()
        if result.compiled_workflow is not None
        else {}
    )
    return {
        "objective": objective.to_dict(),
        "protocol": protocol.to_dict() if protocol is not None else {},
        "workflow_outcome": outcome.to_dict() if outcome is not None else {},
        "specialist_tasks": [task.to_dict() for task in specialist_tasks],
        "accepted_specialist_results": [
            item.to_dict() for item in accepted_specialist_results
        ],
        "decision": decision.to_dict(),
        "workflow_plan": workflow_plan,
        "status": graph_status,
        "public_status": public_status,
        "prerequisites": [item.to_dict() for item in decision.prerequisites],
        "blockers": [item.to_dict() for item in decision.blockers],
        "errors": [],
    }


def _public_status(
    action: CoordinatorAction,
) -> tuple[CoordinatorGraphStatus, str]:
    if action is CoordinatorAction.EXECUTE_REGISTERED_SPECIALIST_TASK:
        return "completed", "ready_for_specialist_execution"
    if action is CoordinatorAction.EXECUTE_REGISTERED_WORKFLOW:
        return "completed", "ready_for_execution"
    if action is CoordinatorAction.REPORT_TERMINAL_STATE:
        return "completed", "terminal_state_reported"
    if action is CoordinatorAction.REQUEST_APPROVAL:
        return "blocked", "awaiting_approval"
    if action is CoordinatorAction.REQUEST_PREREQUISITE:
        return "blocked", "awaiting_prerequisite"
    return "blocked", "blocked"


def _failed_state(
    state: ResearchCoordinatorState,
    *,
    code: str,
    message: str,
) -> ResearchCoordinatorState:
    issue = ResearchIssue(code=code, message=message)
    return {
        "objective": dict(_mapping(state.get("objective"))),
        "protocol": dict(_mapping(state.get("protocol"))),
        "workflow_outcome": dict(_mapping(state.get("workflow_outcome"))),
        "specialist_tasks": [
            dict(item) for item in _mapping_sequence(state.get("specialist_tasks"))
        ],
        "accepted_specialist_results": [
            dict(item)
            for item in _mapping_sequence(state.get("accepted_specialist_results"))
        ],
        "decision": {},
        "workflow_plan": {},
        "status": "failed",
        "public_status": "failed_validation",
        "prerequisites": [],
        "blockers": [],
        "errors": [issue.to_dict()],
    }


def _mapping(value: object) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return {}


def _mapping_sequence(value: object) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()
    return tuple(item for item in value if isinstance(item, Mapping))


def _strict_mapping_sequence(
    value: object,
    label: str,
) -> tuple[Mapping[str, Any], ...]:
    if value is None:
        return ()
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{label} must be a sequence of mappings")
    if any(not isinstance(item, Mapping) for item in value):
        raise ValueError(f"{label} must contain only mappings")
    return tuple(item for item in value if isinstance(item, Mapping))
