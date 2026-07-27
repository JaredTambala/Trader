"""Capability, prerequisite, artifact-slot, plan, and step-result contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from trader_research.foundation import (
    ORCHESTRATION_DOMAIN_OWNER,
    SUPPORTED_DOMAIN_OWNERS,
    jsonable,
)
from ..artifacts import (
    EXPERIMENT_PROTOCOL,
    RESEARCH_OBJECTIVE,
    WORKFLOW_PLAN,
    DOMAIN_OWNER_BY_ARTIFACT_TYPE,
    SUPPORTED_ARTIFACT_TYPES,
)
from ..handoffs import ArtifactReportRef, ResearchIssue
from ._validation import (
    _enum_value,
    _index_unique,
    _mapping,
    _mapping_sequence,
    _required_text,
    _required_text_sequence,
    _text_mapping,
    _text_tuple,
    _unique,
    _validate_payload_artifact_type,
    _validate_ref_type,
    _validate_text_mapping,
)
from .enums import (
    ApprovalStatus,
    ArtifactCardinality,
    ArtifactSlotStatus,
    CapabilitySideEffect,
    PrerequisiteKind,
    PrerequisiteStatus,
    RetryDisposition,
    WorkflowPlanStatus,
    WorkflowStepStatus,
)
from .protocols import Approval

@dataclass(frozen=True)
class ArtifactSlot:
    """Typed artifact requirement or resolved artifact set in a workflow."""

    slot_id: str
    artifact_type: str
    domain_owner: str
    cardinality: ArtifactCardinality
    required: bool
    status: ArtifactSlotStatus = ArtifactSlotStatus.EMPTY
    artifact_refs: tuple[ArtifactReportRef, ...] = ()
    blockers: tuple[ResearchIssue, ...] = ()

    def __post_init__(self) -> None:
        """Validate artifact authority, cardinality, and resolution state."""
        _required_text(self.slot_id, "artifact slot_id")
        if self.artifact_type not in SUPPORTED_ARTIFACT_TYPES:
            raise ValueError(f"unsupported artifact slot type: {self.artifact_type}")
        expected_owner = DOMAIN_OWNER_BY_ARTIFACT_TYPE[self.artifact_type]
        if self.domain_owner != expected_owner:
            raise ValueError(
                f"{self.artifact_type} slots must be owned by the "
                f"{expected_owner} domain"
            )
        for reference in self.artifact_refs:
            _validate_ref_type(reference, self.artifact_type, "artifact slot")
        count = len(self.artifact_refs)
        if self.cardinality is ArtifactCardinality.EXACTLY_ONE and count > 1:
            raise ValueError("exactly_one artifact slots cannot hold multiple refs")
        if self.cardinality is ArtifactCardinality.ZERO_OR_ONE and count > 1:
            raise ValueError("zero_or_one artifact slots cannot hold multiple refs")
        if self.status is ArtifactSlotStatus.EMPTY and (count or self.blockers):
            raise ValueError("empty artifact slots cannot contain refs or blockers")
        if self.status is ArtifactSlotStatus.RESOLVED:
            if self.cardinality in {
                ArtifactCardinality.EXACTLY_ONE,
                ArtifactCardinality.ONE_OR_MORE,
            } and count == 0:
                raise ValueError("resolved artifact slot requires artifact refs")
            if self.blockers:
                raise ValueError("resolved artifact slots cannot contain blockers")
        if self.status is ArtifactSlotStatus.BLOCKED and not self.blockers:
            raise ValueError("blocked artifact slots require blockers")

    def to_dict(self) -> dict[str, Any]:
        """Serialize this artifact slot."""
        return {
            "slot_id": self.slot_id,
            "artifact_type": self.artifact_type,
            "domain_owner": self.domain_owner,
            "cardinality": self.cardinality.value,
            "required": self.required,
            "status": self.status.value,
            "artifact_refs": [item.to_dict() for item in self.artifact_refs],
            "blockers": [item.to_dict() for item in self.blockers],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ArtifactSlot":
        """Parse an artifact slot."""
        return cls(
            slot_id=str(payload.get("slot_id") or ""),
            artifact_type=str(payload.get("artifact_type") or ""),
            domain_owner=str(payload.get("domain_owner") or ""),
            cardinality=_enum_value(
                ArtifactCardinality,
                payload.get("cardinality"),
                "artifact cardinality",
            ),
            required=bool(payload.get("required", False)),
            status=_enum_value(
                ArtifactSlotStatus,
                payload.get("status"),
                "artifact slot status",
            ),
            artifact_refs=tuple(
                ArtifactReportRef.from_dict(item)
                for item in _mapping_sequence(payload.get("artifact_refs"))
            ),
            blockers=tuple(
                ResearchIssue.from_dict(item)
                for item in _mapping_sequence(payload.get("blockers"))
            ),
        )


@dataclass(frozen=True)
class CapabilityDefinition:
    """Declarative snapshot of one registered deterministic action."""

    capability_id: str
    version: str
    description: str
    domain_owner: str
    producer_tool: str
    side_effect: CapabilitySideEffect
    input_slots: tuple[ArtifactSlot, ...]
    output_slots: tuple[ArtifactSlot, ...]
    policy_gates: tuple[str, ...] = ()
    configuration_keys: tuple[str, ...] = ()
    idempotent: bool = True

    def __post_init__(self) -> None:
        """Validate capability identity, authority, and declared slots."""
        _required_text(self.capability_id, "capability_id")
        _required_text(self.version, "capability version")
        _required_text(self.description, "capability description")
        if self.domain_owner not in SUPPORTED_DOMAIN_OWNERS:
            raise ValueError(
                f"unsupported capability domain_owner: {self.domain_owner}"
            )
        _required_text(self.producer_tool, "capability producer_tool")
        _unique(
            (item.slot_id for item in self.input_slots),
            "capability input slot IDs",
        )
        _unique(
            (item.slot_id for item in self.output_slots),
            "capability output slot IDs",
        )
        overlap = {item.slot_id for item in self.input_slots}.intersection(
            item.slot_id for item in self.output_slots
        )
        if overlap:
            raise ValueError(
                "capability input/output slot IDs overlap: "
                + ", ".join(sorted(overlap))
            )
        for slot in (*self.input_slots, *self.output_slots):
            if slot.status is not ArtifactSlotStatus.EMPTY:
                raise ValueError("capability slot declarations must be empty")
        for slot in self.output_slots:
            if slot.domain_owner != self.domain_owner:
                raise ValueError(
                    "capability output slots must match capability domain_owner"
                )
        _required_text_sequence(self.policy_gates, "capability policy gates", allow_empty=True)
        _required_text_sequence(
            self.configuration_keys,
            "capability configuration keys",
            allow_empty=True,
        )
        _unique(self.policy_gates, "capability policy gates")
        _unique(self.configuration_keys, "capability configuration keys")

    def to_dict(self) -> dict[str, Any]:
        """Serialize this capability snapshot."""
        return {
            "capability_id": self.capability_id,
            "version": self.version,
            "description": self.description,
            "domain_owner": self.domain_owner,
            "producer_tool": self.producer_tool,
            "side_effect": self.side_effect.value,
            "input_slots": [item.to_dict() for item in self.input_slots],
            "output_slots": [item.to_dict() for item in self.output_slots],
            "policy_gates": list(self.policy_gates),
            "configuration_keys": list(self.configuration_keys),
            "idempotent": self.idempotent,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CapabilityDefinition":
        """Parse a capability definition."""
        return cls(
            capability_id=str(payload.get("capability_id") or ""),
            version=str(payload.get("version") or ""),
            description=str(payload.get("description") or ""),
            domain_owner=str(payload.get("domain_owner") or ""),
            producer_tool=str(payload.get("producer_tool") or ""),
            side_effect=_enum_value(
                CapabilitySideEffect,
                payload.get("side_effect"),
                "capability side_effect",
            ),
            input_slots=tuple(
                ArtifactSlot.from_dict(item)
                for item in _mapping_sequence(payload.get("input_slots"))
            ),
            output_slots=tuple(
                ArtifactSlot.from_dict(item)
                for item in _mapping_sequence(payload.get("output_slots"))
            ),
            policy_gates=_text_tuple(payload.get("policy_gates")),
            configuration_keys=_text_tuple(payload.get("configuration_keys")),
            idempotent=bool(payload.get("idempotent", True)),
        )


@dataclass(frozen=True)
class Prerequisite:
    """A typed workflow dependency and its bounded resolution evidence."""

    prerequisite_id: str
    kind: PrerequisiteKind
    target: str
    description: str
    required: bool = True
    status: PrerequisiteStatus = PrerequisiteStatus.UNRESOLVED
    satisfied_by: tuple[str, ...] = ()
    blockers: tuple[ResearchIssue, ...] = ()

    def __post_init__(self) -> None:
        """Validate prerequisite identity and resolution consistency."""
        _required_text(self.prerequisite_id, "prerequisite_id")
        _required_text(self.target, "prerequisite target")
        _required_text(self.description, "prerequisite description")
        _required_text_sequence(
            self.satisfied_by,
            "prerequisite satisfied_by",
            allow_empty=True,
        )
        if self.status is PrerequisiteStatus.UNRESOLVED and (
            self.satisfied_by or self.blockers
        ):
            raise ValueError(
                "unresolved prerequisites cannot contain evidence or blockers"
            )
        if self.status is PrerequisiteStatus.SATISFIED:
            if not self.satisfied_by:
                raise ValueError("satisfied prerequisites require evidence refs")
            if self.blockers:
                raise ValueError("satisfied prerequisites cannot contain blockers")
        if self.status is PrerequisiteStatus.BLOCKED and not self.blockers:
            raise ValueError("blocked prerequisites require blockers")

    def to_dict(self) -> dict[str, Any]:
        """Serialize this prerequisite."""
        return {
            "prerequisite_id": self.prerequisite_id,
            "kind": self.kind.value,
            "target": self.target,
            "description": self.description,
            "required": self.required,
            "status": self.status.value,
            "satisfied_by": list(self.satisfied_by),
            "blockers": [item.to_dict() for item in self.blockers],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "Prerequisite":
        """Parse a workflow prerequisite."""
        return cls(
            prerequisite_id=str(payload.get("prerequisite_id") or ""),
            kind=_enum_value(
                PrerequisiteKind,
                payload.get("kind"),
                "prerequisite kind",
            ),
            target=str(payload.get("target") or ""),
            description=str(payload.get("description") or ""),
            required=bool(payload.get("required", True)),
            status=_enum_value(
                PrerequisiteStatus,
                payload.get("status"),
                "prerequisite status",
            ),
            satisfied_by=_text_tuple(payload.get("satisfied_by")),
            blockers=tuple(
                ResearchIssue.from_dict(item)
                for item in _mapping_sequence(payload.get("blockers"))
            ),
        )


@dataclass(frozen=True)
class WorkflowStep:
    """One declarative capability invocation in a workflow graph."""

    step_id: str
    capability_id: str
    depends_on: tuple[str, ...] = ()
    input_bindings: Mapping[str, str] = field(default_factory=dict)
    output_bindings: Mapping[str, str] = field(default_factory=dict)
    prerequisite_ids: tuple[str, ...] = ()
    approval_ids: tuple[str, ...] = ()
    configuration: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate stable step and binding identifiers."""
        _required_text(self.step_id, "workflow step_id")
        _required_text(self.capability_id, "workflow capability_id")
        _required_text_sequence(
            self.depends_on,
            "workflow step dependencies",
            allow_empty=True,
        )
        _required_text_sequence(
            self.prerequisite_ids,
            "workflow step prerequisite IDs",
            allow_empty=True,
        )
        _required_text_sequence(
            self.approval_ids,
            "workflow step approval IDs",
            allow_empty=True,
        )
        _validate_text_mapping(self.input_bindings, "workflow input bindings")
        _validate_text_mapping(self.output_bindings, "workflow output bindings")

    def to_dict(self) -> dict[str, Any]:
        """Serialize this workflow step."""
        return {
            "step_id": self.step_id,
            "capability_id": self.capability_id,
            "depends_on": list(self.depends_on),
            "input_bindings": dict(self.input_bindings),
            "output_bindings": dict(self.output_bindings),
            "prerequisite_ids": list(self.prerequisite_ids),
            "approval_ids": list(self.approval_ids),
            "configuration": jsonable(self.configuration),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "WorkflowStep":
        """Parse a workflow step."""
        return cls(
            step_id=str(payload.get("step_id") or ""),
            capability_id=str(payload.get("capability_id") or ""),
            depends_on=_text_tuple(payload.get("depends_on")),
            input_bindings=_text_mapping(payload.get("input_bindings")),
            output_bindings=_text_mapping(payload.get("output_bindings")),
            prerequisite_ids=_text_tuple(payload.get("prerequisite_ids")),
            approval_ids=_text_tuple(payload.get("approval_ids")),
            configuration=_mapping(payload.get("configuration")),
        )


@dataclass(frozen=True)
class WorkflowPlan:
    """Content-addressable graph of declared research capabilities."""

    plan_id: str
    objective_ref: ArtifactReportRef
    protocol_ref: ArtifactReportRef | None
    template_id: str
    template_version: str
    capabilities: tuple[CapabilityDefinition, ...]
    artifact_slots: tuple[ArtifactSlot, ...]
    prerequisites: tuple[Prerequisite, ...]
    approvals: tuple[Approval, ...]
    steps: tuple[WorkflowStep, ...]
    requested_by: str
    actor: str
    status: WorkflowPlanStatus = WorkflowPlanStatus.DRAFT

    artifact_type = WORKFLOW_PLAN
    domain_owner = ORCHESTRATION_DOMAIN_OWNER

    def __post_init__(self) -> None:
        """Validate workflow references, graph structure, and readiness state."""
        _required_text(self.plan_id, "workflow plan_id")
        _validate_ref_type(self.objective_ref, RESEARCH_OBJECTIVE, "workflow objective")
        if self.protocol_ref is not None:
            _validate_ref_type(
                self.protocol_ref,
                EXPERIMENT_PROTOCOL,
                "workflow protocol",
            )
        _required_text(self.template_id, "workflow template_id")
        _required_text(self.template_version, "workflow template_version")
        _required_text(self.requested_by, "workflow requested_by")
        _required_text(self.actor, "workflow actor")
        if not self.capabilities:
            raise ValueError("workflow capabilities are required")
        if not self.steps:
            raise ValueError("workflow steps are required")
        capabilities = _index_unique(
            self.capabilities,
            lambda item: item.capability_id,
            "workflow capability IDs",
        )
        slots = _index_unique(
            self.artifact_slots,
            lambda item: item.slot_id,
            "workflow artifact slot IDs",
        )
        prerequisites = _index_unique(
            self.prerequisites,
            lambda item: item.prerequisite_id,
            "workflow prerequisite IDs",
        )
        approvals = _index_unique(
            self.approvals,
            lambda item: item.approval_id,
            "workflow approval IDs",
        )
        steps = _index_unique(
            self.steps,
            lambda item: item.step_id,
            "workflow step IDs",
        )
        for step in self.steps:
            capability = capabilities.get(step.capability_id)
            if capability is None:
                raise ValueError(
                    f"workflow step {step.step_id} uses unknown capability "
                    f"{step.capability_id}"
                )
            self._validate_step(
                step,
                capability,
                slots,
                prerequisites,
                approvals,
                steps,
            )
        _validate_acyclic_steps(steps)
        self._validate_prerequisite_targets(
            capabilities,
            slots,
            prerequisites,
            approvals,
        )
        unresolved_inputs, blocked_slots = _validate_workflow_dataflow(
            steps,
            capabilities,
            slots,
        )
        self._validate_status(
            prerequisites,
            approvals,
            unresolved_inputs=unresolved_inputs,
            blocked_slots=blocked_slots,
        )

    @staticmethod
    def _validate_step(
        step: WorkflowStep,
        capability: CapabilityDefinition,
        slots: Mapping[str, ArtifactSlot],
        prerequisites: Mapping[str, Prerequisite],
        approvals: Mapping[str, Approval],
        steps: Mapping[str, WorkflowStep],
    ) -> None:
        unknown_dependencies = set(step.depends_on).difference(steps)
        if unknown_dependencies:
            raise ValueError(
                f"workflow step {step.step_id} has unknown dependencies: "
                + ", ".join(sorted(unknown_dependencies))
            )
        if step.step_id in step.depends_on:
            raise ValueError(f"workflow step {step.step_id} cannot depend on itself")
        _validate_slot_bindings(
            step=step,
            direction="input",
            bindings=step.input_bindings,
            declarations=capability.input_slots,
            plan_slots=slots,
        )
        _validate_slot_bindings(
            step=step,
            direction="output",
            bindings=step.output_bindings,
            declarations=capability.output_slots,
            plan_slots=slots,
        )
        unknown_prerequisites = set(step.prerequisite_ids).difference(prerequisites)
        if unknown_prerequisites:
            raise ValueError(
                f"workflow step {step.step_id} has unknown prerequisites: "
                + ", ".join(sorted(unknown_prerequisites))
            )
        unknown_approvals = set(step.approval_ids).difference(approvals)
        if unknown_approvals:
            raise ValueError(
                f"workflow step {step.step_id} has unknown approvals: "
                + ", ".join(sorted(unknown_approvals))
            )
        unknown_configuration = set(step.configuration).difference(
            capability.configuration_keys
        )
        if unknown_configuration:
            raise ValueError(
                f"workflow step {step.step_id} has undeclared configuration: "
                + ", ".join(sorted(unknown_configuration))
            )

    def _validate_status(
        self,
        prerequisites: Mapping[str, Prerequisite],
        approvals: Mapping[str, Approval],
        *,
        unresolved_inputs: bool,
        blocked_slots: bool,
    ) -> None:
        blocked = any(
            item.required and item.status is PrerequisiteStatus.BLOCKED
            for item in prerequisites.values()
        ) or any(
            item.status is ApprovalStatus.REJECTED for item in approvals.values()
        ) or blocked_slots
        unresolved_prerequisites = any(
            item.required and item.status is not PrerequisiteStatus.SATISFIED
            for item in prerequisites.values()
        )
        unresolved_approvals = any(
            item.status is not ApprovalStatus.APPROVED
            for item in approvals.values()
        )
        if self.status is WorkflowPlanStatus.READY and (
            blocked
            or unresolved_prerequisites
            or unresolved_approvals
            or unresolved_inputs
        ):
            raise ValueError(
                "ready workflow plans require satisfied prerequisites, approvals, "
                "and input slots"
            )
        if self.status is WorkflowPlanStatus.AWAITING_APPROVAL and not (
            unresolved_approvals
        ):
            raise ValueError(
                "awaiting_approval workflow plans require unresolved approvals"
            )
        if self.status is WorkflowPlanStatus.BLOCKED and not blocked:
            raise ValueError(
                "blocked workflow plans require a blocked prerequisite, approval, "
                "or artifact slot"
            )

    @staticmethod
    def _validate_prerequisite_targets(
        capabilities: Mapping[str, CapabilityDefinition],
        slots: Mapping[str, ArtifactSlot],
        prerequisites: Mapping[str, Prerequisite],
        approvals: Mapping[str, Approval],
    ) -> None:
        policy_gates = {
            gate
            for capability in capabilities.values()
            for gate in capability.policy_gates
        }
        targets = {
            PrerequisiteKind.ARTIFACT: set(slots),
            PrerequisiteKind.CAPABILITY: set(capabilities),
            PrerequisiteKind.POLICY_GATE: policy_gates,
            PrerequisiteKind.APPROVAL: set(approvals),
        }
        for prerequisite in prerequisites.values():
            if prerequisite.target not in targets[prerequisite.kind]:
                raise ValueError(
                    f"prerequisite {prerequisite.prerequisite_id} targets unknown "
                    f"{prerequisite.kind.value} {prerequisite.target}"
                )

    def to_dict(self) -> dict[str, Any]:
        """Serialize the complete workflow plan graph."""
        return {
            "artifact_type": self.artifact_type,
            "plan_id": self.plan_id,
            "objective_ref": self.objective_ref.to_dict(),
            "protocol_ref": (
                self.protocol_ref.to_dict() if self.protocol_ref is not None else None
            ),
            "template_id": self.template_id,
            "template_version": self.template_version,
            "capabilities": [item.to_dict() for item in self.capabilities],
            "artifact_slots": [item.to_dict() for item in self.artifact_slots],
            "prerequisites": [item.to_dict() for item in self.prerequisites],
            "approvals": [item.to_dict() for item in self.approvals],
            "steps": [item.to_dict() for item in self.steps],
            "requested_by": self.requested_by,
            "actor": self.actor,
            "status": self.status.value,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "WorkflowPlan":
        """Parse and revalidate a complete workflow plan graph."""
        _validate_payload_artifact_type(payload, WORKFLOW_PLAN)
        protocol_payload = payload.get("protocol_ref")
        return cls(
            plan_id=str(payload.get("plan_id") or ""),
            objective_ref=ArtifactReportRef.from_dict(
                _mapping(payload.get("objective_ref"))
            ),
            protocol_ref=(
                ArtifactReportRef.from_dict(protocol_payload)
                if isinstance(protocol_payload, Mapping)
                else None
            ),
            template_id=str(payload.get("template_id") or ""),
            template_version=str(payload.get("template_version") or ""),
            capabilities=tuple(
                CapabilityDefinition.from_dict(item)
                for item in _mapping_sequence(payload.get("capabilities"))
            ),
            artifact_slots=tuple(
                ArtifactSlot.from_dict(item)
                for item in _mapping_sequence(payload.get("artifact_slots"))
            ),
            prerequisites=tuple(
                Prerequisite.from_dict(item)
                for item in _mapping_sequence(payload.get("prerequisites"))
            ),
            approvals=tuple(
                Approval.from_dict(item)
                for item in _mapping_sequence(payload.get("approvals"))
            ),
            steps=tuple(
                WorkflowStep.from_dict(item)
                for item in _mapping_sequence(payload.get("steps"))
            ),
            requested_by=str(payload.get("requested_by") or ""),
            actor=str(payload.get("actor") or ""),
            status=_enum_value(
                WorkflowPlanStatus,
                payload.get("status"),
                "workflow plan status",
            ),
        )


@dataclass(frozen=True)
class WorkflowStepResult:
    """Bounded public result for one deterministic workflow-step attempt."""

    result_id: str
    plan_id: str
    step_id: str
    attempt: int
    command: str
    side_effect: CapabilitySideEffect
    status: WorkflowStepStatus
    requested_by: str
    actor: str
    idempotency_key: str
    produced_artifact_refs: tuple[ArtifactReportRef, ...] = ()
    public_data: Mapping[str, Any] = field(default_factory=dict)
    warnings: tuple[ResearchIssue, ...] = ()
    blockers: tuple[ResearchIssue, ...] = ()
    retry: RetryDisposition = RetryDisposition.NOT_APPLICABLE

    def __post_init__(self) -> None:
        """Validate result provenance, terminal state, and retry classification."""
        _required_text(self.result_id, "workflow result_id")
        _required_text(self.plan_id, "workflow result plan_id")
        _required_text(self.step_id, "workflow result step_id")
        if self.attempt <= 0:
            raise ValueError("workflow step result attempt must be positive")
        _required_text(self.command, "workflow result command")
        _required_text(self.requested_by, "workflow result requested_by")
        _required_text(self.actor, "workflow result actor")
        _required_text(self.idempotency_key, "workflow result idempotency_key")
        _unique(
            (item.uri for item in self.produced_artifact_refs),
            "workflow result artifact refs",
        )
        if self.status is WorkflowStepStatus.SUCCEEDED:
            if self.blockers:
                raise ValueError("successful workflow step results cannot have blockers")
            if self.retry is not RetryDisposition.NOT_APPLICABLE:
                raise ValueError(
                    "successful workflow step results cannot be retryable"
                )
        elif not self.blockers:
            raise ValueError("blocked or failed workflow step results require blockers")
        if (
            self.status is WorkflowStepStatus.BLOCKED
            and self.retry is RetryDisposition.NOT_APPLICABLE
        ):
            raise ValueError(
                "blocked workflow step results require a retry disposition"
            )

    def to_dict(self) -> dict[str, Any]:
        """Serialize this public workflow-step result."""
        return {
            "result_id": self.result_id,
            "plan_id": self.plan_id,
            "step_id": self.step_id,
            "attempt": self.attempt,
            "command": self.command,
            "side_effect": self.side_effect.value,
            "status": self.status.value,
            "requested_by": self.requested_by,
            "actor": self.actor,
            "idempotency_key": self.idempotency_key,
            "produced_artifact_refs": [
                item.to_dict() for item in self.produced_artifact_refs
            ],
            "public_data": jsonable(self.public_data),
            "warnings": [item.to_dict() for item in self.warnings],
            "blockers": [item.to_dict() for item in self.blockers],
            "retry": self.retry.value,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "WorkflowStepResult":
        """Parse and revalidate a workflow-step result."""
        return cls(
            result_id=str(payload.get("result_id") or ""),
            plan_id=str(payload.get("plan_id") or ""),
            step_id=str(payload.get("step_id") or ""),
            attempt=int(payload.get("attempt", 0)),
            command=str(payload.get("command") or ""),
            side_effect=_enum_value(
                CapabilitySideEffect,
                payload.get("side_effect"),
                "workflow result side_effect",
            ),
            status=_enum_value(
                WorkflowStepStatus,
                payload.get("status"),
                "workflow step status",
            ),
            requested_by=str(payload.get("requested_by") or ""),
            actor=str(payload.get("actor") or ""),
            idempotency_key=str(payload.get("idempotency_key") or ""),
            produced_artifact_refs=tuple(
                ArtifactReportRef.from_dict(item)
                for item in _mapping_sequence(
                    payload.get("produced_artifact_refs")
                )
            ),
            public_data=_mapping(payload.get("public_data")),
            warnings=tuple(
                ResearchIssue.from_dict(item)
                for item in _mapping_sequence(payload.get("warnings"))
            ),
            blockers=tuple(
                ResearchIssue.from_dict(item)
                for item in _mapping_sequence(payload.get("blockers"))
            ),
            retry=_enum_value(
                RetryDisposition,
                payload.get("retry"),
                "workflow retry disposition",
            ),
        )


def _validate_slot_bindings(
    *,
    step: WorkflowStep,
    direction: str,
    bindings: Mapping[str, str],
    declarations: tuple[ArtifactSlot, ...],
    plan_slots: Mapping[str, ArtifactSlot],
) -> None:
    declared = {item.slot_id: item for item in declarations}
    missing = {
        key for key, item in declared.items() if item.required and key not in bindings
    }
    if missing:
        raise ValueError(
            f"workflow step {step.step_id} is missing required {direction} bindings: "
            + ", ".join(sorted(missing))
        )
    unknown = set(bindings).difference(declared)
    if unknown:
        raise ValueError(
            f"workflow step {step.step_id} has undeclared {direction} bindings: "
            + ", ".join(sorted(unknown))
        )
    for declaration_id, plan_slot_id in bindings.items():
        plan_slot = plan_slots.get(plan_slot_id)
        if plan_slot is None:
            raise ValueError(
                f"workflow step {step.step_id} binds unknown artifact slot "
                f"{plan_slot_id}"
            )
        declaration = declared[declaration_id]
        if (
            plan_slot.artifact_type != declaration.artifact_type
            or plan_slot.domain_owner != declaration.domain_owner
            or plan_slot.cardinality is not declaration.cardinality
        ):
            raise ValueError(
                f"workflow step {step.step_id} {direction} binding "
                f"{declaration_id} does not match slot {plan_slot_id}"
            )


def _validate_acyclic_steps(steps: Mapping[str, WorkflowStep]) -> None:
    visited: set[str] = set()
    active: set[str] = set()

    def visit(step_id: str) -> None:
        if step_id in active:
            raise ValueError("workflow step dependencies contain a cycle")
        if step_id in visited:
            return
        active.add(step_id)
        for dependency in steps[step_id].depends_on:
            visit(dependency)
        active.remove(step_id)
        visited.add(step_id)

    for step_id in steps:
        visit(step_id)


def _validate_workflow_dataflow(
    steps: Mapping[str, WorkflowStep],
    capabilities: Mapping[str, CapabilityDefinition],
    slots: Mapping[str, ArtifactSlot],
) -> tuple[bool, bool]:
    producers: dict[str, str] = {}
    for step in steps.values():
        for slot_id in step.output_bindings.values():
            if slot_id in producers:
                raise ValueError(
                    f"workflow artifact slot {slot_id} has multiple producers"
                )
            if slots[slot_id].status is not ArtifactSlotStatus.EMPTY:
                raise ValueError(
                    f"workflow output slot {slot_id} must be empty in a plan"
                )
            producers[slot_id] = step.step_id

    dependency_cache: dict[str, set[str]] = {}

    def dependencies(step_id: str) -> set[str]:
        cached = dependency_cache.get(step_id)
        if cached is not None:
            return cached
        result: set[str] = set()
        for dependency in steps[step_id].depends_on:
            result.add(dependency)
            result.update(dependencies(dependency))
        dependency_cache[step_id] = result
        return result

    unresolved_inputs = False
    blocked_slots = any(
        slot.required and slot.status is ArtifactSlotStatus.BLOCKED
        for slot in slots.values()
    )
    for step in steps.values():
        declarations = {
            item.slot_id: item
            for item in capabilities[step.capability_id].input_slots
        }
        for declaration_id, slot_id in step.input_bindings.items():
            declaration = declarations[declaration_id]
            slot = slots[slot_id]
            if slot.status is ArtifactSlotStatus.BLOCKED:
                if declaration.required:
                    blocked_slots = True
                continue
            if slot.status is ArtifactSlotStatus.RESOLVED:
                continue
            producer = producers.get(slot_id)
            if producer is None:
                if declaration.required:
                    unresolved_inputs = True
                continue
            if producer not in dependencies(step.step_id):
                raise ValueError(
                    f"workflow step {step.step_id} consumes slot {slot_id} without "
                    f"depending on producer step {producer}"
                )
    return unresolved_inputs, blocked_slots
