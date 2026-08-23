"""Select the deterministic proposal action for Experiment Design tasks."""

from __future__ import annotations

from trader_research.governance import (
    DATASET_MANIFEST,
    DATA_QUALITY_REPORT,
    IMPLEMENTATION_VALIDATION_REPORT,
    IMPLEMENTATION_VERSION,
    CapabilitySideEffect,
    Prerequisite,
    PrerequisiteKind,
)

from trader_agents.specialists import (
    SpecialistDecision,
    SpecialistPolicyAction,
    SpecialistPolicyContext,
    SpecialistPolicyError,
)

from .domain import (
    EXPERIMENT_PROTOCOL_PROPOSAL_TASK_SLOT,
    experiment_design_request_from_task,
)


CREATE_EXPERIMENT_PROTOCOL_PROPOSAL_ACTION = (
    "create_experiment_protocol_proposal"
)
"""Registered action that persists one immutable protocol proposal."""

EXPERIMENT_DESIGN_ACTION_VERSION = "1"
"""Current immutable version for Experiment Design action registration."""


class ExperimentDesignPolicy:
    """Advance a complete Experiment Design task through one registered action."""

    async def decide(
        self,
        context: SpecialistPolicyContext,
    ) -> SpecialistDecision:
        """Return a persistence prerequisite, proposal action, or completion."""
        experiment_design_request_from_task(context.task)
        if CapabilitySideEffect.LOCAL_MUTATING not in (
            context.task.permitted_side_effects
        ):
            prerequisite = Prerequisite(
                prerequisite_id="permit_protocol_proposal_persistence",
                kind=PrerequisiteKind.POLICY_GATE,
                target=CapabilitySideEffect.LOCAL_MUTATING.value,
                description=(
                    "Local mutation permission is required to persist the "
                    "experiment protocol proposal."
                ),
            )
            return SpecialistDecision(
                action=SpecialistPolicyAction.REQUEST_PREREQUISITE,
                task_id=context.task.task_id,
                authority_key=context.task.authority_key,
                reason=prerequisite.description,
                prerequisites=(prerequisite,),
            )
        completed = tuple(item.action_id for item in context.action_summaries)
        if completed not in ((), (CREATE_EXPERIMENT_PROTOCOL_PROPOSAL_ACTION,)):
            raise SpecialistPolicyError(
                "invalid_experiment_design_action_history",
                "Experiment Design action history does not match its one-action policy.",
            )
        if not completed:
            return SpecialistDecision(
                action=SpecialistPolicyAction.RUN_REGISTERED_ACTION,
                task_id=context.task.task_id,
                authority_key=context.task.authority_key,
                reason="Persist the explicit approval-aware protocol proposal.",
                action_id=CREATE_EXPERIMENT_PROTOCOL_PROPOSAL_ACTION,
                action_version=EXPERIMENT_DESIGN_ACTION_VERSION,
                input_bindings=_input_bindings(context),
                output_bindings={
                    "proposal": EXPERIMENT_PROTOCOL_PROPOSAL_TASK_SLOT
                },
            )
        return SpecialistDecision(
            action=SpecialistPolicyAction.COMPLETE,
            task_id=context.task.task_id,
            authority_key=context.task.authority_key,
            reason="The immutable experiment protocol proposal is available.",
        )


def _input_bindings(
    context: SpecialistPolicyContext,
) -> dict[str, tuple[str, ...]]:
    refs_by_type: dict[str, list[str]] = {}
    for reference in context.available_refs:
        refs_by_type.setdefault(reference.artifact_type, []).append(reference.uri)
    bindings = {
        "implementations": tuple(refs_by_type.get(IMPLEMENTATION_VERSION, ())),
        "dataset_manifests": tuple(refs_by_type.get(DATASET_MANIFEST, ())),
        "data_quality_reports": tuple(
            refs_by_type.get(DATA_QUALITY_REPORT, ())
        ),
    }
    optimization_refs = tuple(
        refs_by_type.get(IMPLEMENTATION_VALIDATION_REPORT, ())
    )
    if optimization_refs:
        bindings["optimization_objective_validation"] = optimization_refs
    return bindings
