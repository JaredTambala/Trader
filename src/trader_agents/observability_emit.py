"""Process-scoped emission for validated agent observability events."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from threading import Lock
from typing import Any
from uuid import uuid4

from .observability import (
    AgentEventCorrelation,
    AgentEventError,
    AgentEventName,
    AgentObservabilityEvent,
    NoOpObservabilityEventSink,
    ObservabilityEventSink,
    build_agent_observability_event,
)
from .tracing import TraceCorrelation


EventClock = Callable[[], datetime]
"""Return one aware timestamp for a public observability event."""


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass
class AgentEventEmitter:
    """Create and deliver one ordered event stream for a runtime process.

    The emitter owns process identity, time, and sequence so graph nodes cannot
    invent or reuse ordering fields. One instance must be shared by every
    component in a composed runtime.

    Attributes:
        sink: Destination receiving validated public events.
        process_instance_id: Stable identity for the emitting process.
        clock: Injected aware clock used to timestamp events.
    """

    sink: ObservabilityEventSink = field(default_factory=NoOpObservabilityEventSink)
    process_instance_id: str = field(default_factory=lambda: uuid4().hex)
    clock: EventClock = _utc_now
    _sequence: int = field(default=0, init=False, repr=False)
    _lock: Lock = field(default_factory=Lock, init=False, repr=False)

    def __post_init__(self) -> None:
        """Reject an absent process identity before any event is emitted."""
        if not self.process_instance_id.strip():
            raise ValueError("event emitter process_instance_id is required")

    def emit(
        self,
        *,
        name: AgentEventName,
        correlation: TraceCorrelation,
        role: str,
        fields: Mapping[str, Any] | None = None,
        error: AgentEventError | None = None,
        call_id: str | None = None,
        transition_sequence: int | None = None,
    ) -> AgentObservabilityEvent:
        """Build and synchronously deliver the next process-local event.

        Args:
            name: Closed semantic event identity.
            correlation: Existing session, branch, program, and delegation IDs.
            role: Active coordinator or specialist role.
            fields: Bounded fields from the matching safe projector.
            error: Purpose-written public failure classification when required.
            call_id: Model or MCP call identity when required by the event.
            transition_sequence: Checkpoint or decision sequence when required.

        Returns:
            Exact validated event delivered to the configured sink.

        Raises:
            ValueError: If identity, event semantics, or public fields are invalid.
        """
        normalized_role = str(role).strip()
        if not normalized_role:
            raise ValueError("event emitter role is required")
        with self._lock:
            next_sequence = self._sequence + 1
            event = build_agent_observability_event(
                name=name,
                timestamp=self.clock(),
                sequence=next_sequence,
                correlation=AgentEventCorrelation(
                    session_id=correlation.session_id,
                    branch_id=correlation.branch_id,
                    role=normalized_role,
                    program_id=correlation.program_id,
                    model_profile_id=correlation.model_profile_id,
                    tool_catalog_id=correlation.tool_catalog_id,
                    process_instance_id=self.process_instance_id,
                    delegation_id=correlation.delegation_id,
                    attempt_id=correlation.attempt_id,
                    call_id=call_id,
                    transition_sequence=transition_sequence,
                ),
                fields=fields,
                error=error,
            )
            self.sink.emit(event)
            self._sequence = next_sequence
        return event

    def emit_phase_change(
        self,
        *,
        correlation: TraceCorrelation,
        role: str,
        previous_phase: str,
        next_phase: str,
        transition_sequence: int,
        reason: str,
    ) -> AgentObservabilityEvent | None:
        """Emit one real phase transition and ignore unchanged phases.

        Args:
            correlation: Stable runtime and optional delegation identities.
            role: Active coordinator or specialist role.
            previous_phase: Public phase before the accepted transition.
            next_phase: Public phase after the accepted transition.
            transition_sequence: Positive checkpoint transition sequence.
            reason: Bounded code-owned transition reason.

        Returns:
            Delivered event, or ``None`` when the phase did not change.
        """
        if previous_phase == next_phase:
            return None
        return self.emit(
            name=AgentEventName.PHASE_CHANGED,
            correlation=correlation,
            role=role,
            transition_sequence=transition_sequence,
            fields={
                "previous_phase": previous_phase,
                "next_phase": next_phase,
                "reason": reason,
            },
        )
