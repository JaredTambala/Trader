"""Deterministic UJ-04 lifecycle qualification fixtures.

The fixture composes the public event and checkpoint projections used by the
runtime. It intentionally retains no prompts, model messages, tool payloads,
or complete checkpoint state. Each case has stable session, branch, run, and
artifact identities so a fresh process can replay and qualify the same public
trajectory.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Any, Literal

from trader_agents import (
    AgentErrorCategory,
    AgentEventCorrelation,
    AgentEventName,
    AgentObservabilityEvent,
    AgentEventError,
    RetainedTrajectory,
    RetainedTrajectorySink,
    build_agent_checkpoint_state,
    build_agent_observability_event,
    first_slice_tool_catalogue,
)
from trader_agents.model_runtime.profiles import DEVELOPMENT_MODEL_PROFILE_ID


SessionOutcome = Literal["completed", "failed", "cancelled"]
QUALIFICATION_OUTCOMES: tuple[SessionOutcome, ...] = (
    "completed",
    "failed",
    "cancelled",
)
QUALIFICATION_PROGRAM_ID = "research-coordinator-v7"
QUALIFICATION_MODEL_PROFILE_ID = DEVELOPMENT_MODEL_PROFILE_ID
QUALIFICATION_TOOL_CATALOG_ID = first_slice_tool_catalogue().catalogue_id


@dataclass(frozen=True)
class SessionQualificationIdentity:
    """Stable public identities joining one qualification trajectory."""

    session_id: str
    root_branch_id: str
    run_id: str
    artifact_id: str

    @property
    def artifact_uri(self) -> str:
        """Return the exact canonical URI for the retained decision artifact."""
        return f"research://postgres/agent_decision_receipt/{self.artifact_id}"


def build_session_qualification_fixture(
    *,
    outcome: SessionOutcome = "completed",
    include_checkpoint: bool = True,
    storage_path: Path | str | None = None,
) -> RetainedTrajectory:
    """Build one isolated public UJ-04 session trajectory.

    Args:
        outcome: Terminal public result represented by the trajectory.
        include_checkpoint: Whether the resume checkpoint is retained. Setting
            this false produces the explicit missing-checkpoint qualification
            case while preserving the terminal public event.
        storage_path: Optional atomic JSON path for fresh-process replay.

    Returns:
        Detached public events and checkpoint projections for one session.

    Raises:
        ValueError: If ``outcome`` is not a supported terminal state.
    """
    if outcome not in QUALIFICATION_OUTCOMES:
        raise ValueError(f"unsupported qualification outcome: {outcome}")
    identity = _identity(outcome)
    sink = RetainedTrajectorySink(storage_path=storage_path)
    initial = build_agent_checkpoint_state(
        session_id=identity.session_id,
        session_digest=sha256(identity.session_id.encode("utf-8")).hexdigest(),
        branch_id=identity.root_branch_id,
        coordinator_program_id=QUALIFICATION_PROGRAM_ID,
        model_profile_id=QUALIFICATION_MODEL_PROFILE_ID,
        tool_catalog_id=QUALIFICATION_TOOL_CATALOG_ID,
    )
    if include_checkpoint:
        sink.retain_checkpoint(initial, process_instance_id="process-start")

    for event in (
        _event(
            identity,
            AgentEventName.SESSION_STARTED,
            process_id="process-start",
            sequence=1,
            timestamp_offset=0,
            fields={"lifecycle_operation": "start", "recovered": False},
        ),
        _event(
            identity,
            AgentEventName.DELEGATION_STARTED,
            process_id="process-start",
            branch_id=f"{identity.root_branch_id}:data",
            sequence=2,
            timestamp_offset=1,
            delegation_id=f"{identity.run_id}:data",
            attempt_id=f"{identity.run_id}:data:attempt-1",
            fields={"role": "data_research", "task_id": "data"},
        ),
        _event(
            identity,
            AgentEventName.DELEGATION_STARTED,
            process_id="process-start",
            branch_id=f"{identity.root_branch_id}:strategy",
            sequence=3,
            timestamp_offset=2,
            delegation_id=f"{identity.run_id}:strategy",
            attempt_id=f"{identity.run_id}:strategy:attempt-1",
            fields={"role": "strategy_engineering", "task_id": "strategy"},
        ),
    ):
        sink.emit(event)
    if include_checkpoint:
        sink.emit(
            _event(
                identity,
                AgentEventName.CHECKPOINT_SAVED,
                process_id="process-start",
                sequence=4,
                transition_sequence=1,
                timestamp_offset=3,
                fields={"status": "running", "phase": "delegate"},
            )
        )

    sink.emit(
        _event(
            identity,
            AgentEventName.DECISION_COMMITTED,
            process_id="process-start",
            sequence=5 if include_checkpoint else 4,
            transition_sequence=2,
            timestamp_offset=3 if include_checkpoint else 4,
            fields={
                "decision_status": outcome,
                "decision_receipt_ref": identity.artifact_uri,
            },
        )
    )

    terminal_state = dict(initial)
    terminal_state.update(
        {
            "next_sequence": 2,
            "status": outcome,
            "phase": "terminal",
            "decision_receipt_ref": {
                "artifact_type": "agent_decision_receipt",
                "artifact_id": identity.artifact_id,
                "domain_owner": "research_coordinator",
                "uri": identity.artifact_uri,
            },
            "evidence_refs": [
                {
                    "artifact_type": "agent_decision_receipt",
                    "artifact_id": identity.artifact_id,
                    "domain_owner": "research_coordinator",
                    "uri": identity.artifact_uri,
                }
            ],
        }
    )
    if include_checkpoint:
        sink.retain_checkpoint(terminal_state, process_instance_id="process-resume")
        sink.emit(
            _event(
                identity,
                AgentEventName.CHECKPOINT_RECOVERED,
                process_id="process-resume",
                sequence=1,
                transition_sequence=1,
                timestamp_offset=4,
                fields={"status": outcome, "phase": "terminal"},
            )
        )
        sink.emit(
            _event(
                identity,
                AgentEventName.SESSION_RESUMED,
                process_id="process-resume",
                sequence=2,
                timestamp_offset=5,
                fields={"lifecycle_operation": "resume", "recovered": True},
            )
        )

    terminal_name = {
        "completed": AgentEventName.SESSION_COMPLETED,
        "failed": AgentEventName.SESSION_FAILED,
        "cancelled": AgentEventName.SESSION_CANCELLED,
    }[outcome]
    sink.emit(
        _event(
            identity,
            terminal_name,
            process_id="process-resume" if include_checkpoint else "process-start",
            sequence=3 if include_checkpoint else 5,
            timestamp_offset=6 if include_checkpoint else 5,
            fields={
                "status": outcome,
                "run_id": identity.run_id,
                "artifact_id": identity.artifact_id,
                "decision_receipt_ref": identity.artifact_uri,
            },
            error=(
                AgentEventError(
                    code="research_session_failed",
                    category=AgentErrorCategory.INTERNAL,
                    message="The qualification session failed before a usable conclusion.",
                )
                if outcome == "failed"
                else None
            ),
        )
    )
    return sink.snapshot()


def qualification_identity(outcome: SessionOutcome) -> SessionQualificationIdentity:
    """Return the stable identity set used by one terminal outcome case."""
    if outcome not in QUALIFICATION_OUTCOMES:
        raise ValueError(f"unsupported qualification outcome: {outcome}")
    return _identity(outcome)


def _identity(outcome: SessionOutcome) -> SessionQualificationIdentity:
    """Build deterministic identities without process or clock entropy."""
    suffix = f"{outcome}-uj04"
    return SessionQualificationIdentity(
        session_id=f"session-{suffix}",
        root_branch_id=f"branch-{suffix}",
        run_id=f"run-{suffix}",
        artifact_id=f"decision-{suffix}",
    )


def _event(
    identity: SessionQualificationIdentity,
    name: AgentEventName,
    *,
    process_id: str,
    sequence: int,
    timestamp_offset: int,
    fields: dict[str, Any],
    branch_id: str | None = None,
    delegation_id: str | None = None,
    attempt_id: str | None = None,
    transition_sequence: int | None = None,
    error: AgentEventError | None = None,
) -> AgentObservabilityEvent:
    """Build one validated public event with stable identity fields."""
    return build_agent_observability_event(
        name=name,
        timestamp=datetime(2026, 10, 5, 12, tzinfo=UTC)
        + timedelta(seconds=timestamp_offset),
        sequence=sequence,
        correlation=AgentEventCorrelation(
            session_id=identity.session_id,
            branch_id=branch_id or identity.root_branch_id,
            role=(
                "research_coordinator"
                if branch_id is None or branch_id == identity.root_branch_id
                else branch_id.rsplit(":", 1)[-1]
            ),
            program_id=QUALIFICATION_PROGRAM_ID,
            model_profile_id=QUALIFICATION_MODEL_PROFILE_ID,
            tool_catalog_id=QUALIFICATION_TOOL_CATALOG_ID,
            process_instance_id=process_id,
            delegation_id=delegation_id,
            attempt_id=attempt_id,
            transition_sequence=transition_sequence,
        ),
        fields={
            "run_id": identity.run_id,
            "artifact_id": identity.artifact_id,
            **fields,
        },
        error=error,
    )
