"""Define bounded request and checkpoint values for research composition.

The public request contains exact caller-built specialist tasks. Operational
checkpoint state retains only stable identities, digests, canonical references,
bounded decisions, and issues; runtime clients and complete artifact payloads
remain outside this module.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal, TypedDict

from trader_research.foundation import json_payload_hash
from trader_research.governance import (
    ExperimentProtocol,
    ResearchObjective,
    ResearchObjectiveStatus,
    experiment_protocol_design_digest,
)

from trader_agents.specialists import SpecialistTask, specialist_task_digest


MAX_COMPOSITION_SPECIALIST_TASKS = 8
"""Maximum explicit specialist tasks accepted by one composition request."""

MAX_COMPOSITION_TRANSITIONS = 32
"""Maximum checkpointed composition transitions before terminal failure."""


@dataclass(frozen=True)
class ResearchCompositionRequest:
    """Immutable caller-owned boundary for one coordinated research run.

    Specialist task scope is supplied explicitly and is never inferred from the
    objective statement. Each task must carry the same exact approved objective,
    use the composition ID as its requester, and identify the same routing actor.

    Attributes:
        composition_id: Stable operational identity for the composition thread.
        objective: Exact approved operator-owned research objective.
        specialist_tasks: Ordered bounded work supplied by role-owned builders.
        requested_by: Operator or upstream request that initiated composition.
        actor: Coordinator identity routing every specialist task.
    """

    composition_id: str
    objective: ResearchObjective
    specialist_tasks: tuple[SpecialistTask, ...]
    requested_by: str
    actor: str

    def __post_init__(self) -> None:
        """Validate identity, task bounds, and exact objective attribution."""
        _required_text(self.composition_id, "composition_id")
        _required_text(self.requested_by, "composition requested_by")
        _required_text(self.actor, "composition actor")
        if self.objective.status is not ResearchObjectiveStatus.APPROVED:
            raise ValueError("research composition requires an approved objective")
        if len(self.specialist_tasks) > MAX_COMPOSITION_SPECIALIST_TASKS:
            raise ValueError(
                "research composition exceeds the specialist task limit"
            )
        task_ids = tuple(task.task_id for task in self.specialist_tasks)
        if len(task_ids) != len(set(task_ids)):
            raise ValueError("research composition specialist task IDs must be unique")
        objective_payload = self.objective.to_dict()
        for task in self.specialist_tasks:
            if task.objective.to_dict() != objective_payload:
                raise ValueError(
                    f"specialist task {task.task_id} objective does not match composition"
                )
            if task.requested_by != self.composition_id:
                raise ValueError(
                    f"specialist task {task.task_id} requester must be composition_id"
                )
            if task.actor != self.actor:
                raise ValueError(
                    f"specialist task {task.task_id} actor does not match composition"
                )

    def to_dict(self) -> dict[str, Any]:
        """Serialize the complete bounded caller request into stable plain data."""
        return {
            "composition_id": self.composition_id,
            "objective": self.objective.to_dict(),
            "specialist_tasks": [task.to_dict() for task in self.specialist_tasks],
            "requested_by": self.requested_by,
            "actor": self.actor,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ResearchCompositionRequest:
        """Parse a strict composition request at a JSON-compatible boundary.

        Args:
            payload: Mapping containing the exact objective and explicit tasks.

        Returns:
            Validated immutable composition request.

        Raises:
            ValueError: If fields, task bounds, objective, or attribution differ.
        """
        _reject_unknown_fields(
            payload,
            {
                "composition_id",
                "objective",
                "specialist_tasks",
                "requested_by",
                "actor",
            },
            "research composition request",
        )
        tasks = _mapping_sequence(payload.get("specialist_tasks"), "specialist_tasks")
        return cls(
            composition_id=str(payload.get("composition_id") or ""),
            objective=ResearchObjective.from_dict(
                _mapping(payload.get("objective"), "objective")
            ),
            specialist_tasks=tuple(SpecialistTask.from_dict(item) for item in tasks),
            requested_by=str(payload.get("requested_by") or ""),
            actor=str(payload.get("actor") or ""),
        )


ResearchCompositionStatus = Literal[
    "ready",
    "running",
    "awaiting_prerequisite",
    "awaiting_approval",
    "interrupted",
    "completed",
    "blocked",
    "failed",
]
"""Lifecycle values exposed by resumable research composition."""


class ResearchCompositionState(TypedDict, total=False):
    """Bounded JSON-safe operational state for one composition thread.

    Attributes:
        composition_id: Stable operational thread identity.
        request_digest: Digest of the exact immutable composition request.
        objective_id: Coordinated objective identity.
        objective_digest: Digest of the exact approved objective.
        task_digests: Exact task IDs mapped to their original content digests.
        accepted_specialist_results: Validated completed-task receipts.
        last_specialist_result: Bounded latest terminal task summary and refs.
        protocol_id: Observed protocol identity after operator input.
        protocol_design_digest: Digest excluding lifecycle decision fields.
        accepted_protocol_digest: Exact approved protocol digest, once accepted.
        protocol_proposal_ref: Canonical immutable proposal used by composition.
        protocol_proposal_digest: Exact proposal payload digest.
        decision: Latest bounded Coordinator decision.
        workflow_id: Stable child workflow identity, when selected.
        plan_id: Deterministically selected workflow plan identity.
        outcome_ref: Canonical terminal workflow-outcome reference.
        outcome_digest: Digest of the exact canonical terminal outcome.
        transition_count: Number of checkpointed composition transitions.
        status: Current composition lifecycle state.
        public_status: Operator-facing bounded status.
        prerequisites: Unresolved prerequisite payloads.
        warnings: Structured non-fatal issues.
        blockers: Structured terminal blockers.
        errors: Structured boundary or execution failures.
    """

    composition_id: str
    request_digest: str
    objective_id: str
    objective_digest: str
    task_digests: dict[str, str]
    accepted_specialist_results: list[dict[str, Any]]
    last_specialist_result: dict[str, Any]
    protocol_id: str
    protocol_design_digest: str
    accepted_protocol_digest: str
    protocol_proposal_ref: dict[str, Any]
    protocol_proposal_digest: str
    decision: dict[str, Any]
    workflow_id: str
    plan_id: str
    outcome_ref: dict[str, Any]
    outcome_digest: str
    transition_count: int
    status: ResearchCompositionStatus
    public_status: str
    prerequisites: list[dict[str, Any]]
    warnings: list[dict[str, Any]]
    blockers: list[dict[str, Any]]
    errors: list[dict[str, Any]]


def research_composition_digest(request: ResearchCompositionRequest) -> str:
    """Return the stable content digest retained by a composition checkpoint."""
    return json_payload_hash(request.to_dict())


def protocol_digest(protocol: ExperimentProtocol) -> str:
    """Return the exact digest pinned after an approved protocol is accepted."""
    return json_payload_hash(protocol.to_dict())


def protocol_design_digest(protocol: ExperimentProtocol) -> str:
    """Hash protocol design while excluding approval lifecycle decisions.

    This permits the same proposed protocol to advance to approved status on one
    composition thread. Strategy, risk, data, cost, optimisation, robustness,
    question, limit, assumption, requester, and approval-subject changes still
    alter the digest and fail as protocol drift.
    """
    return experiment_protocol_design_digest(protocol)


def build_research_composition_initial_state(
    request: ResearchCompositionRequest,
) -> ResearchCompositionState:
    """Build the bounded initial checkpoint state for a composition request.

    Args:
        request: Validated exact composition input retained outside checkpointing.

    Returns:
        Initial state containing identities and digests but no task payloads.
    """
    return {
        "composition_id": request.composition_id,
        "request_digest": research_composition_digest(request),
        "objective_id": request.objective.objective_id,
        "objective_digest": json_payload_hash(request.objective.to_dict()),
        "task_digests": {
            task.task_id: specialist_task_digest(task)
            for task in request.specialist_tasks
        },
        "accepted_specialist_results": [],
        "last_specialist_result": {},
        "protocol_id": "",
        "protocol_design_digest": "",
        "accepted_protocol_digest": "",
        "protocol_proposal_ref": {},
        "protocol_proposal_digest": "",
        "decision": {},
        "workflow_id": "",
        "plan_id": "",
        "outcome_ref": {},
        "outcome_digest": "",
        "transition_count": 0,
        "status": "ready",
        "public_status": "ready",
        "prerequisites": [],
        "warnings": [],
        "blockers": [],
        "errors": [],
    }


def research_composition_thread_config(
    composition_id: str,
) -> dict[str, Any]:
    """Build an isolated LangGraph thread configuration for composition."""
    return {
        "configurable": {
            "thread_id": f"research_composition:{_required_text(composition_id, 'composition_id')}"
        }
    }


def research_composition_public_state(
    state: Mapping[str, Any],
) -> dict[str, Any]:
    """Project checkpoint state to the stable caller-visible result surface.

    Args:
        state: Current internal composition checkpoint state.

    Returns:
        Bounded identities, receipts, decisions, refs, status, and issues.
    """
    return {
        "composition_id": str(state.get("composition_id") or ""),
        "objective_id": str(state.get("objective_id") or ""),
        "accepted_specialist_results": [
            dict(item)
            for item in _mapping_sequence(
                state.get("accepted_specialist_results"),
                "accepted_specialist_results",
            )
        ],
        "last_specialist_result": dict(
            _mapping_or_empty(state.get("last_specialist_result"))
        ),
        "protocol_id": str(state.get("protocol_id") or ""),
        "protocol_proposal_ref": dict(
            _mapping_or_empty(state.get("protocol_proposal_ref"))
        ),
        "decision": dict(_mapping_or_empty(state.get("decision"))),
        "workflow_id": str(state.get("workflow_id") or ""),
        "plan_id": str(state.get("plan_id") or ""),
        "outcome_ref": dict(_mapping_or_empty(state.get("outcome_ref"))),
        "transition_count": int(state.get("transition_count", 0)),
        "status": str(state.get("status") or "failed"),
        "public_status": str(state.get("public_status") or "failed_validation"),
        "prerequisites": [
            dict(item)
            for item in _mapping_sequence(
                state.get("prerequisites"),
                "prerequisites",
            )
        ],
        "warnings": [
            dict(item)
            for item in _mapping_sequence(state.get("warnings"), "warnings")
        ],
        "blockers": [
            dict(item)
            for item in _mapping_sequence(state.get("blockers"), "blockers")
        ],
        "errors": [
            dict(item)
            for item in _mapping_sequence(state.get("errors"), "errors")
        ],
    }


def _required_text(value: object, label: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{label} is required")
    return normalized


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be a mapping")
    return value


def _mapping_or_empty(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


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


def _reject_unknown_fields(
    payload: Mapping[str, Any],
    allowed: set[str],
    label: str,
) -> None:
    unknown = sorted(set(payload).difference(allowed))
    if unknown:
        raise ValueError(f"{label} contains unknown fields: {', '.join(unknown)}")
