"""Deterministic retained trajectory fixture for public observability qualification."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from trader_agents import (
    AgentEventCorrelation,
    AgentEventName,
    AgentObservabilityEvent,
    RetainedTrajectory,
    RetainedTrajectorySink,
    build_agent_checkpoint_state,
    build_agent_observability_event,
    first_slice_tool_catalogue,
)
from trader_agents.model_runtime.profiles import DEVELOPMENT_MODEL_PROFILE_ID


SESSION_ID = "trajectory-session"
ROOT_BRANCH_ID = "branch-root"
DATA_BRANCH_ID = "branch-data"
STRATEGY_BRANCH_ID = "branch-strategy"
COORDINATOR_PROGRAM_ID = "research-coordinator-v7"
MODEL_PROFILE_ID = DEVELOPMENT_MODEL_PROFILE_ID
TOOL_CATALOG_ID = first_slice_tool_catalogue().catalogue_id
DECISION_RECEIPT_URI = "research://postgres/agent_decision_receipt/trajectory-decision"


def build_retained_trajectory_fixture() -> RetainedTrajectory:
    """Build a complete two-process trajectory with concurrent branches."""
    sink = RetainedTrajectorySink()
    first_state = build_agent_checkpoint_state(
        session_id=SESSION_ID,
        session_digest="session-digest",
        branch_id=ROOT_BRANCH_ID,
        coordinator_program_id=COORDINATOR_PROGRAM_ID,
        model_profile_id=MODEL_PROFILE_ID,
        tool_catalog_id=TOOL_CATALOG_ID,
    )
    sink.retain_checkpoint(first_state, process_instance_id="process-start")

    for event in (
        _event(
            AgentEventName.SESSION_STARTED,
            process_id="process-start",
            branch_id=ROOT_BRANCH_ID,
            sequence=1,
            timestamp_offset=0,
            fields={"lifecycle_operation": "start", "recovered": False},
        ),
        _event(
            AgentEventName.DELEGATION_STARTED,
            process_id="process-start",
            branch_id=DATA_BRANCH_ID,
            sequence=2,
            timestamp_offset=1,
            delegation_id="delegation-data",
            attempt_id="attempt-data",
            fields={"role": "data_research", "task_id": "data"},
        ),
        _event(
            AgentEventName.DELEGATION_STARTED,
            process_id="process-start",
            branch_id=STRATEGY_BRANCH_ID,
            sequence=3,
            timestamp_offset=2,
            delegation_id="delegation-strategy",
            attempt_id="attempt-strategy",
            fields={"role": "strategy_engineering", "task_id": "strategy"},
        ),
        _event(
            AgentEventName.CHECKPOINT_SAVED,
            process_id="process-start",
            branch_id=ROOT_BRANCH_ID,
            sequence=4,
            transition_sequence=1,
            timestamp_offset=3,
            fields={
                "checkpoint_digest": sink.snapshot().checkpoints[0].checkpoint_digest,
                "transition_sequence": 1,
                "status": "running",
                "phase": "delegate",
            },
        ),
        _event(
            AgentEventName.DECISION_COMMITTED,
            process_id="process-start",
            branch_id=ROOT_BRANCH_ID,
            sequence=5,
            transition_sequence=2,
            timestamp_offset=4,
            fields={"decision_status": "conclude", "summary": "Evidence joined."},
        ),
    ):
        sink.emit(event)

    recovered_state = dict(first_state)
    recovered_state["next_sequence"] = 2
    recovered_state["status"] = "completed"
    recovered_state["phase"] = "terminal"
    recovered_state["decision_receipt_ref"] = {
        "artifact_type": "agent_decision_receipt",
        "artifact_id": "trajectory-decision",
        "domain_owner": "research_coordinator",
        "uri": DECISION_RECEIPT_URI,
    }
    sink.retain_checkpoint(recovered_state, process_instance_id="process-resume")
    for event in (
        _event(
            AgentEventName.CHECKPOINT_RECOVERED,
            process_id="process-resume",
            branch_id=ROOT_BRANCH_ID,
            sequence=1,
            transition_sequence=2,
            timestamp_offset=5,
            fields={
                "checkpoint_digest": sink.snapshot().checkpoints[-1].checkpoint_digest,
                "transition_sequence": 2,
                "status": "completed",
                "phase": "terminal",
            },
        ),
        _event(
            AgentEventName.SESSION_RESUMED,
            process_id="process-resume",
            branch_id=ROOT_BRANCH_ID,
            sequence=2,
            timestamp_offset=6,
            fields={"lifecycle_operation": "resume", "recovered": True},
        ),
        _event(
            AgentEventName.SESSION_COMPLETED,
            process_id="process-resume",
            branch_id=ROOT_BRANCH_ID,
            sequence=3,
            timestamp_offset=7,
            fields={
                "status": "completed",
                "decision_receipt_ref": DECISION_RECEIPT_URI,
            },
        ),
    ):
        sink.emit(event)
    return sink.snapshot()


def _event(
    name: AgentEventName,
    *,
    process_id: str,
    branch_id: str,
    sequence: int,
    timestamp_offset: int,
    fields: dict[str, Any],
    delegation_id: str | None = None,
    attempt_id: str | None = None,
    transition_sequence: int | None = None,
) -> AgentObservabilityEvent:
    """Build one fixture event with exact process and branch identity."""
    return build_agent_observability_event(
        name=name,
        timestamp=datetime(2026, 10, 4, 12, tzinfo=UTC)
        + timedelta(seconds=timestamp_offset),
        sequence=sequence,
        correlation=AgentEventCorrelation(
            session_id=SESSION_ID,
            branch_id=branch_id,
            role="research_coordinator" if branch_id == ROOT_BRANCH_ID else branch_id,
            program_id=COORDINATOR_PROGRAM_ID,
            model_profile_id=MODEL_PROFILE_ID,
            tool_catalog_id=TOOL_CATALOG_ID,
            process_instance_id=process_id,
            delegation_id=delegation_id,
            attempt_id=attempt_id,
            transition_sequence=transition_sequence,
        ),
        fields=fields,
    )
