"""Define bounded public decisions emitted by the Research Coordinator.

The contracts in this module contain only canonical research identifiers,
registered workflow-template identity, typed prerequisites, and bounded issues.
They deliberately exclude tool names, tool arguments, experiment configuration,
and hidden reasoning so callers cannot use a coordination decision to alter an
approved experiment protocol.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any

from trader_research.governance import (
    Prerequisite,
    PrerequisiteKind,
    ResearchIssue,
    WorkflowOutcomeStatus,
)


class CoordinatorAction(str, Enum):
    """Closed set of next actions the Research Coordinator may select."""

    EXECUTE_REGISTERED_SPECIALIST_TASK = "execute_registered_specialist_task"
    EXECUTE_REGISTERED_WORKFLOW = "execute_registered_workflow"
    REQUEST_PREREQUISITE = "request_prerequisite"
    REQUEST_APPROVAL = "request_approval"
    REPORT_TERMINAL_STATE = "report_terminal_state"
    BLOCK = "block"


@dataclass(frozen=True)
class WorkflowTemplateDescriptor:
    """Public identity and purpose of one code-registered workflow template.

    Attributes:
        template_id: Stable responsibility-based template identifier.
        version: Immutable template contract version.
        description: Operator-facing summary of the workflow's purpose.
    """

    template_id: str
    version: str
    description: str

    def __post_init__(self) -> None:
        """Validate the stable public template metadata."""
        _required_text(self.template_id, "workflow template_id")
        _required_text(self.version, "workflow template version")
        _required_text(self.description, "workflow template description")

    def to_dict(self) -> dict[str, str]:
        """Serialize the template metadata without its runtime compiler."""
        return {
            "template_id": self.template_id,
            "version": self.version,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> WorkflowTemplateDescriptor:
        """Parse template metadata from a strict JSON-compatible mapping.

        Args:
            payload: Mapping containing only template identity and description.

        Returns:
            Validated workflow-template metadata.

        Raises:
            ValueError: If fields are missing, blank, or outside the contract.
        """
        _reject_unknown_fields(
            payload,
            allowed={"template_id", "version", "description"},
            label="workflow template descriptor",
        )
        return cls(
            template_id=str(payload.get("template_id") or ""),
            version=str(payload.get("version") or ""),
            description=str(payload.get("description") or ""),
        )


@dataclass(frozen=True)
class CoordinationDecision:
    """One validated next action for a bounded research objective.

    The selected action determines which optional fields are legal. Executable
    decisions pin either one registered specialist route or one registered
    workflow template and compiler-produced plan. Prerequisite and approval
    decisions contain only typed unresolved dependencies. Terminal decisions
    reproduce canonical outcome identity and permitted actions.

    Attributes:
        action: Next permitted coordinator action.
        objective_id: Canonical research objective identifier.
        protocol_id: Canonical experiment protocol identifier, when available.
        template_id: Registered workflow template selected for execution.
        template_version: Selected immutable template version.
        plan_id: Deterministically compiled workflow-plan identifier.
        specialist_task_id: Exact caller-built task selected for execution.
        specialist_authority: Decision authority addressed by the task.
        specialist_task_digest: Content digest of the exact selected task.
        specialist_route_version: Immutable code-owned route version.
        outcome_id: Canonical terminal workflow-outcome identifier.
        outcome_status: Terminal workflow status copied from canonical state.
        next_permitted_actions: Actions copied from a canonical outcome.
        prerequisites: Typed unresolved dependencies for the next action.
        blockers: Structured issues that prevent safe progression.
    """

    action: CoordinatorAction
    objective_id: str
    protocol_id: str | None = None
    template_id: str | None = None
    template_version: str | None = None
    plan_id: str | None = None
    specialist_task_id: str | None = None
    specialist_authority: str | None = None
    specialist_task_digest: str | None = None
    specialist_route_version: str | None = None
    outcome_id: str | None = None
    outcome_status: WorkflowOutcomeStatus | None = None
    next_permitted_actions: tuple[str, ...] = ()
    prerequisites: tuple[Prerequisite, ...] = ()
    blockers: tuple[ResearchIssue, ...] = ()

    def __post_init__(self) -> None:
        """Validate action-specific fields and reject contradictory decisions."""
        _required_text(self.objective_id, "coordination objective_id")
        _unique(
            (item.prerequisite_id for item in self.prerequisites),
            "coordination prerequisite IDs",
        )
        _unique(self.next_permitted_actions, "next permitted actions")
        if self.action is CoordinatorAction.EXECUTE_REGISTERED_SPECIALIST_TASK:
            self._validate_specialist_execution()
            return
        if self.action is CoordinatorAction.EXECUTE_REGISTERED_WORKFLOW:
            self._validate_execution()
            return
        self._reject_execution_fields()
        if self.action is CoordinatorAction.REQUEST_PREREQUISITE:
            self._validate_prerequisite_request()
        elif self.action is CoordinatorAction.REQUEST_APPROVAL:
            self._validate_approval_request()
        elif self.action is CoordinatorAction.REPORT_TERMINAL_STATE:
            self._validate_terminal_report()
        elif self.action is CoordinatorAction.BLOCK:
            self._validate_block()

    def _validate_execution(self) -> None:
        _required_text(self.protocol_id or "", "execution protocol_id")
        _required_text(self.template_id or "", "execution template_id")
        _required_text(
            self.template_version or "",
            "execution template version",
        )
        _required_text(self.plan_id or "", "execution plan_id")
        if self.prerequisites or self.blockers:
            raise ValueError(
                "executable coordination decisions cannot contain unresolved issues"
            )
        self._reject_specialist_fields()
        self._reject_outcome_fields()

    def _validate_specialist_execution(self) -> None:
        _required_text(self.specialist_task_id or "", "specialist task_id")
        _required_text(self.specialist_authority or "", "specialist authority")
        _required_text(self.specialist_task_digest or "", "specialist task digest")
        _required_text(
            self.specialist_route_version or "",
            "specialist route version",
        )
        if self.prerequisites or self.blockers:
            raise ValueError(
                "specialist execution decisions cannot contain unresolved issues"
            )
        self._reject_workflow_fields()
        self._reject_outcome_fields()

    def _reject_execution_fields(self) -> None:
        self._reject_workflow_fields()
        self._reject_specialist_fields()

    def _reject_workflow_fields(self) -> None:
        if self.template_id is not None:
            raise ValueError("non-execution decisions cannot select a template")
        if self.template_version is not None:
            raise ValueError("non-execution decisions cannot select a template version")
        if self.plan_id is not None:
            raise ValueError("non-execution decisions cannot select a plan")

    def _reject_specialist_fields(self) -> None:
        if any(
            value is not None
            for value in (
                self.specialist_task_id,
                self.specialist_authority,
                self.specialist_task_digest,
                self.specialist_route_version,
            )
        ):
            raise ValueError("non-specialist decisions cannot select a specialist task")

    def _validate_prerequisite_request(self) -> None:
        if not self.prerequisites:
            raise ValueError("prerequisite requests require unresolved prerequisites")
        if any(item.kind is PrerequisiteKind.APPROVAL for item in self.prerequisites):
            raise ValueError(
                "approval prerequisites require the request_approval action"
            )
        if self.blockers:
            raise ValueError("prerequisite requests cannot contain blockers")
        self._reject_outcome_fields()

    def _validate_approval_request(self) -> None:
        if not self.prerequisites:
            raise ValueError("approval requests require approval prerequisites")
        if any(
            item.kind is not PrerequisiteKind.APPROVAL for item in self.prerequisites
        ):
            raise ValueError(
                "request_approval decisions require only approval prerequisites"
            )
        if self.blockers:
            raise ValueError("approval requests cannot contain blockers")
        self._reject_outcome_fields()

    def _validate_terminal_report(self) -> None:
        _required_text(self.protocol_id or "", "terminal protocol_id")
        _required_text(self.outcome_id or "", "terminal outcome_id")
        if self.outcome_status is None:
            raise ValueError("terminal reports require outcome_status")
        if self.prerequisites or self.blockers:
            raise ValueError("terminal reports cannot contain unresolved issues")

    def _validate_block(self) -> None:
        if not self.blockers:
            raise ValueError("blocked coordination decisions require blockers")
        if self.prerequisites:
            raise ValueError("blocked decisions cannot request prerequisites")
        self._reject_outcome_fields()

    def _reject_outcome_fields(self) -> None:
        if self.outcome_id is not None or self.outcome_status is not None:
            raise ValueError("non-terminal decisions cannot report an outcome")
        if self.next_permitted_actions:
            raise ValueError(
                "non-terminal decisions cannot report next permitted actions"
            )

    def to_dict(self) -> dict[str, Any]:
        """Serialize the complete bounded decision into stable plain data."""
        return {
            "action": self.action.value,
            "objective_id": self.objective_id,
            "protocol_id": self.protocol_id,
            "template_id": self.template_id,
            "template_version": self.template_version,
            "plan_id": self.plan_id,
            "specialist_task_id": self.specialist_task_id,
            "specialist_authority": self.specialist_authority,
            "specialist_task_digest": self.specialist_task_digest,
            "specialist_route_version": self.specialist_route_version,
            "outcome_id": self.outcome_id,
            "outcome_status": (
                self.outcome_status.value if self.outcome_status is not None else None
            ),
            "next_permitted_actions": list(self.next_permitted_actions),
            "prerequisites": [item.to_dict() for item in self.prerequisites],
            "blockers": [item.to_dict() for item in self.blockers],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> CoordinationDecision:
        """Parse a strict decision mapping and enforce the closed action schema.

        Unknown fields are rejected so tool names, experiment overrides, or
        unreviewed planner output cannot be smuggled through this boundary.

        Args:
            payload: JSON-compatible coordination decision.

        Returns:
            Parsed and validated coordination decision.

        Raises:
            ValueError: If the action, fields, or nested contracts are invalid.
        """
        _reject_unknown_fields(
            payload,
            allowed={
                "action",
                "objective_id",
                "protocol_id",
                "template_id",
                "template_version",
                "plan_id",
                "specialist_task_id",
                "specialist_authority",
                "specialist_task_digest",
                "specialist_route_version",
                "outcome_id",
                "outcome_status",
                "next_permitted_actions",
                "prerequisites",
                "blockers",
            },
            label="coordination decision",
        )
        outcome_status = payload.get("outcome_status")
        prerequisite_payloads = _mapping_sequence(
            payload.get("prerequisites"),
            "prerequisites",
        )
        for prerequisite in prerequisite_payloads:
            _reject_unknown_fields(
                prerequisite,
                allowed={
                    "prerequisite_id",
                    "kind",
                    "target",
                    "description",
                    "required",
                    "status",
                    "satisfied_by",
                    "blockers",
                },
                label="coordination prerequisite",
            )
        blocker_payloads = _mapping_sequence(payload.get("blockers"), "blockers")
        for blocker in blocker_payloads:
            _reject_unknown_fields(
                blocker,
                allowed={"code", "message", "details"},
                label="coordination blocker",
            )
        return cls(
            action=_enum_value(
                CoordinatorAction,
                payload.get("action"),
                "coordinator action",
            ),
            objective_id=str(payload.get("objective_id") or ""),
            protocol_id=_optional_text(payload.get("protocol_id")),
            template_id=_optional_text(payload.get("template_id")),
            template_version=_optional_text(payload.get("template_version")),
            plan_id=_optional_text(payload.get("plan_id")),
            specialist_task_id=_optional_text(payload.get("specialist_task_id")),
            specialist_authority=_optional_text(payload.get("specialist_authority")),
            specialist_task_digest=_optional_text(
                payload.get("specialist_task_digest")
            ),
            specialist_route_version=_optional_text(
                payload.get("specialist_route_version")
            ),
            outcome_id=_optional_text(payload.get("outcome_id")),
            outcome_status=(
                _enum_value(
                    WorkflowOutcomeStatus,
                    outcome_status,
                    "workflow outcome status",
                )
                if outcome_status is not None
                else None
            ),
            next_permitted_actions=_text_tuple(
                payload.get("next_permitted_actions"),
                "next_permitted_actions",
            ),
            prerequisites=tuple(
                Prerequisite.from_dict(item) for item in prerequisite_payloads
            ),
            blockers=tuple(ResearchIssue.from_dict(item) for item in blocker_payloads),
        )


def _required_text(value: str, label: str) -> None:
    if not value.strip():
        raise ValueError(f"{label} is required")


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _enum_value[EnumType: Enum](
    enum_type: type[EnumType],
    value: object,
    label: str,
) -> EnumType:
    try:
        return enum_type(str(value))
    except ValueError as exc:
        raise ValueError(f"unsupported {label}: {value}") from exc


def _mapping_sequence(
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


def _text_tuple(value: object, label: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{label} must be a sequence")
    return tuple(str(item) for item in value)


def _unique(values: Iterable[str], label: str) -> None:
    materialized = tuple(values)
    if len(materialized) != len(set(materialized)):
        raise ValueError(f"{label} must be unique")


def _reject_unknown_fields(
    payload: Mapping[str, Any],
    *,
    allowed: set[str],
    label: str,
) -> None:
    unknown = sorted(set(payload).difference(allowed))
    if unknown:
        raise ValueError(f"{label} contains unknown fields: {', '.join(unknown)}")
