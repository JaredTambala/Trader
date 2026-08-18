"""Select one bounded next action for a research objective.

The policy is deterministic for a given objective, protocol, outcome, template
catalog, and artifact-store state. It never calls MCP tools or writes canonical
records. Expected readiness gaps become typed prerequisite or blocker decisions;
successful selection returns the compiler-produced workflow for the existing
mechanical executor.
"""

from __future__ import annotations

from dataclasses import dataclass

from trader_research.foundation import (
    ResearchArtifactStore,
    ResearchArtifactStoreError,
    stable_research_id,
)
from trader_research.governance import (
    EXPERIMENT_PROTOCOL,
    ApprovalStatus,
    ExperimentProtocol,
    ExperimentProtocolStatus,
    Prerequisite,
    PrerequisiteKind,
    ResearchIssue,
    ResearchObjective,
    ResearchObjectiveStatus,
    WorkflowOutcome,
)

from trader_agents.orchestration import (
    CompiledResearchWorkflow,
    WorkflowInputUnavailableError,
)

from .catalog import WorkflowTemplateCatalog, default_workflow_template_catalog
from .domain import CoordinationDecision, CoordinatorAction


@dataclass(frozen=True)
class ResearchCoordination:
    """Bounded coordinator decision plus an optional executable workflow.

    Attributes:
        decision: Public next action containing no tool invocation details.
        compiled_workflow: Compiler-produced workflow when execution is ready;
            otherwise ``None``.
    """

    decision: CoordinationDecision
    compiled_workflow: CompiledResearchWorkflow | None = None

    def __post_init__(self) -> None:
        """Keep executable decisions and compiled state internally consistent."""
        executable = (
            self.decision.action is CoordinatorAction.EXECUTE_REGISTERED_WORKFLOW
        )
        if executable != (self.compiled_workflow is not None):
            raise ValueError(
                "only executable coordination decisions may carry a compiled workflow"
            )


def coordinate_research(
    *,
    objective: ResearchObjective,
    protocol: ExperimentProtocol | None,
    artifact_store: ResearchArtifactStore,
    outcome: WorkflowOutcome | None = None,
    catalog: WorkflowTemplateCatalog | None = None,
) -> ResearchCoordination:
    """Select the next permitted action for canonical research state.

    Objective and protocol lifecycle checks run before artifact reads. An
    approved, uniquely supported protocol is compiled through its code-owned
    registration to prove that every canonical input resolves. The function
    performs no persistence or network writes.

    Args:
        objective: Operator-owned research objective to coordinate.
        protocol: Optional experiment protocol proposed for the objective.
        artifact_store: Canonical reader used by the selected template compiler.
        outcome: Optional canonical terminal outcome to report.
        catalog: Optional injected catalog for deterministic tests or composition.

    Returns:
        A bounded decision and, only when ready, its compiled workflow.
    """
    selected_catalog = catalog or default_workflow_template_catalog()
    objective_decision = _objective_lifecycle_decision(objective)
    if objective_decision is not None:
        return ResearchCoordination(decision=objective_decision)
    if protocol is None:
        return ResearchCoordination(decision=_request_experiment_protocol(objective))
    if protocol.objective_id != objective.objective_id:
        return ResearchCoordination(
            decision=_blocked(
                objective=objective,
                protocol=protocol,
                code="protocol_objective_mismatch",
                message="Experiment protocol does not belong to the research objective.",
            )
        )
    protocol_decision = _protocol_lifecycle_decision(objective, protocol)
    if protocol_decision is not None:
        return ResearchCoordination(decision=protocol_decision)
    if outcome is not None:
        return ResearchCoordination(
            decision=_terminal_outcome_decision(objective, protocol, outcome)
        )
    return _select_registered_workflow(
        objective=objective,
        protocol=protocol,
        artifact_store=artifact_store,
        catalog=selected_catalog,
    )


def _select_registered_workflow(
    *,
    objective: ResearchObjective,
    protocol: ExperimentProtocol,
    artifact_store: ResearchArtifactStore,
    catalog: WorkflowTemplateCatalog,
) -> ResearchCoordination:
    """Require one eligible registration and compile it without side effects."""
    eligible = catalog.eligible_templates(
        objective=objective,
        protocol=protocol,
    )
    if not eligible:
        return ResearchCoordination(
            decision=_blocked(
                objective=objective,
                protocol=protocol,
                code="no_registered_workflow_template",
                message=(
                    "No registered workflow template accepts the approved "
                    "experiment protocol."
                ),
            )
        )
    if len(eligible) > 1:
        identities = [
            (
                template.descriptor.template_id,
                template.descriptor.version,
            )
            for template in eligible
        ]
        return ResearchCoordination(
            decision=_blocked(
                objective=objective,
                protocol=protocol,
                code="ambiguous_registered_workflow_template",
                message=(
                    "More than one registered workflow template accepts the "
                    "approved experiment protocol."
                ),
                details={
                    "templates": [
                        f"{template_id}:{version}"
                        for template_id, version in identities
                    ]
                },
            )
        )
    registration = eligible[0]
    try:
        compiled = registration.compiler(
            objective=objective,
            protocol=protocol,
            artifact_store=artifact_store,
        )
    except WorkflowInputUnavailableError as exc:
        return ResearchCoordination(
            decision=_request_artifact(objective, protocol, exc)
        )
    except ResearchArtifactStoreError as exc:
        return ResearchCoordination(
            decision=_blocked(
                objective=objective,
                protocol=protocol,
                code="workflow_input_store_unavailable",
                message=str(exc),
                details={
                    "template_id": registration.descriptor.template_id,
                    "template_version": registration.descriptor.version,
                },
            )
        )
    except ValueError as exc:
        return ResearchCoordination(
            decision=_blocked(
                objective=objective,
                protocol=protocol,
                code="registered_workflow_rejected",
                message=str(exc),
                details={
                    "template_id": registration.descriptor.template_id,
                    "template_version": registration.descriptor.version,
                },
            )
        )
    if (
        compiled.plan.template_id != registration.descriptor.template_id
        or compiled.plan.template_version != registration.descriptor.version
    ):
        return ResearchCoordination(
            decision=_blocked(
                objective=objective,
                protocol=protocol,
                code="registered_template_identity_mismatch",
                message=(
                    "Selected workflow compiler returned a plan for a different "
                    "template identity."
                ),
            )
        )
    decision = CoordinationDecision(
        action=CoordinatorAction.EXECUTE_REGISTERED_WORKFLOW,
        objective_id=objective.objective_id,
        protocol_id=protocol.protocol_id,
        template_id=registration.descriptor.template_id,
        template_version=registration.descriptor.version,
        plan_id=compiled.plan.plan_id,
    )
    return ResearchCoordination(
        decision=decision,
        compiled_workflow=compiled,
    )


def compile_coordination_decision(
    *,
    decision: CoordinationDecision,
    objective: ResearchObjective,
    protocol: ExperimentProtocol,
    artifact_store: ResearchArtifactStore,
    catalog: WorkflowTemplateCatalog | None = None,
) -> CompiledResearchWorkflow:
    """Recompile and validate an executable coordination decision.

    This boundary is intended for callers that persisted or transported only the
    bounded decision. Exact objective, protocol, registered-template, and plan
    identity must still match before the workflow can reach the executor.

    Args:
        decision: Previously produced executable coordination decision.
        objective: Exact objective named by the decision.
        protocol: Exact approved protocol named by the decision.
        artifact_store: Canonical reader used to revalidate workflow inputs.
        catalog: Optional injected code-owned template catalog.

    Returns:
        Recompiled workflow whose identity exactly matches the decision.

    Raises:
        ValueError: If the action, canonical identities, registration, or
            deterministic plan identity differs from the decision.
    """
    if decision.action is not CoordinatorAction.EXECUTE_REGISTERED_WORKFLOW:
        raise ValueError("coordination decision is not executable")
    if decision.objective_id != objective.objective_id:
        raise ValueError("coordination decision objective does not match input")
    if decision.protocol_id != protocol.protocol_id:
        raise ValueError("coordination decision protocol does not match input")
    selected_catalog = catalog or default_workflow_template_catalog()
    registration = selected_catalog.require(
        decision.template_id or "",
        decision.template_version or "",
    )
    if not registration.is_eligible(objective, protocol):
        raise ValueError("registered workflow template no longer accepts protocol")
    compiled = registration.compiler(
        objective=objective,
        protocol=protocol,
        artifact_store=artifact_store,
    )
    if compiled.plan.plan_id != decision.plan_id:
        raise ValueError("recompiled workflow plan does not match decision")
    return compiled


def _objective_lifecycle_decision(
    objective: ResearchObjective,
) -> CoordinationDecision | None:
    if objective.status is ResearchObjectiveStatus.APPROVED:
        return None
    if objective.status is ResearchObjectiveStatus.DRAFT:
        prerequisite = _prerequisite(
            objective_id=objective.objective_id,
            kind=PrerequisiteKind.APPROVAL,
            target=objective.objective_id,
            description="Approve the research objective before protocol selection.",
        )
        return CoordinationDecision(
            action=CoordinatorAction.REQUEST_APPROVAL,
            objective_id=objective.objective_id,
            prerequisites=(prerequisite,),
        )
    return _blocked(
        objective=objective,
        protocol=None,
        code=f"research_objective_{objective.status.value}",
        message=(
            "Research objective cannot progress while its status is "
            f"{objective.status.value}."
        ),
    )


def _request_experiment_protocol(
    objective: ResearchObjective,
) -> CoordinationDecision:
    prerequisite = _prerequisite(
        objective_id=objective.objective_id,
        kind=PrerequisiteKind.ARTIFACT,
        target=EXPERIMENT_PROTOCOL,
        description=(
            "An Experiment Design owner must propose a protocol for the approved "
            "research objective."
        ),
    )
    return CoordinationDecision(
        action=CoordinatorAction.REQUEST_PREREQUISITE,
        objective_id=objective.objective_id,
        prerequisites=(prerequisite,),
    )


def _protocol_lifecycle_decision(
    objective: ResearchObjective,
    protocol: ExperimentProtocol,
) -> CoordinationDecision | None:
    if protocol.status is ExperimentProtocolStatus.APPROVED:
        return None
    if protocol.status in {
        ExperimentProtocolStatus.BLOCKED,
        ExperimentProtocolStatus.SUPERSEDED,
    }:
        return _blocked(
            objective=objective,
            protocol=protocol,
            code=f"experiment_protocol_{protocol.status.value}",
            message=(
                "Experiment protocol cannot progress while its status is "
                f"{protocol.status.value}."
            ),
        )
    rejected = tuple(
        approval
        for approval in protocol.approvals
        if approval.status is ApprovalStatus.REJECTED
    )
    if rejected:
        return _blocked(
            objective=objective,
            protocol=protocol,
            code="experiment_protocol_approval_rejected",
            message="Experiment protocol contains rejected material approvals.",
            details={"approval_ids": [item.approval_id for item in rejected]},
        )
    requested = tuple(
        approval
        for approval in protocol.approvals
        if approval.status is ApprovalStatus.REQUESTED
    )
    if requested:
        prerequisites = tuple(
            _prerequisite(
                objective_id=objective.objective_id,
                kind=PrerequisiteKind.APPROVAL,
                target=approval.approval_id,
                description=(
                    "Resolve material protocol assumption approval "
                    f"{approval.approval_id} with {approval.requested_from}."
                ),
            )
            for approval in requested
        )
    else:
        prerequisites = (
            _prerequisite(
                objective_id=objective.objective_id,
                kind=PrerequisiteKind.APPROVAL,
                target=protocol.protocol_id,
                description="Approve the complete experiment protocol.",
            ),
        )
    return CoordinationDecision(
        action=CoordinatorAction.REQUEST_APPROVAL,
        objective_id=objective.objective_id,
        protocol_id=protocol.protocol_id,
        prerequisites=prerequisites,
    )


def _request_artifact(
    objective: ResearchObjective,
    protocol: ExperimentProtocol,
    error: WorkflowInputUnavailableError,
) -> CoordinationDecision:
    reference = error.reference
    prerequisite = _prerequisite(
        objective_id=objective.objective_id,
        kind=PrerequisiteKind.ARTIFACT,
        target=reference.uri,
        description=(
            f"Resolve the declared {reference.artifact_type} from the "
            f"{reference.domain_owner} domain."
        ),
    )
    return CoordinationDecision(
        action=CoordinatorAction.REQUEST_PREREQUISITE,
        objective_id=objective.objective_id,
        protocol_id=protocol.protocol_id,
        prerequisites=(prerequisite,),
    )


def _terminal_outcome_decision(
    objective: ResearchObjective,
    protocol: ExperimentProtocol,
    outcome: WorkflowOutcome,
) -> CoordinationDecision:
    if outcome.objective_ref.artifact_id != objective.objective_id:
        return _blocked(
            objective=objective,
            protocol=protocol,
            code="workflow_outcome_objective_mismatch",
            message="Workflow outcome does not belong to the research objective.",
        )
    if outcome.protocol_ref.artifact_id != protocol.protocol_id:
        return _blocked(
            objective=objective,
            protocol=protocol,
            code="workflow_outcome_protocol_mismatch",
            message="Workflow outcome does not belong to the experiment protocol.",
        )
    return CoordinationDecision(
        action=CoordinatorAction.REPORT_TERMINAL_STATE,
        objective_id=objective.objective_id,
        protocol_id=protocol.protocol_id,
        outcome_id=outcome.outcome_id,
        outcome_status=outcome.status,
        next_permitted_actions=outcome.next_permitted_actions,
    )


def _blocked(
    *,
    objective: ResearchObjective,
    protocol: ExperimentProtocol | None,
    code: str,
    message: str,
    details: dict[str, object] | None = None,
) -> CoordinationDecision:
    return CoordinationDecision(
        action=CoordinatorAction.BLOCK,
        objective_id=objective.objective_id,
        protocol_id=protocol.protocol_id if protocol is not None else None,
        blockers=(
            ResearchIssue(
                code=code,
                message=message,
                details=details or {},
            ),
        ),
    )


def _prerequisite(
    *,
    objective_id: str,
    kind: PrerequisiteKind,
    target: str,
    description: str,
) -> Prerequisite:
    return Prerequisite(
        prerequisite_id=stable_research_id(
            "coordination_prerequisite",
            {
                "objective_id": objective_id,
                "kind": kind.value,
                "target": target,
            },
        ),
        kind=kind,
        target=target,
        description=description,
    )
