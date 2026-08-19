"""Define bounded tasks, decisions, and results for specialist graphs.

The contracts in this module form the public boundary between research
coordination and specialist policy graphs. They carry approved objective data,
canonical artifact references, requested output slots, registered action
identity, and bounded issues. Tool names, raw MCP results, prompts, credentials,
and hidden reasoning are deliberately absent.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
import json
import math
from typing import Any

from trader_research.governance import (
    ArtifactReportRef,
    ArtifactSlot,
    ArtifactSlotStatus,
    CapabilitySideEffect,
    Prerequisite,
    PrerequisiteStatus,
    ResearchIssue,
    ResearchObjective,
    ResearchObjectiveStatus,
    SpecialistHandoff,
    get_decision_authority,
)


MAX_SPECIALIST_INPUT_BYTES = 65_536
"""Maximum serialized size of specialist-specific input in one task."""

MAX_SPECIALIST_INPUT_DEPTH = 12
"""Maximum nesting depth accepted in specialist-specific input."""

MAX_SPECIALIST_INPUT_REFS = 128
"""Maximum canonical input references accepted by one specialist task."""

MAX_SPECIALIST_OUTPUT_SLOTS = 64
"""Maximum requested output slots accepted by one specialist task."""


class SpecialistPolicyAction(str, Enum):
    """Closed actions a specialist policy may request from the shared shell."""

    RUN_REGISTERED_ACTION = "run_registered_action"
    REQUEST_PREREQUISITE = "request_prerequisite"
    COMPLETE = "complete"
    BLOCK = "block"


class SpecialistActionStatus(str, Enum):
    """Terminal outcomes returned by one registered specialist action."""

    SUCCEEDED = "succeeded"
    BLOCKED = "blocked"
    FAILED = "failed"


class SpecialistResultStatus(str, Enum):
    """Public terminal statuses returned by a specialist graph."""

    COMPLETED = "completed"
    AWAITING_PREREQUISITE = "awaiting_prerequisite"
    BLOCKED = "blocked"
    FAILED = "failed"


@dataclass(frozen=True)
class SpecialistTask:
    """One bounded request addressed to a registered specialist authority.

    Specialist-specific input remains a JSON-safe boundary payload. A registered
    action must parse that payload into its own typed request before performing
    any side effect. The shared shell never interprets it as tool arguments.

    Attributes:
        task_id: Stable identity for the specialist request.
        authority_key: Registered decision-authority key receiving the task.
        objective: Operator-owned research objective that bounds the work.
        requested_outputs: Empty typed artifact slots the specialist may fill.
        input_refs: Canonical artifacts available to specialist actions.
        requested_by: Workflow, objective, or operator request requiring the work.
        actor: Identity that routed the task to the specialist.
        permitted_side_effects: Side-effect classes explicitly permitted for work.
        approved_policy_gates: Policy gates already satisfied by the caller.
        specialist_input: Bounded role-specific input parsed again by an action.
    """

    task_id: str
    authority_key: str
    objective: ResearchObjective
    requested_outputs: tuple[ArtifactSlot, ...]
    input_refs: tuple[ArtifactReportRef, ...]
    requested_by: str
    actor: str
    permitted_side_effects: tuple[CapabilitySideEffect, ...] = (
        CapabilitySideEffect.READ_ONLY,
    )
    approved_policy_gates: tuple[str, ...] = ()
    specialist_input: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate task identity, authority, bounds, and requested outputs."""
        _required_text(self.task_id, "specialist task_id")
        _required_text(self.requested_by, "specialist requested_by")
        _required_text(self.actor, "specialist actor")
        authority = get_decision_authority(self.authority_key)
        if authority.key == "research_coordinator":
            raise ValueError("Research Coordinator cannot be invoked as a specialist")
        if self.objective.status is not ResearchObjectiveStatus.APPROVED:
            raise ValueError("specialist tasks require an approved research objective")
        if not self.requested_outputs:
            raise ValueError("specialist tasks require requested output slots")
        if len(self.requested_outputs) > MAX_SPECIALIST_OUTPUT_SLOTS:
            raise ValueError("specialist task exceeds the requested output-slot limit")
        if len(self.input_refs) > MAX_SPECIALIST_INPUT_REFS:
            raise ValueError("specialist task exceeds the input-reference limit")
        if not self.permitted_side_effects:
            raise ValueError("specialist task requires permitted side effects")
        _unique(
            (item.value for item in self.permitted_side_effects),
            "specialist permitted side effects",
        )
        for gate in self.approved_policy_gates:
            _required_text(gate, "specialist approved policy gate")
        _unique(self.approved_policy_gates, "specialist approved policy gates")
        _unique(
            (slot.slot_id for slot in self.requested_outputs),
            "specialist output slot IDs",
        )
        _unique(
            (reference.uri for reference in self.input_refs),
            "specialist input artifact URIs",
        )
        for slot in self.requested_outputs:
            if slot.status is not ArtifactSlotStatus.EMPTY:
                raise ValueError("specialist requested output slots must be empty")
            if slot.domain_owner not in authority.artifact_domains:
                raise ValueError(
                    f"{authority.display_name} cannot produce artifacts for the "
                    f"{slot.domain_owner} domain"
                )
        normalized_input = _normalize_json_mapping(
            self.specialist_input,
            label="specialist_input",
        )
        object.__setattr__(self, "specialist_input", normalized_input)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the bounded specialist request into plain data."""
        return {
            "task_id": self.task_id,
            "authority_key": self.authority_key,
            "objective": self.objective.to_dict(),
            "requested_outputs": [slot.to_dict() for slot in self.requested_outputs],
            "input_refs": [reference.to_dict() for reference in self.input_refs],
            "requested_by": self.requested_by,
            "actor": self.actor,
            "permitted_side_effects": [
                item.value for item in self.permitted_side_effects
            ],
            "approved_policy_gates": list(self.approved_policy_gates),
            "specialist_input": dict(self.specialist_input),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SpecialistTask":
        """Parse a strict JSON-compatible specialist task.

        Args:
            payload: Mapping containing the complete specialist request.

        Returns:
            Validated specialist task.

        Raises:
            ValueError: If fields, authority, bounds, or artifact slots are invalid.
        """
        _reject_unknown_fields(
            payload,
            allowed={
                "task_id",
                "authority_key",
                "objective",
                "requested_outputs",
                "input_refs",
                "requested_by",
                "actor",
                "permitted_side_effects",
                "approved_policy_gates",
                "specialist_input",
            },
            label="specialist task",
        )
        return cls(
            task_id=str(payload.get("task_id") or ""),
            authority_key=str(payload.get("authority_key") or ""),
            objective=ResearchObjective.from_dict(
                _mapping(payload.get("objective"), "objective")
            ),
            requested_outputs=tuple(
                ArtifactSlot.from_dict(item)
                for item in _mapping_sequence(
                    payload.get("requested_outputs"),
                    "requested_outputs",
                )
            ),
            input_refs=tuple(
                ArtifactReportRef.from_dict(item)
                for item in _mapping_sequence(
                    payload.get("input_refs"),
                    "input_refs",
                )
            ),
            requested_by=str(payload.get("requested_by") or ""),
            actor=str(payload.get("actor") or ""),
            permitted_side_effects=tuple(
                _enum_value(
                    CapabilitySideEffect,
                    item,
                    "specialist permitted side effect",
                )
                for item in _raw_sequence(
                    payload.get("permitted_side_effects")
                    or [CapabilitySideEffect.READ_ONLY.value],
                    "permitted_side_effects",
                )
            ),
            approved_policy_gates=_text_tuple(
                payload.get("approved_policy_gates"),
                "approved_policy_gates",
            ),
            specialist_input=_mapping(
                payload.get("specialist_input"),
                "specialist_input",
            ),
        )


@dataclass(frozen=True)
class SpecialistDecision:
    """One validated policy decision for a specialist task.

    Registered-action decisions bind only canonical input URIs and declared
    output slots. They cannot carry tool names or tool arguments. Prerequisite,
    completion, and blocker decisions reject all action-specific fields.

    Attributes:
        action: Closed policy action selected for this step.
        task_id: Specialist task receiving the decision.
        authority_key: Decision authority responsible for the task.
        reason: Concise public explanation for the selected action.
        action_id: Registered action identity when execution is requested.
        action_version: Exact registered action version.
        input_bindings: Capability input-slot IDs to canonical artifact URIs.
        output_bindings: Capability output-slot IDs to requested task-slot IDs.
        prerequisites: Unresolved dependencies requested from coordination.
        blockers: Structured reasons the specialist cannot continue.
    """

    action: SpecialistPolicyAction
    task_id: str
    authority_key: str
    reason: str
    action_id: str | None = None
    action_version: str | None = None
    input_bindings: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    output_bindings: Mapping[str, str] = field(default_factory=dict)
    prerequisites: tuple[Prerequisite, ...] = ()
    blockers: tuple[ResearchIssue, ...] = ()

    def __post_init__(self) -> None:
        """Validate action-specific fields and reject contradictory decisions."""
        _required_text(self.task_id, "specialist decision task_id")
        _required_text(self.authority_key, "specialist decision authority_key")
        _required_text(self.reason, "specialist decision reason")
        get_decision_authority(self.authority_key)
        normalized_inputs = _text_sequence_mapping(
            self.input_bindings,
            "specialist input bindings",
        )
        normalized_outputs = _text_mapping(
            self.output_bindings,
            "specialist output bindings",
        )
        object.__setattr__(self, "input_bindings", normalized_inputs)
        object.__setattr__(self, "output_bindings", normalized_outputs)
        _unique(
            (item.prerequisite_id for item in self.prerequisites),
            "specialist prerequisite IDs",
        )
        if self.action is SpecialistPolicyAction.RUN_REGISTERED_ACTION:
            _required_text(self.action_id or "", "specialist action_id")
            _required_text(
                self.action_version or "",
                "specialist action_version",
            )
            if self.prerequisites or self.blockers:
                raise ValueError(
                    "registered-action decisions cannot contain unresolved issues"
                )
            return
        if self.action_id is not None or self.action_version is not None:
            raise ValueError("non-execution decisions cannot select an action")
        if self.input_bindings or self.output_bindings:
            raise ValueError("non-execution decisions cannot contain bindings")
        if self.action is SpecialistPolicyAction.REQUEST_PREREQUISITE:
            if not self.prerequisites:
                raise ValueError(
                    "specialist prerequisite requests require prerequisites"
                )
            if any(
                item.status is not PrerequisiteStatus.UNRESOLVED
                for item in self.prerequisites
            ):
                raise ValueError(
                    "specialist prerequisite requests require unresolved prerequisites"
                )
            if self.blockers:
                raise ValueError(
                    "specialist prerequisite requests cannot contain blockers"
                )
        elif self.action is SpecialistPolicyAction.COMPLETE:
            if self.prerequisites or self.blockers:
                raise ValueError(
                    "specialist completion decisions cannot contain unresolved issues"
                )
        elif self.action is SpecialistPolicyAction.BLOCK:
            if not self.blockers:
                raise ValueError("specialist block decisions require blockers")
            if self.prerequisites:
                raise ValueError(
                    "specialist block decisions cannot request prerequisites"
                )

    def to_dict(self) -> dict[str, Any]:
        """Serialize the complete public specialist decision."""
        return {
            "action": self.action.value,
            "task_id": self.task_id,
            "authority_key": self.authority_key,
            "reason": self.reason,
            "action_id": self.action_id,
            "action_version": self.action_version,
            "input_bindings": {
                key: list(value) for key, value in self.input_bindings.items()
            },
            "output_bindings": dict(self.output_bindings),
            "prerequisites": [item.to_dict() for item in self.prerequisites],
            "blockers": [item.to_dict() for item in self.blockers],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SpecialistDecision":
        """Parse a strict policy decision and its closed action vocabulary."""
        _reject_unknown_fields(
            payload,
            allowed={
                "action",
                "task_id",
                "authority_key",
                "reason",
                "action_id",
                "action_version",
                "input_bindings",
                "output_bindings",
                "prerequisites",
                "blockers",
            },
            label="specialist decision",
        )
        return cls(
            action=_enum_value(
                SpecialistPolicyAction,
                payload.get("action"),
                "specialist policy action",
            ),
            task_id=str(payload.get("task_id") or ""),
            authority_key=str(payload.get("authority_key") or ""),
            reason=str(payload.get("reason") or ""),
            action_id=_optional_text(payload.get("action_id")),
            action_version=_optional_text(payload.get("action_version")),
            input_bindings=_sequence_mapping(
                payload.get("input_bindings"),
                "input_bindings",
            ),
            output_bindings=_mapping(
                payload.get("output_bindings"),
                "output_bindings",
            ),
            prerequisites=tuple(
                Prerequisite.from_dict(item)
                for item in _mapping_sequence(
                    payload.get("prerequisites"),
                    "prerequisites",
                )
            ),
            blockers=tuple(
                ResearchIssue.from_dict(item)
                for item in _mapping_sequence(payload.get("blockers"), "blockers")
            ),
        )


@dataclass(frozen=True)
class SpecialistActionOutcome:
    """Validated output from one code-registered specialist action.

    Outputs are keyed by the capability's declared output-slot IDs. Successful
    canonical handoffs may then be bound to the task's requested slots by the
    shared graph. No raw transport response or unrestricted public data is kept.

    Attributes:
        action_id: Registered action identity that produced the outcome.
        action_version: Exact registered action version.
        status: Terminal status for this action attempt.
        outputs: Declared output-slot IDs to canonical specialist handoffs.
        warnings: Structured non-fatal issues.
        blockers: Structured issues preventing safe continuation.
        errors: Structured execution or validation failures.
    """

    action_id: str
    action_version: str
    status: SpecialistActionStatus
    outputs: Mapping[str, tuple[SpecialistHandoff, ...]] = field(default_factory=dict)
    warnings: tuple[ResearchIssue, ...] = ()
    blockers: tuple[ResearchIssue, ...] = ()
    errors: tuple[ResearchIssue, ...] = ()

    def __post_init__(self) -> None:
        """Validate action identity, unique handoffs, and terminal issues."""
        _required_text(self.action_id, "specialist action outcome action_id")
        _required_text(
            self.action_version,
            "specialist action outcome action_version",
        )
        normalized_outputs = {
            str(key): tuple(value) for key, value in self.outputs.items()
        }
        for key in normalized_outputs:
            _required_text(key, "specialist action output slot ID")
        handoff_ids = [
            handoff.handoff_id
            for handoffs in normalized_outputs.values()
            for handoff in handoffs
        ]
        _unique(handoff_ids, "specialist action handoff IDs")
        object.__setattr__(self, "outputs", normalized_outputs)
        if self.status is SpecialistActionStatus.SUCCEEDED:
            if self.blockers or self.errors:
                raise ValueError(
                    "successful specialist actions cannot contain blockers or errors"
                )
        elif self.status is SpecialistActionStatus.BLOCKED:
            if not self.blockers or self.errors:
                raise ValueError(
                    "blocked specialist actions require blockers and no errors"
                )
        elif self.status is SpecialistActionStatus.FAILED:
            if not self.errors or self.blockers:
                raise ValueError(
                    "failed specialist actions require errors and no blockers"
                )

    def to_dict(self) -> dict[str, Any]:
        """Serialize the bounded registered-action outcome."""
        return {
            "action_id": self.action_id,
            "action_version": self.action_version,
            "status": self.status.value,
            "outputs": {
                key: [handoff.to_dict() for handoff in handoffs]
                for key, handoffs in self.outputs.items()
            },
            "warnings": [item.to_dict() for item in self.warnings],
            "blockers": [item.to_dict() for item in self.blockers],
            "errors": [item.to_dict() for item in self.errors],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SpecialistActionOutcome":
        """Parse and validate a registered-action outcome mapping."""
        _reject_unknown_fields(
            payload,
            allowed={
                "action_id",
                "action_version",
                "status",
                "outputs",
                "warnings",
                "blockers",
                "errors",
            },
            label="specialist action outcome",
        )
        raw_outputs = _mapping(payload.get("outputs"), "outputs")
        outputs: dict[str, tuple[SpecialistHandoff, ...]] = {}
        for key, value in raw_outputs.items():
            outputs[str(key)] = tuple(
                SpecialistHandoff.from_dict(item)
                for item in _mapping_sequence(value, f"outputs.{key}")
            )
        return cls(
            action_id=str(payload.get("action_id") or ""),
            action_version=str(payload.get("action_version") or ""),
            status=_enum_value(
                SpecialistActionStatus,
                payload.get("status"),
                "specialist action status",
            ),
            outputs=outputs,
            warnings=_issues(payload.get("warnings"), "warnings"),
            blockers=_issues(payload.get("blockers"), "blockers"),
            errors=_issues(payload.get("errors"), "errors"),
        )


@dataclass(frozen=True)
class SpecialistActionSummary:
    """Checkpoint-safe summary of one registered action attempt."""

    action_id: str
    action_version: str
    status: SpecialistActionStatus
    handoff_ids: tuple[str, ...] = ()
    warnings: tuple[ResearchIssue, ...] = ()
    blockers: tuple[ResearchIssue, ...] = ()
    errors: tuple[ResearchIssue, ...] = ()

    def __post_init__(self) -> None:
        """Validate bounded action identity, handoff IDs, and issue state."""
        _required_text(self.action_id, "specialist action summary action_id")
        _required_text(
            self.action_version,
            "specialist action summary action_version",
        )
        for handoff_id in self.handoff_ids:
            _required_text(handoff_id, "specialist action summary handoff_id")
        _unique(self.handoff_ids, "specialist action summary handoff IDs")
        if self.status is SpecialistActionStatus.SUCCEEDED:
            if self.blockers or self.errors:
                raise ValueError(
                    "successful specialist action summaries cannot contain "
                    "blockers or errors"
                )
        elif self.status is SpecialistActionStatus.BLOCKED:
            if not self.blockers or self.errors:
                raise ValueError(
                    "blocked specialist action summaries require blockers only"
                )
        elif self.status is SpecialistActionStatus.FAILED:
            if not self.errors or self.blockers:
                raise ValueError(
                    "failed specialist action summaries require errors only"
                )

    @classmethod
    def from_outcome(
        cls,
        outcome: SpecialistActionOutcome,
    ) -> "SpecialistActionSummary":
        """Reduce an outcome to identity, status, handoff IDs, and issues."""
        return cls(
            action_id=outcome.action_id,
            action_version=outcome.action_version,
            status=outcome.status,
            handoff_ids=tuple(
                handoff.handoff_id
                for handoffs in outcome.outputs.values()
                for handoff in handoffs
            ),
            warnings=outcome.warnings,
            blockers=outcome.blockers,
            errors=outcome.errors,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize a bounded action-attempt summary."""
        return {
            "action_id": self.action_id,
            "action_version": self.action_version,
            "status": self.status.value,
            "handoff_ids": list(self.handoff_ids),
            "warnings": [item.to_dict() for item in self.warnings],
            "blockers": [item.to_dict() for item in self.blockers],
            "errors": [item.to_dict() for item in self.errors],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SpecialistActionSummary":
        """Parse a strict action-attempt summary."""
        _reject_unknown_fields(
            payload,
            allowed={
                "action_id",
                "action_version",
                "status",
                "handoff_ids",
                "warnings",
                "blockers",
                "errors",
            },
            label="specialist action summary",
        )
        return cls(
            action_id=str(payload.get("action_id") or ""),
            action_version=str(payload.get("action_version") or ""),
            status=_enum_value(
                SpecialistActionStatus,
                payload.get("status"),
                "specialist action summary status",
            ),
            handoff_ids=_text_tuple(payload.get("handoff_ids"), "handoff_ids"),
            warnings=_issues(payload.get("warnings"), "warnings"),
            blockers=_issues(payload.get("blockers"), "blockers"),
            errors=_issues(payload.get("errors"), "errors"),
        )


@dataclass(frozen=True)
class SpecialistResult:
    """Bounded terminal result returned from a specialist graph.

    Attributes:
        task_id: Specialist task that reached a terminal state.
        authority_key: Specialist decision authority that handled the task.
        status: Completed, waiting, blocked, or failed terminal status.
        requested_by: Original request or workflow identity.
        actor: Registered specialist display identity.
        handoffs: Canonical specialist outputs produced during the task.
        output_bindings: Task-slot IDs to the handoffs that resolve them.
        prerequisites: Unresolved dependencies returned to coordination.
        warnings: Structured non-fatal issues.
        blockers: Structured domain blockers.
        errors: Structured policy, boundary, or execution failures.
    """

    task_id: str
    authority_key: str
    status: SpecialistResultStatus
    requested_by: str
    actor: str
    handoffs: tuple[SpecialistHandoff, ...] = ()
    output_bindings: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    prerequisites: tuple[Prerequisite, ...] = ()
    warnings: tuple[ResearchIssue, ...] = ()
    blockers: tuple[ResearchIssue, ...] = ()
    errors: tuple[ResearchIssue, ...] = ()

    def __post_init__(self) -> None:
        """Validate terminal consistency and unique handoff identity."""
        _required_text(self.task_id, "specialist result task_id")
        _required_text(self.authority_key, "specialist result authority_key")
        _required_text(self.requested_by, "specialist result requested_by")
        _required_text(self.actor, "specialist result actor")
        authority = get_decision_authority(self.authority_key)
        if self.actor != authority.display_name:
            raise ValueError(
                "specialist result actor does not match decision authority"
            )
        for handoff in self.handoffs:
            if handoff.artifact_uri is None:
                raise ValueError(
                    "specialist result handoffs require canonical artifact URIs"
                )
            if handoff.domain_owner not in authority.artifact_domains:
                raise ValueError("specialist result handoff exceeds decision authority")
            if handoff.requested_by != self.requested_by:
                raise ValueError(
                    "specialist result handoff requester does not match result"
                )
            if handoff.actor != self.actor:
                raise ValueError(
                    "specialist result handoff actor does not match result"
                )
        _unique(
            (handoff.handoff_id for handoff in self.handoffs),
            "specialist result handoff IDs",
        )
        normalized_bindings = _text_sequence_mapping(
            self.output_bindings,
            "specialist result output bindings",
        )
        object.__setattr__(self, "output_bindings", normalized_bindings)
        bound_handoff_ids = {
            handoff_id
            for handoff_ids in self.output_bindings.values()
            for handoff_id in handoff_ids
        }
        known_handoff_ids = {handoff.handoff_id for handoff in self.handoffs}
        bound_handoff_sequence = tuple(
            handoff_id
            for handoff_ids in self.output_bindings.values()
            for handoff_id in handoff_ids
        )
        if len(bound_handoff_sequence) != len(set(bound_handoff_sequence)):
            raise ValueError("specialist result handoffs cannot bind more than once")
        if bound_handoff_ids != known_handoff_ids:
            raise ValueError(
                "specialist result bindings must cover every handoff exactly"
            )
        if self.status is SpecialistResultStatus.COMPLETED:
            if self.prerequisites or self.blockers or self.errors:
                raise ValueError(
                    "completed specialist results cannot contain unresolved issues"
                )
        elif self.status is SpecialistResultStatus.AWAITING_PREREQUISITE:
            if not self.prerequisites or self.blockers or self.errors:
                raise ValueError(
                    "awaiting specialist results require prerequisites only"
                )
        elif self.status is SpecialistResultStatus.BLOCKED:
            if not self.blockers or self.prerequisites or self.errors:
                raise ValueError("blocked specialist results require blockers only")
        elif self.status is SpecialistResultStatus.FAILED:
            if not self.errors or self.prerequisites or self.blockers:
                raise ValueError("failed specialist results require errors only")

    def to_dict(self) -> dict[str, Any]:
        """Serialize the terminal result without operational internals."""
        return {
            "task_id": self.task_id,
            "authority_key": self.authority_key,
            "status": self.status.value,
            "requested_by": self.requested_by,
            "actor": self.actor,
            "handoffs": [handoff.to_dict() for handoff in self.handoffs],
            "output_bindings": {
                key: list(value) for key, value in self.output_bindings.items()
            },
            "prerequisites": [item.to_dict() for item in self.prerequisites],
            "warnings": [item.to_dict() for item in self.warnings],
            "blockers": [item.to_dict() for item in self.blockers],
            "errors": [item.to_dict() for item in self.errors],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SpecialistResult":
        """Parse a strict terminal specialist result."""
        _reject_unknown_fields(
            payload,
            allowed={
                "task_id",
                "authority_key",
                "status",
                "requested_by",
                "actor",
                "handoffs",
                "output_bindings",
                "prerequisites",
                "warnings",
                "blockers",
                "errors",
            },
            label="specialist result",
        )
        return cls(
            task_id=str(payload.get("task_id") or ""),
            authority_key=str(payload.get("authority_key") or ""),
            status=_enum_value(
                SpecialistResultStatus,
                payload.get("status"),
                "specialist result status",
            ),
            requested_by=str(payload.get("requested_by") or ""),
            actor=str(payload.get("actor") or ""),
            handoffs=tuple(
                SpecialistHandoff.from_dict(item)
                for item in _mapping_sequence(payload.get("handoffs"), "handoffs")
            ),
            output_bindings=_sequence_mapping(
                payload.get("output_bindings"),
                "output_bindings",
            ),
            prerequisites=tuple(
                Prerequisite.from_dict(item)
                for item in _mapping_sequence(
                    payload.get("prerequisites"),
                    "prerequisites",
                )
            ),
            warnings=_issues(payload.get("warnings"), "warnings"),
            blockers=_issues(payload.get("blockers"), "blockers"),
            errors=_issues(payload.get("errors"), "errors"),
        )


def _normalize_json_mapping(
    value: Mapping[str, Any],
    *,
    label: str,
) -> dict[str, Any]:
    normalized = _normalize_json_value(value, label=label, depth=0)
    if not isinstance(normalized, dict):  # pragma: no cover - Mapping guarantees this
        raise ValueError(f"{label} must be an object")
    serialized = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
    if len(serialized.encode("utf-8")) > MAX_SPECIALIST_INPUT_BYTES:
        raise ValueError(f"{label} exceeds the {MAX_SPECIALIST_INPUT_BYTES}-byte limit")
    return normalized


def _normalize_json_value(value: Any, *, label: str, depth: int) -> Any:
    if depth > MAX_SPECIALIST_INPUT_DEPTH:
        raise ValueError(f"{label} exceeds the nesting-depth limit")
    if value is None or isinstance(value, str | bool | int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{label} contains a non-finite number")
        return value
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str) or not key:
                raise ValueError(f"{label} keys must be non-empty strings")
            normalized[key] = _normalize_json_value(
                item,
                label=f"{label}.{key}",
                depth=depth + 1,
            )
        return normalized
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [
            _normalize_json_value(
                item,
                label=f"{label}[{index}]",
                depth=depth + 1,
            )
            for index, item in enumerate(value)
        ]
    raise ValueError(f"{label} contains a non-JSON value: {type(value).__name__}")


def _required_text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} is required")
    return value


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError("optional text values must be non-empty strings")
    return value


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _mapping_sequence(value: Any, label: str) -> tuple[Mapping[str, Any], ...]:
    if value is None:
        return ()
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        raise ValueError(f"{label} must be an array")
    items: list[Mapping[str, Any]] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise ValueError(f"{label} entries must be objects")
        items.append(item)
    return tuple(items)


def _raw_sequence(value: Any, label: str) -> tuple[Any, ...]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        raise ValueError(f"{label} must be an array")
    return tuple(value)


def _sequence_mapping(value: Any, label: str) -> Mapping[str, tuple[str, ...]]:
    raw = _mapping(value, label)
    return {str(key): _text_tuple(item, f"{label}.{key}") for key, item in raw.items()}


def _text_tuple(value: Any, label: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        raise ValueError(f"{label} must be an array")
    result = tuple(str(item) for item in value)
    for item in result:
        _required_text(item, label)
    _unique(result, label)
    return result


def _text_sequence_mapping(
    value: Mapping[str, Sequence[str]],
    label: str,
) -> dict[str, tuple[str, ...]]:
    result: dict[str, tuple[str, ...]] = {}
    for key, items in value.items():
        if not isinstance(key, str):
            raise ValueError(f"{label} keys must be strings")
        if not isinstance(items, Sequence) or isinstance(
            items,
            str | bytes | bytearray,
        ):
            raise ValueError(f"{label}.{key} must be an array")
        normalized_key = key
        _required_text(normalized_key, f"{label} key")
        if any(not isinstance(item, str) for item in items):
            raise ValueError(f"{label}.{normalized_key} entries must be strings")
        normalized_items = tuple(items)
        for item in normalized_items:
            _required_text(item, f"{label}.{normalized_key}")
        _unique(normalized_items, f"{label}.{normalized_key}")
        result[normalized_key] = normalized_items
    return result


def _text_mapping(value: Mapping[str, str], label: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not isinstance(item, str):
            raise ValueError(f"{label} keys and values must be strings")
        normalized_key = key
        normalized_item = item
        _required_text(normalized_key, f"{label} key")
        _required_text(normalized_item, f"{label}.{normalized_key}")
        result[normalized_key] = normalized_item
    return result


def _issues(value: Any, label: str) -> tuple[ResearchIssue, ...]:
    return tuple(
        ResearchIssue.from_dict(item) for item in _mapping_sequence(value, label)
    )


def _enum_value(enum_type: type[Enum], value: Any, label: str) -> Any:
    try:
        return enum_type(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"unsupported {label}: {value}") from exc


def _reject_unknown_fields(
    payload: Mapping[str, Any],
    *,
    allowed: set[str],
    label: str,
) -> None:
    unknown = sorted(str(key) for key in payload if key not in allowed)
    if unknown:
        raise ValueError(f"{label} contains unknown fields: {', '.join(unknown)}")


def _unique(values: Iterable[str], label: str) -> None:
    normalized = tuple(values)
    if len(normalized) != len(set(normalized)):
        raise ValueError(f"{label} must be unique")
