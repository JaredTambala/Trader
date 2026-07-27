"""Shared workflow-plan fixtures for checkpoint contract tests."""

from __future__ import annotations

from typing import Any

from trader_research.governance import (
    DATA_QUALITY_REPORT,
    DATASET_MANIFEST,
    EXPERIMENT_PROTOCOL,
    RESEARCH_OBJECTIVE,
    ArtifactCardinality,
    ArtifactSlot,
    CapabilityDefinition,
    CapabilitySideEffect,
    ResearchIssue,
    RetryDisposition,
    WorkflowPlan,
    WorkflowPlanStatus,
    WorkflowStep,
    WorkflowStepResult,
    WorkflowStepStatus,
)
from trader_research.governance.handoffs import artifact_report_ref


def checkpoint_artifact_slot(
    slot_id: str,
    artifact_type: str,
    *,
    required: bool = True,
) -> ArtifactSlot:
    """Build a Data-owned artifact slot for checkpoint tests."""
    return ArtifactSlot(
        slot_id=slot_id,
        artifact_type=artifact_type,
        domain_owner="Data",
        cardinality=ArtifactCardinality.EXACTLY_ONE,
        required=required,
    )


def checkpoint_workflow_plan(
    *,
    quality_threshold: float = 0.99,
) -> WorkflowPlan:
    """Build the deterministic two-step plan used by checkpoint tests."""
    inventory = CapabilityDefinition(
        capability_id="inventory",
        version="1",
        description="Resolve a bounded dataset manifest.",
        domain_owner="Data",
        producer_tool="data_get_inventory",
        side_effect=CapabilitySideEffect.READ_ONLY,
        input_slots=(),
        output_slots=(
            checkpoint_artifact_slot("manifest_output", DATASET_MANIFEST),
        ),
    )
    quality = CapabilityDefinition(
        capability_id="quality",
        version="1",
        description="Summarize bounded dataset quality.",
        domain_owner="Data",
        producer_tool="data_summarize_quality",
        side_effect=CapabilitySideEffect.READ_ONLY,
        input_slots=(
            checkpoint_artifact_slot("manifest_input", DATASET_MANIFEST),
        ),
        output_slots=(
            checkpoint_artifact_slot("quality_output", DATA_QUALITY_REPORT),
        ),
        configuration_keys=("minimum_coverage",),
    )
    return WorkflowPlan(
        plan_id="workflow_plan_demo",
        objective_ref=artifact_report_ref(
            RESEARCH_OBJECTIVE,
            "objective_demo",
        ),
        protocol_ref=artifact_report_ref(
            EXPERIMENT_PROTOCOL,
            "protocol_demo",
        ),
        template_id="checkpoint_contract_test",
        template_version="1",
        capabilities=(inventory, quality),
        artifact_slots=(
            checkpoint_artifact_slot("dataset_manifest", DATASET_MANIFEST),
            checkpoint_artifact_slot("data_quality", DATA_QUALITY_REPORT),
        ),
        prerequisites=(),
        approvals=(),
        steps=(
            WorkflowStep(
                step_id="inventory",
                capability_id=inventory.capability_id,
                output_bindings={"manifest_output": "dataset_manifest"},
            ),
            WorkflowStep(
                step_id="quality",
                capability_id=quality.capability_id,
                depends_on=("inventory",),
                input_bindings={"manifest_input": "dataset_manifest"},
                output_bindings={"quality_output": "data_quality"},
                configuration={"minimum_coverage": quality_threshold},
            ),
        ),
        requested_by="operator_request_demo",
        actor="research_coordinator",
        status=WorkflowPlanStatus.READY,
    )


def checkpoint_step_result(
    *,
    workflow_id: str,
    step_id: str,
    attempt: int = 1,
    status: WorkflowStepStatus = WorkflowStepStatus.SUCCEEDED,
    retry: RetryDisposition = RetryDisposition.NOT_APPLICABLE,
    idempotency_key: str | None = None,
    public_data: dict[str, Any] | None = None,
) -> WorkflowStepResult:
    """Build a validated external result for one fixture workflow step."""
    artifact_type = (
        DATASET_MANIFEST if step_id == "inventory" else DATA_QUALITY_REPORT
    )
    command = (
        "data_get_inventory"
        if step_id == "inventory"
        else "data_summarize_quality"
    )
    blockers = (
        (
            ResearchIssue(
                code="temporary_failure",
                message="Temporary provider failure.",
            ),
        )
        if status is not WorkflowStepStatus.SUCCEEDED
        else ()
    )
    return WorkflowStepResult(
        result_id=f"result_{step_id}_{attempt}",
        plan_id="workflow_plan_demo",
        step_id=step_id,
        attempt=attempt,
        command=command,
        side_effect=CapabilitySideEffect.READ_ONLY,
        status=status,
        requested_by=workflow_id,
        actor="workflow_executor",
        idempotency_key=(
            idempotency_key or f"{workflow_id}:{step_id}:{attempt}"
        ),
        produced_artifact_refs=(
            (
                artifact_report_ref(
                    artifact_type,
                    f"{artifact_type}_{attempt}",
                ),
            )
            if status is WorkflowStepStatus.SUCCEEDED
            else ()
        ),
        public_data=public_data or {},
        blockers=blockers,
        retry=retry,
    )
