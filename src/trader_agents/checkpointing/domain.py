"""Bounded operational state for resumable research workflows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence, TypedDict

from trader_research.foundation import json_payload_hash, parse_research_artifact_uri
from trader_research.governance import (
    ArtifactReportRef,
    ResearchIssue,
    SpecialistHandoff,
    WorkflowPlan,
    WorkflowPlanStatus,
    WorkflowStepResult,
)


MAX_WORKFLOW_STEPS = 128
MAX_STEP_ATTEMPTS = 256
MAX_HANDOFF_SUMMARIES = 64
MAX_CHECKPOINT_ISSUES = 128


class WorkflowCheckpointState(TypedDict, total=False):
    """LangGraph state that is operational and never canonical evidence."""

    workflow_id: str
    plan_id: str
    plan_digest: str
    requested_by: str
    actor: str
    current_step_index: int
    next_attempt: int
    pending_step_id: str
    step_attempts: list[dict[str, Any]]
    handoff_summaries: list[dict[str, Any]]
    processed_result_digests: dict[str, str]
    status: str
    public_status: str
    warnings: list[dict[str, Any]]
    blockers: list[dict[str, Any]]
    errors: list[dict[str, Any]]


@dataclass(frozen=True)
class OperationalHandoffSummary:
    """Checkpoint-safe specialist handoff containing a canonical ref only."""

    handoff_id: str
    artifact_ref: ArtifactReportRef
    producer_tool: str
    requested_by: str
    actor: str
    warnings: tuple[ResearchIssue, ...] = ()
    blockers: tuple[ResearchIssue, ...] = ()

    @classmethod
    def from_handoff(
        cls,
        handoff: SpecialistHandoff,
    ) -> "OperationalHandoffSummary":
        """Reduce a specialist handoff to canonical identity and bounded issues.

        Raises:
            ValueError: If the handoff does not contain a canonical Postgres URI.
        """
        if handoff.artifact_uri is None:
            raise ValueError(
                "checkpoint handoffs require a canonical artifact_uri; "
                "payload-only handoffs cannot be checkpointed"
            )
        artifact_type, artifact_id = parse_research_artifact_uri(
            handoff.artifact_uri
        )
        return cls(
            handoff_id=handoff.handoff_id,
            artifact_ref=ArtifactReportRef(
                artifact_id=artifact_id,
                artifact_type=artifact_type,
                domain_owner=handoff.domain_owner,
                uri=handoff.artifact_uri,
            ),
            producer_tool=handoff.producer_tool,
            requested_by=handoff.requested_by,
            actor=handoff.actor,
            warnings=handoff.warnings,
            blockers=handoff.blockers,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize the bounded handoff summary."""
        return {
            "handoff_id": self.handoff_id,
            "artifact_ref": self.artifact_ref.to_dict(),
            "producer_tool": self.producer_tool,
            "requested_by": self.requested_by,
            "actor": self.actor,
            "warnings": [item.to_dict() for item in self.warnings],
            "blockers": [item.to_dict() for item in self.blockers],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "OperationalHandoffSummary":
        """Parse a bounded handoff summary."""
        return cls(
            handoff_id=_required_text(payload.get("handoff_id"), "handoff_id"),
            artifact_ref=ArtifactReportRef.from_dict(
                _mapping(payload.get("artifact_ref"))
            ),
            producer_tool=_required_text(
                payload.get("producer_tool"),
                "producer_tool",
            ),
            requested_by=_required_text(
                payload.get("requested_by"),
                "requested_by",
            ),
            actor=_required_text(payload.get("actor"), "actor"),
            warnings=tuple(
                ResearchIssue.from_dict(item)
                for item in _mapping_sequence(payload.get("warnings"))
            ),
            blockers=tuple(
                ResearchIssue.from_dict(item)
                for item in _mapping_sequence(payload.get("blockers"))
            ),
        )


@dataclass(frozen=True)
class CheckpointStepSummary:
    """Bounded operational summary of one externally executed step attempt."""

    result_id: str
    step_id: str
    attempt: int
    command: str
    status: str
    retry: str
    produced_artifact_refs: tuple[ArtifactReportRef, ...] = ()
    warnings: tuple[ResearchIssue, ...] = ()
    blockers: tuple[ResearchIssue, ...] = ()

    @classmethod
    def from_result(cls, result: WorkflowStepResult) -> "CheckpointStepSummary":
        """Drop arbitrary public result data before checkpoint persistence."""
        return cls(
            result_id=result.result_id,
            step_id=result.step_id,
            attempt=result.attempt,
            command=result.command,
            status=result.status.value,
            retry=result.retry.value,
            produced_artifact_refs=result.produced_artifact_refs,
            warnings=result.warnings,
            blockers=result.blockers,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize this bounded attempt summary."""
        return {
            "result_id": self.result_id,
            "step_id": self.step_id,
            "attempt": self.attempt,
            "command": self.command,
            "status": self.status,
            "retry": self.retry,
            "produced_artifact_refs": [
                item.to_dict() for item in self.produced_artifact_refs
            ],
            "warnings": [item.to_dict() for item in self.warnings],
            "blockers": [item.to_dict() for item in self.blockers],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CheckpointStepSummary":
        """Parse a checkpoint step summary."""
        return cls(
            result_id=_required_text(payload.get("result_id"), "result_id"),
            step_id=_required_text(payload.get("step_id"), "step_id"),
            attempt=int(payload.get("attempt", 0)),
            command=_required_text(payload.get("command"), "command"),
            status=_required_text(payload.get("status"), "status"),
            retry=_required_text(payload.get("retry"), "retry"),
            produced_artifact_refs=tuple(
                ArtifactReportRef.from_dict(item)
                for item in _mapping_sequence(
                    payload.get("produced_artifact_refs")
                )
            ),
            warnings=tuple(
                ResearchIssue.from_dict(item)
                for item in _mapping_sequence(payload.get("warnings"))
            ),
            blockers=tuple(
                ResearchIssue.from_dict(item)
                for item in _mapping_sequence(payload.get("blockers"))
            ),
        )


def build_workflow_checkpoint_state(
    *,
    workflow_id: str,
    plan: WorkflowPlan,
    handoffs: Sequence[SpecialistHandoff] = (),
) -> WorkflowCheckpointState:
    """Build the bounded initial state for one workflow thread.

    Args:
        workflow_id: Unique operational run identity and LangGraph thread ID.
        plan: Ready ORCH-1 workflow plan used to compile the graph.
        handoffs: Canonical-ref specialist handoffs available at start.

    Returns:
        JSON-safe operational state without complete artifact payloads.
    """
    workflow_id = _required_text(workflow_id, "workflow_id")
    if plan.status is not WorkflowPlanStatus.READY:
        raise ValueError("checkpointed workflows require a ready workflow plan")
    if len(plan.steps) > MAX_WORKFLOW_STEPS:
        raise ValueError(
            f"checkpointed workflows support at most {MAX_WORKFLOW_STEPS} steps"
        )
    if len(handoffs) > MAX_HANDOFF_SUMMARIES:
        raise ValueError(
            "checkpointed workflows support at most "
            f"{MAX_HANDOFF_SUMMARIES} handoffs"
        )
    summaries = [
        OperationalHandoffSummary.from_handoff(item).to_dict()
        for item in handoffs
    ]
    return {
        "workflow_id": workflow_id,
        "plan_id": plan.plan_id,
        "plan_digest": workflow_plan_digest(plan),
        "requested_by": plan.requested_by,
        "actor": plan.actor,
        "current_step_index": 0,
        "next_attempt": 1,
        "pending_step_id": "",
        "step_attempts": [],
        "handoff_summaries": summaries,
        "processed_result_digests": {},
        "status": "ready",
        "public_status": "ready",
        "warnings": [],
        "blockers": [],
        "errors": [],
    }


def workflow_plan_digest(plan: WorkflowPlan) -> str:
    """Return the content digest that a checkpointed workflow must retain."""
    return json_payload_hash(plan.to_dict())


def workflow_thread_config(workflow_id: str) -> dict[str, Any]:
    """Build the LangGraph configuration for one workflow checkpoint thread."""
    return {"configurable": {"thread_id": _required_text(workflow_id, "workflow_id")}}


def workflow_public_state(
    state: Mapping[str, Any],
) -> dict[str, Any]:
    """Return the bounded operator-visible projection of checkpoint state."""
    return {
        "workflow_id": str(state.get("workflow_id") or ""),
        "plan_id": str(state.get("plan_id") or ""),
        "status": str(state.get("status") or ""),
        "public_status": str(state.get("public_status") or ""),
        "pending_step_id": str(state.get("pending_step_id") or ""),
        "next_attempt": int(state.get("next_attempt", 0)),
        "step_attempts": [
            CheckpointStepSummary.from_dict(item).to_dict()
            for item in _mapping_sequence(state.get("step_attempts"))
        ],
        "handoff_summaries": [
            OperationalHandoffSummary.from_dict(item).to_dict()
            for item in _mapping_sequence(state.get("handoff_summaries"))
        ],
        "warnings": list(_mapping_sequence(state.get("warnings"))),
        "blockers": list(_mapping_sequence(state.get("blockers"))),
        "errors": list(_mapping_sequence(state.get("errors"))),
    }


def result_digest(result: WorkflowStepResult) -> str:
    """Return a digest used to distinguish exact retries from conflicts."""
    return json_payload_hash(result.to_dict())


def validate_checkpoint_bounds(state: Mapping[str, Any]) -> None:
    """Reject checkpoint state that exceeds the public bounded-state policy."""
    if len(_sequence(state.get("step_attempts"))) > MAX_STEP_ATTEMPTS:
        raise ValueError(
            f"checkpoint step attempts exceed the limit of {MAX_STEP_ATTEMPTS}"
        )
    if len(_sequence(state.get("handoff_summaries"))) > MAX_HANDOFF_SUMMARIES:
        raise ValueError(
            f"checkpoint handoffs exceed the limit of {MAX_HANDOFF_SUMMARIES}"
        )
    issue_count = sum(
        len(_sequence(state.get(key)))
        for key in ("warnings", "blockers", "errors")
    )
    if issue_count > MAX_CHECKPOINT_ISSUES:
        raise ValueError(
            f"checkpoint issues exceed the limit of {MAX_CHECKPOINT_ISSUES}"
        )


def _required_text(value: object, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{label} is required")
    return text


def _mapping(value: object) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return {}


def _sequence(value: object) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return value
    return ()


def _mapping_sequence(value: object) -> tuple[Mapping[str, Any], ...]:
    return tuple(item for item in _sequence(value) if isinstance(item, Mapping))
