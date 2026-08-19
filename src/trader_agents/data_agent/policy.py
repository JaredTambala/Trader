"""Select deterministic registered actions for the Data specialist.

The policy reasons only over a normalized Data request and bounded action
summaries. MCP tool selection and argument construction belong to registered
handlers and are deliberately absent from policy decisions.
"""

from __future__ import annotations

from trader_research.governance import (
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
    ALLOW_SAMPLE_DATA_LOADING_GATE,
    DATASET_MANIFEST_TASK_SLOT,
    DATA_QUALITY_REPORT_TASK_SLOT,
    data_request_from_task,
)


VALIDATE_MARKET_DATA_SCOPE_ACTION = "validate_market_data_scope"
"""Registered action that validates provider-scoped symbol availability."""

ENSURE_MARKET_DATA_AVAILABLE_ACTION = "ensure_market_data_available"
"""Registered action that performs an approved idempotent sample load."""

CAPTURE_MARKET_DATA_EVIDENCE_ACTION = "capture_market_data_evidence"
"""Registered action that creates and verifies canonical Data evidence."""

DATA_SPECIALIST_ACTION_VERSION = "1"
"""Current immutable version for the Data specialist action registrations."""


class DataSpecialistPolicy:
    """Deterministically advance one Data task through its registered actions."""

    async def decide(
        self,
        context: SpecialistPolicyContext,
    ) -> SpecialistDecision:
        """Return the next closed action, prerequisite request, or completion."""
        request = data_request_from_task(context.task)
        prerequisite = _missing_permission(
            context, loading_requested=request.loading_intent is not None
        )
        if prerequisite is not None:
            return SpecialistDecision(
                action=SpecialistPolicyAction.REQUEST_PREREQUISITE,
                task_id=context.task.task_id,
                authority_key=context.task.authority_key,
                reason=prerequisite.description,
                prerequisites=(prerequisite,),
            )

        completed_actions = tuple(
            summary.action_id for summary in context.action_summaries
        )
        _validate_action_history(
            completed_actions,
            loading_requested=request.loading_intent is not None,
        )
        if VALIDATE_MARKET_DATA_SCOPE_ACTION not in completed_actions:
            return _run_action(
                context,
                action_id=VALIDATE_MARKET_DATA_SCOPE_ACTION,
                reason="Validate the explicit symbols and provider context.",
            )
        if (
            request.loading_intent is not None
            and ENSURE_MARKET_DATA_AVAILABLE_ACTION not in completed_actions
        ):
            return _run_action(
                context,
                action_id=ENSURE_MARKET_DATA_AVAILABLE_ACTION,
                reason="Load the explicitly approved idempotent sample dataset.",
            )
        if CAPTURE_MARKET_DATA_EVIDENCE_ACTION not in completed_actions:
            return _run_action(
                context,
                action_id=CAPTURE_MARKET_DATA_EVIDENCE_ACTION,
                reason="Persist and verify the final market-data evidence.",
                output_bindings={
                    "manifest": DATASET_MANIFEST_TASK_SLOT,
                    "quality": DATA_QUALITY_REPORT_TASK_SLOT,
                },
            )
        return SpecialistDecision(
            action=SpecialistPolicyAction.COMPLETE,
            task_id=context.task.task_id,
            authority_key=context.task.authority_key,
            reason="Canonical market-data scope and quality evidence are available.",
        )


def _missing_permission(
    context: SpecialistPolicyContext,
    *,
    loading_requested: bool,
) -> Prerequisite | None:
    task = context.task
    if CapabilitySideEffect.LOCAL_MUTATING not in task.permitted_side_effects:
        return Prerequisite(
            prerequisite_id="permit_data_evidence_persistence",
            kind=PrerequisiteKind.POLICY_GATE,
            target=CapabilitySideEffect.LOCAL_MUTATING.value,
            description=(
                "Local mutation permission is required to persist canonical "
                "Data evidence."
            ),
        )
    if (
        loading_requested
        and ALLOW_SAMPLE_DATA_LOADING_GATE not in task.approved_policy_gates
    ):
        return Prerequisite(
            prerequisite_id="approve_sample_data_loading",
            kind=PrerequisiteKind.APPROVAL,
            target=ALLOW_SAMPLE_DATA_LOADING_GATE,
            description="Explicit approval is required before sample data loading.",
        )
    return None


def _run_action(
    context: SpecialistPolicyContext,
    *,
    action_id: str,
    reason: str,
    output_bindings: dict[str, str] | None = None,
) -> SpecialistDecision:
    return SpecialistDecision(
        action=SpecialistPolicyAction.RUN_REGISTERED_ACTION,
        task_id=context.task.task_id,
        authority_key=context.task.authority_key,
        reason=reason,
        action_id=action_id,
        action_version=DATA_SPECIALIST_ACTION_VERSION,
        output_bindings=output_bindings or {},
    )


def _validate_action_history(
    action_ids: tuple[str, ...],
    *,
    loading_requested: bool,
) -> None:
    expected = [VALIDATE_MARKET_DATA_SCOPE_ACTION]
    if loading_requested:
        expected.append(ENSURE_MARKET_DATA_AVAILABLE_ACTION)
    expected.append(CAPTURE_MARKET_DATA_EVIDENCE_ACTION)
    if (
        len(action_ids) > len(expected)
        or list(action_ids) != expected[: len(action_ids)]
    ):
        raise SpecialistPolicyError(
            "invalid_data_action_history",
            "Data specialist action history does not match the normalized request.",
        )
