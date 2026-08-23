"""Build strict tasks for the Experiment Design specialist.

The task boundary carries one complete structured design request and exact
canonical input refs. It contains no tool name, approval decision, transport
payload, model prompt, or executable workflow arguments.
"""

from __future__ import annotations

from trader_research.foundation import EXPERIMENTS_DOMAIN_OWNER, stable_research_id
from trader_research.governance import (
    EXPERIMENT_PROTOCOL_PROPOSAL,
    ArtifactCardinality,
    ArtifactSlot,
    CapabilitySideEffect,
    ExperimentDesignRequest,
    ResearchObjective,
    ResearchObjectiveStatus,
    experiment_design_input_refs,
)

from trader_agents.specialists import SpecialistTask


EXPERIMENT_DESIGN_AUTHORITY = "experiment_design_agent"
"""Registered decision authority used by the Experiment Design specialist."""

EXPERIMENT_PROTOCOL_PROPOSAL_TASK_SLOT = "experiment_protocol_proposal"
"""Task output slot containing one immutable protocol proposal."""


def build_experiment_design_task(
    *,
    request: ExperimentDesignRequest,
    objective: ResearchObjective,
    requested_by: str,
    actor: str,
    permit_local_mutation: bool,
) -> SpecialistTask:
    """Build one stable specialist task over an explicit experiment design.

    Args:
        request: Complete structured protocol-design request.
        objective: Approved objective supplying the implementation refs.
        requested_by: Composition or workflow requiring the proposal.
        actor: Coordinator identity routing the task.
        permit_local_mutation: Whether proposal persistence is permitted.

    Returns:
        Stable generic specialist task requesting exactly one proposal artifact.

    Raises:
        ValueError: If objective status, identity, or mutation permission shape is
            invalid, or required implementations are outside objective scope.
    """
    if objective.status is not ResearchObjectiveStatus.APPROVED:
        raise ValueError("Experiment Design tasks require an approved objective")
    if not isinstance(permit_local_mutation, bool):
        raise ValueError("permit_local_mutation must be a boolean")
    normalized_requester = _required_text(requested_by, "requested_by")
    normalized_actor = _required_text(actor, "actor")
    supplied = {item.uri for item in objective.supplied_artifact_refs}
    required_implementations = {
        request.strategy.implementation_ref.uri,
        *(item.implementation_ref.uri for item in request.risk_managers),
    }
    missing = sorted(required_implementations.difference(supplied))
    if missing:
        raise ValueError(
            "Experiment Design implementations are not supplied by the objective: "
            + ", ".join(missing)
        )
    side_effects = [CapabilitySideEffect.READ_ONLY]
    if permit_local_mutation:
        side_effects.append(CapabilitySideEffect.LOCAL_MUTATING)
    identity = {
        "objective_id": objective.objective_id,
        "design_request": request.to_dict(),
        "requested_by": normalized_requester,
        "actor": normalized_actor,
        "permit_local_mutation": permit_local_mutation,
    }
    return SpecialistTask(
        task_id=stable_research_id("experiment_design_task", identity),
        authority_key=EXPERIMENT_DESIGN_AUTHORITY,
        objective=objective,
        requested_outputs=(
            ArtifactSlot(
                slot_id=EXPERIMENT_PROTOCOL_PROPOSAL_TASK_SLOT,
                artifact_type=EXPERIMENT_PROTOCOL_PROPOSAL,
                domain_owner=EXPERIMENTS_DOMAIN_OWNER,
                cardinality=ArtifactCardinality.EXACTLY_ONE,
                required=True,
            ),
        ),
        input_refs=experiment_design_input_refs(request),
        requested_by=normalized_requester,
        actor=normalized_actor,
        permitted_side_effects=tuple(side_effects),
        specialist_input=request.to_dict(),
    )


def experiment_design_request_from_task(
    task: SpecialistTask,
) -> ExperimentDesignRequest:
    """Parse and revalidate the role-specific request held by a Design task."""
    if task.authority_key != EXPERIMENT_DESIGN_AUTHORITY:
        raise ValueError("specialist task is not addressed to Experiment Design")
    if len(task.requested_outputs) != 1:
        raise ValueError("Experiment Design tasks require one proposal output")
    output = task.requested_outputs[0]
    if (
        output.slot_id != EXPERIMENT_PROTOCOL_PROPOSAL_TASK_SLOT
        or output.artifact_type != EXPERIMENT_PROTOCOL_PROPOSAL
        or output.domain_owner != EXPERIMENTS_DOMAIN_OWNER
        or output.cardinality is not ArtifactCardinality.EXACTLY_ONE
        or not output.required
    ):
        raise ValueError("Experiment Design task proposal output is invalid")
    if task.approved_policy_gates:
        raise ValueError("Experiment Design task contains unknown policy gates")
    request = ExperimentDesignRequest.from_dict(task.specialist_input)
    if {item.uri for item in task.input_refs} != {
        item.uri for item in experiment_design_input_refs(request)
    }:
        raise ValueError("Experiment Design task input refs do not match request")
    return request


def _required_text(value: object, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{label} is required")
    return text
