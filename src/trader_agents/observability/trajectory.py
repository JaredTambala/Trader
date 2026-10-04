"""Retained public agent trajectories and qualification verification.

The runtime event stream and checkpoint projection are intentionally separate
from canonical research evidence. This module provides a small retention
boundary for a qualification fixture (or a future read adapter): it accepts
only validated :class:`AgentObservabilityEvent` values and the redacted
``agent_public_state`` checkpoint projection, then verifies the identities,
branch ownership, restart markers, redaction, and terminal lineage needed to
call a trajectory queryable evidence.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
import copy
import json
import os
from pathlib import Path
import tempfile
from threading import Lock
from typing import Any

from trader_agents.checkpointing.domain import (
    agent_checkpoint_digest,
    agent_public_state,
    validate_agent_checkpoint_state,
)

from .events import (
    AgentEventName,
    AgentObservabilityEvent,
    validate_agent_event_stream,
    validate_observability_fields,
)


_TERMINAL_EVENTS = frozenset(
    {
        AgentEventName.SESSION_COMPLETED,
        AgentEventName.SESSION_FAILED,
        AgentEventName.SESSION_CANCELLED,
    }
)


class RetainedTrajectoryUnavailable(RuntimeError):
    """Raised when a retained trajectory sink is deliberately unavailable."""


@dataclass(frozen=True)
class RetainedCheckpoint:
    """One redacted checkpoint projection retained with its process identity.

    Attributes:
        process_instance_id: Process that observed and retained the checkpoint.
        checkpoint_digest: Digest of the validated operational checkpoint.
        transition_sequence: Checkpoint transition represented by the state.
        state: Operator-visible state projection with no private payloads.
    """

    process_instance_id: str
    checkpoint_digest: str
    transition_sequence: int
    state: Mapping[str, Any]

    def __post_init__(self) -> None:
        """Validate the bounded projection and immutable identity fields."""
        if not self.process_instance_id.strip():
            raise ValueError("retained checkpoint process identity is required")
        if len(self.checkpoint_digest) != 64 or any(
            character not in "0123456789abcdef" for character in self.checkpoint_digest
        ):
            raise ValueError("retained checkpoint digest must be lowercase SHA-256")
        if isinstance(self.transition_sequence, bool) or self.transition_sequence <= 0:
            raise ValueError("retained checkpoint transition sequence must be positive")
        if not isinstance(self.state, Mapping):
            raise ValueError("retained checkpoint state must be an object")
        # The state is already projected by ``agent_public_state`` at the
        # retention boundary. Re-run the public validator to protect callers
        # that construct a record directly from a fixture.
        validate_observability_fields(self.state, label="retained checkpoint state")


@dataclass(frozen=True)
class RetainedTrajectory:
    """Query result containing public events and redacted checkpoint records."""

    events: tuple[AgentObservabilityEvent, ...]
    checkpoints: tuple[RetainedCheckpoint, ...]

    def for_session(self, session_id: str) -> "RetainedTrajectory":
        """Return only records correlated to ``session_id``."""
        identity = str(session_id).strip()
        if not identity:
            raise ValueError("trajectory session_id is required")
        events = tuple(
            event
            for event in self.events
            if event.correlation.session_id == identity
        )
        checkpoints = tuple(
            checkpoint
            for checkpoint in self.checkpoints
            if str(checkpoint.state.get("session_id") or "") == identity
        )
        return RetainedTrajectory(events=events, checkpoints=checkpoints)


@dataclass
class RetainedTrajectorySink:
    """Thread-safe retained sink for a public qualification trajectory.

    This sink deliberately retains no raw event source, model message, prompt,
    credential, or checkpoint input. ``retain_checkpoint`` validates and
    projects a checkpoint before storing it. Setting ``available`` to ``False``
    models a sink outage and fails closed without appending a partial record.
    """

    available: bool = True
    storage_path: Path | str | None = None
    _events: list[AgentObservabilityEvent] = field(default_factory=list, init=False)
    _checkpoints: list[RetainedCheckpoint] = field(default_factory=list, init=False)
    _event_positions: set[tuple[str, int]] = field(default_factory=set, init=False)
    _lock: Lock = field(default_factory=Lock, init=False, repr=False)

    def __post_init__(self) -> None:
        """Load an existing detached public snapshot when a path is supplied."""
        if self.storage_path is None:
            return
        self.storage_path = Path(self.storage_path)
        self._load_storage()

    def emit(self, event: AgentObservabilityEvent) -> None:
        """Retain one validated event, rejecting outages and duplicate positions."""
        if not self.available:
            raise RetainedTrajectoryUnavailable("retained trajectory sink is unavailable")
        validated = AgentObservabilityEvent.model_validate(event.model_dump(mode="python"))
        position = validated.stream_position
        with self._lock:
            if position in self._event_positions:
                raise ValueError(
                    "retained trajectory already contains event stream position "
                    f"{position[0]}:{position[1]}"
                )
            # Keep a detached copy so caller mutation cannot alter retained
            # evidence after sink validation.
            retained = AgentObservabilityEvent.model_validate(
                validated.model_dump(mode="python")
            )
            self._events.append(retained)
            self._event_positions.add(position)
            try:
                self._persist_locked()
            except Exception:
                self._events.pop()
                self._event_positions.remove(position)
                raise

    def retain_checkpoint(
        self,
        state: Mapping[str, Any],
        *,
        process_instance_id: str,
    ) -> RetainedCheckpoint:
        """Project and retain one validated operational checkpoint.

        Args:
            state: Complete checkpoint state returned by LangGraph.
            process_instance_id: Process that read or wrote this checkpoint.

        Returns:
            Detached redacted checkpoint record retained by this sink.
        """
        if not self.available:
            raise RetainedTrajectoryUnavailable("retained trajectory sink is unavailable")
        validate_agent_checkpoint_state(state)
        public_state = agent_public_state(state)
        digest = agent_checkpoint_digest(state)
        sequence = state.get("next_sequence", 1)
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence <= 0:
            raise ValueError("checkpoint next_sequence must be positive")
        record = RetainedCheckpoint(
            process_instance_id=str(process_instance_id).strip(),
            checkpoint_digest=digest,
            transition_sequence=sequence,
            state=_detached_json(public_state),
        )
        key = (
            str(record.state.get("session_id") or ""),
            str(record.state.get("branch_id") or ""),
            record.transition_sequence,
            record.checkpoint_digest,
        )
        with self._lock:
            if any(
                (
                    str(existing.state.get("session_id") or ""),
                    str(existing.state.get("branch_id") or ""),
                    existing.transition_sequence,
                    existing.checkpoint_digest,
                )
                == key
                for existing in self._checkpoints
            ):
                raise ValueError("retained trajectory already contains checkpoint")
            self._checkpoints.append(record)
            try:
                self._persist_locked()
            except Exception:
                self._checkpoints.pop()
                raise
        return record

    def snapshot(self) -> RetainedTrajectory:
        """Return a detached queryable trajectory snapshot."""
        with self._lock:
            events = tuple(
                AgentObservabilityEvent.model_validate(
                    event.model_dump(mode="python")
                )
                for event in self._events
            )
            checkpoints = tuple(
                RetainedCheckpoint(
                    process_instance_id=checkpoint.process_instance_id,
                    checkpoint_digest=checkpoint.checkpoint_digest,
                    transition_sequence=checkpoint.transition_sequence,
                    state=_detached_json(checkpoint.state),
                )
                for checkpoint in self._checkpoints
            )
        return RetainedTrajectory(events=events, checkpoints=checkpoints)

    def _load_storage(self) -> None:
        """Load and validate one atomically-written public snapshot."""
        path = self._storage_file()
        if not path.exists():
            return
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ValueError(f"retained trajectory storage is unreadable: {path}") from exc
        if not isinstance(payload, Mapping) or payload.get("schema_version") != "1":
            raise ValueError("retained trajectory storage has an unsupported schema")
        raw_events = payload.get("events")
        raw_checkpoints = payload.get("checkpoints")
        if not isinstance(raw_events, list) or not isinstance(raw_checkpoints, list):
            raise ValueError("retained trajectory storage must contain event and checkpoint lists")
        events: list[AgentObservabilityEvent] = []
        for raw_event in raw_events:
            if not isinstance(raw_event, Mapping):
                raise ValueError("retained trajectory storage contains an invalid event")
            events.append(AgentObservabilityEvent.model_validate(raw_event))
        checkpoints: list[RetainedCheckpoint] = []
        for raw_checkpoint in raw_checkpoints:
            if not isinstance(raw_checkpoint, Mapping):
                raise ValueError("retained trajectory storage contains an invalid checkpoint")
            checkpoints.append(RetainedCheckpoint(**dict(raw_checkpoint)))
        validate_agent_event_stream(events)
        positions = [event.stream_position for event in events]
        if len(set(positions)) != len(positions):
            raise ValueError("retained trajectory storage contains duplicate event positions")
        with self._lock:
            self._events = events
            self._checkpoints = checkpoints
            self._event_positions = set(positions)

    def _storage_file(self) -> Path:
        """Return the configured storage path or raise for memory-only sinks."""
        if self.storage_path is None:  # pragma: no cover - guarded by callers
            raise RuntimeError("retained trajectory sink has no storage path")
        path = Path(self.storage_path)
        if path.exists() and path.is_dir():
            raise ValueError("retained trajectory storage path must be a file")
        return path

    def _persist_locked(self) -> None:
        """Atomically replace the storage document after a successful append."""
        if self.storage_path is None:
            return
        path = self._storage_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": "1",
            "events": [event.model_dump(mode="json") for event in self._events],
            "checkpoints": [
                {
                    "process_instance_id": checkpoint.process_instance_id,
                    "checkpoint_digest": checkpoint.checkpoint_digest,
                    "transition_sequence": checkpoint.transition_sequence,
                    "state": _detached_json(checkpoint.state),
                }
                for checkpoint in self._checkpoints
            ],
        }
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temporary.write(encoded)
                temporary.flush()
                os.fsync(temporary.fileno())
                temporary_path = Path(temporary.name)
            os.replace(temporary_path, path)
        except OSError as exc:
            raise RetainedTrajectoryUnavailable(
                "retained trajectory storage is unavailable"
            ) from exc
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink(missing_ok=True)

    def query(
        self,
        *,
        session_id: str,
        branch_id: str | None = None,
    ) -> RetainedTrajectory:
        """Query a session, optionally narrowed to one branch."""
        trajectory = self.snapshot().for_session(session_id)
        if branch_id is None:
            return trajectory
        branch = str(branch_id).strip()
        if not branch:
            raise ValueError("branch_id must not be empty")
        events = tuple(
            event for event in trajectory.events if event.correlation.branch_id == branch
        )
        checkpoints = tuple(
            checkpoint
            for checkpoint in trajectory.checkpoints
            if checkpoint.state.get("branch_id") == branch
        )
        return RetainedTrajectory(events=events, checkpoints=checkpoints)


def verify_retained_trajectory(
    trajectory: RetainedTrajectory,
    *,
    expected_branch_ids: Sequence[str] = (),
) -> dict[str, bool]:
    """Verify the public qualification invariants for one trajectory.

    The return value is a stable named verdict map suitable for a retained
    qualification record. A ``ValueError`` indicates malformed evidence (for
    example an event stream with a duplicate process sequence). A false verdict
    indicates a complete but insufficient trajectory, such as one without a
    recovery marker or terminal decision lineage.

    Args:
        trajectory: Detached events and checkpoint projections from one session.
        expected_branch_ids: Branch identities that must each be represented.

    Returns:
        Named boolean verdicts for identity, branches, redaction, recovery,
        terminal lineage, and checkpoint coverage.
    """
    events = validate_agent_event_stream(trajectory.events)
    if not events:
        raise ValueError("retained trajectory requires at least one event")
    sessions = {event.correlation.session_id for event in events}
    checkpoint_sessions = {
        str(checkpoint.state.get("session_id") or "")
        for checkpoint in trajectory.checkpoints
    }
    if len(sessions) != 1:
        raise ValueError("retained trajectory must contain one session")
    if checkpoint_sessions - sessions:
        raise ValueError("checkpoint belongs to an unobserved session")
    session_id = next(iter(sessions))
    identity_values = {
        (
            event.correlation.program_id,
            event.correlation.model_profile_id,
            event.correlation.tool_catalog_id,
        )
        for event in events
    }
    expected_identity = next(iter(identity_values))
    branch_ids = {event.correlation.branch_id for event in events}
    expected = {str(branch).strip() for branch in expected_branch_ids if str(branch).strip()}
    if expected and not expected.issubset(branch_ids):
        raise ValueError(
            "retained trajectory is missing expected branches: "
            + ", ".join(sorted(expected - branch_ids))
        )
    checkpoint_identity_ok = all(
        checkpoint.state.get("session_id") == session_id
        and str(checkpoint.state.get("branch_id") or "") in branch_ids
        and (
            checkpoint.state.get("coordinator_program_id"),
            checkpoint.state.get("model_profile_id"),
            checkpoint.state.get("tool_catalog_id"),
        )
        == expected_identity
        for checkpoint in trajectory.checkpoints
    )
    process_ids = {event.correlation.process_instance_id for event in events}
    resumed = any(event.name is AgentEventName.SESSION_RESUMED for event in events)
    recovered = any(event.name is AgentEventName.CHECKPOINT_RECOVERED for event in events)
    terminal = [event for event in events if event.name in _TERMINAL_EVENTS]
    decisions = [
        event for event in events if event.name is AgentEventName.DECISION_COMMITTED
    ]
    terminal_receipts = {
        str(event.fields.get("decision_receipt_ref") or "")
        for event in terminal
        if event.fields.get("decision_receipt_ref")
    }
    checkpoint_receipts = {
        str(checkpoint.state.get("decision_receipt_ref", {}).get("uri") or "")
        for checkpoint in trajectory.checkpoints
        if isinstance(checkpoint.state.get("decision_receipt_ref"), Mapping)
    }
    terminal_lineage = bool(
        len(terminal) == 1
        and decisions
        and terminal_receipts
        and terminal_receipts.issubset(checkpoint_receipts)
        and any(
            str(event.fields.get("decision_receipt_ref") or "") in terminal_receipts
            for event in terminal
        )
    )
    branch_coverage = bool(expected or len(branch_ids) >= 2) and all(
        branch in branch_ids for branch in expected
    )
    return {
        "identity_consistent": len(identity_values) == 1,
        "concurrent_branch_attribution": branch_coverage,
        "redacted_public_projection": _trajectory_is_redacted(trajectory),
        "fresh_process_recovery": len(process_ids) >= 2 and resumed and recovered,
        "terminal_decision_lineage": terminal_lineage,
        "checkpoint_projection_complete": bool(trajectory.checkpoints)
        and checkpoint_identity_ok,
    }


def _trajectory_is_redacted(trajectory: RetainedTrajectory) -> bool:
    """Revalidate every detached public value in a retained snapshot."""
    try:
        for event in trajectory.events:
            AgentObservabilityEvent.model_validate(event.model_dump(mode="python"))
            validate_observability_fields(event.fields, label="retained event fields")
        for checkpoint in trajectory.checkpoints:
            validate_observability_fields(
                checkpoint.state,
                label="retained checkpoint state",
            )
    except (TypeError, ValueError):
        return False
    return True


def _detached_json(value: Mapping[str, Any]) -> dict[str, Any]:
    """Detach a JSON-native mapping through strict serialization."""
    try:
        result = json.loads(
            json.dumps(dict(value), sort_keys=True, separators=(",", ":"), allow_nan=False)
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("retained trajectory value must be JSON-native") from exc
    if not isinstance(result, dict):  # pragma: no cover - json object input
        raise ValueError("retained trajectory value must be an object")
    return copy.deepcopy(result)
