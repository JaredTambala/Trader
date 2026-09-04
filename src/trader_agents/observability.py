"""Public observability event and redaction contracts for agent execution.

The contract is deliberately independent of console, MLflow, and persistence
adapters so every destination receives the same semantic event and redaction
boundary. Schema-specific field projections live in
``observability_projections``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
import json
import math
from threading import Lock
from typing import Any, Literal, Protocol

from pydantic import Field, field_validator, model_validator

from .contracts import StrictPublicModel


OBSERVABILITY_SCHEMA_VERSION = "1"
MAX_OBSERVABILITY_EVENT_BYTES = 16_000
MAX_OBSERVABILITY_FIELDS_BYTES = 12_000
MAX_OBSERVABILITY_TEXT_CHARS = 4_000
MAX_OBSERVABILITY_COLLECTION_ITEMS = 64
MAX_OBSERVABILITY_NESTING_DEPTH = 8

_FORBIDDEN_EXACT_FIELDS = frozenset(
    {
        "authorization",
        "completion",
        "content",
        "credential",
        "document_text",
        "messages",
        "password",
        "prompt",
        "raw_payload",
        "request_body",
        "response_body",
        "scratchpad",
        "source_code",
        "source_text",
        "stderr",
        "stdout",
        "tool_transcript",
    }
)
_FORBIDDEN_FIELD_PARTS = (
    "access_token",
    "api_key",
    "chain_of_thought",
    "chunk_text",
    "client_secret",
    "completion",
    "content",
    "credential",
    "hidden_reasoning",
    "password",
    "private_key",
    "prompt",
    "raw_message",
    "raw_model",
    "raw_payload",
    "raw_tool",
    "refresh_token",
    "retrieved_chunk",
    "scratchpad",
    "secret",
    "source_code",
    "source_text",
    "tool_transcript",
)


class AgentEventLevel(str, Enum):
    """Visibility and severity assigned to one semantic agent event."""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class AgentEventAuthority(str, Enum):
    """Authority of the state projected by an observability event.

    The event remains diagnostic in every sink. This value tells an operator
    whether its subject is diagnostic activity, recoverable checkpoint state,
    or an already accepted canonical product record.
    """

    DIAGNOSTIC = "diagnostic"
    RECOVERY_STATE = "recovery_state"
    CANONICAL_RECORD = "canonical_record"


class AgentEventName(str, Enum):
    """Closed semantic vocabulary for the agent runtime trajectory."""

    SESSION_STARTED = "agent.session.started"
    SESSION_RESUMED = "agent.session.resumed"
    SESSION_INSPECTED = "agent.session.inspected"
    SESSION_INTERRUPTED = "agent.session.interrupted"
    SESSION_CANCELLED = "agent.session.cancelled"
    SESSION_COMPLETED = "agent.session.completed"
    SESSION_FAILED = "agent.session.failed"
    AGENDA_ACCEPTED = "agent.coordinator.agenda_accepted"
    SCHEDULING_COMPLETED = "agent.coordinator.scheduling_completed"
    DELEGATION_STARTED = "agent.delegation.started"
    JOIN_COMPLETED = "agent.coordinator.join_completed"
    MODEL_CALL_STARTED = "agent.model.call_started"
    MODEL_CALL_COMPLETED = "agent.model.call_completed"
    MODEL_CALL_FAILED = "agent.model.call_failed"
    MODEL_RESPONSE_RECEIVED = "agent.model.response_received"
    MODEL_SCHEMA_ACCEPTED = "agent.model.schema_accepted"
    MODEL_SCHEMA_REJECTED = "agent.model.schema_rejected"
    ACTION_DOMAIN_ACCEPTED = "agent.action.domain_accepted"
    ACTION_DOMAIN_REJECTED = "agent.action.domain_rejected"
    TOOL_POLICY_AUTHORIZED = "agent.tool.policy_authorized"
    TOOL_POLICY_DENIED = "agent.tool.policy_denied"
    TOOL_EXECUTION_STARTED = "agent.tool.execution_started"
    TOOL_EXECUTION_COMPLETED = "agent.tool.execution_completed"
    TOOL_EXECUTION_FAILED = "agent.tool.execution_failed"
    PHASE_CHANGED = "agent.phase.changed"
    BUDGET_UPDATED = "agent.budget.updated"
    CHECKPOINT_SAVED = "agent.checkpoint.saved"
    CHECKPOINT_RECOVERED = "agent.checkpoint.recovered"
    SPECIALIST_RETURNED = "agent.specialist.returned"
    SPECIALIST_RETURN_ACCEPTED = "agent.specialist.return_accepted"
    SPECIALIST_RETURN_REJECTED = "agent.specialist.return_rejected"
    EVIDENCE_REVIEW_STARTED = "agent.coordinator.evidence_review_started"
    EVIDENCE_REVIEW_COMPLETED = "agent.coordinator.evidence_review_completed"
    DECISION_COMMITTED = "agent.coordinator.decision_committed"


class AgentErrorCategory(str, Enum):
    """Stable public classification for an observable runtime failure."""

    CONFIGURATION = "configuration"
    MODEL_PROVIDER = "model_provider"
    SCHEMA_VALIDATION = "schema_validation"
    DOMAIN_VALIDATION = "domain_validation"
    POLICY = "policy"
    MCP_APPLICATION = "mcp_application"
    MCP_TRANSPORT = "mcp_transport"
    CHECKPOINT = "checkpoint"
    RESOURCE = "resource"
    OPERATOR = "operator"
    INTERNAL = "internal"


class ProjectionDetail(str, Enum):
    """Field detail selected before a public event reaches any sink."""

    INFO = "info"
    DEBUG = "debug"


class AgentEventCorrelation(StrictPublicModel):
    """Stable identities joining events across agents, tools, and processes.

    Attributes:
        session_id: Immutable research-session identity.
        branch_id: Coordinator or specialist branch identity.
        role: Active coordinator or specialist role.
        program_id: Exact admitted agent-program identity.
        model_profile_id: Exact admitted model-profile identity.
        tool_catalog_id: Exact code-owned tool-catalogue identity.
        process_instance_id: Identity of the process emitting the event.
        delegation_id: Specialist delegation identity when applicable.
        attempt_id: Specialist attempt identity paired with a delegation.
        call_id: Model or MCP call identity when applicable.
        transition_sequence: Checkpoint or decision sequence when applicable.
    """

    session_id: str = Field(min_length=1, max_length=200)
    branch_id: str = Field(min_length=1, max_length=200)
    role: str = Field(min_length=1, max_length=100)
    program_id: str = Field(min_length=1, max_length=200)
    model_profile_id: str = Field(min_length=1, max_length=200)
    tool_catalog_id: str = Field(min_length=1, max_length=200)
    process_instance_id: str = Field(min_length=1, max_length=200)
    delegation_id: str | None = Field(default=None, min_length=1, max_length=200)
    attempt_id: str | None = Field(default=None, min_length=1, max_length=200)
    call_id: str | None = Field(default=None, min_length=1, max_length=200)
    transition_sequence: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_delegation_identity(self) -> "AgentEventCorrelation":
        """Require delegation and attempt identities to appear together."""
        if (self.delegation_id is None) != (self.attempt_id is None):
            raise ValueError(
                "delegation_id and attempt_id must either both be present or absent"
            )
        return self


class AgentEventError(StrictPublicModel):
    """Bounded purpose-written error attached to a warning or failed event.

    ``message`` is an already-public operator explanation, not a raw exception
    string. Adapters and instrumentation must classify exceptions before
    constructing this value.
    """

    code: str = Field(
        min_length=1,
        max_length=100,
        pattern=r"^[a-z][a-z0-9_]*$",
    )
    category: AgentErrorCategory
    message: str = Field(min_length=1, max_length=1_000)
    retryable: bool = False


@dataclass(frozen=True)
class _EventRule:
    level: AgentEventLevel
    authority: AgentEventAuthority = AgentEventAuthority.DIAGNOSTIC
    call_id_required: bool = False
    delegation_required: bool = False
    transition_sequence_required: bool = False
    error_required: bool = False


_EVENT_RULES: Mapping[AgentEventName, _EventRule] = {
    AgentEventName.SESSION_STARTED: _EventRule(AgentEventLevel.INFO),
    AgentEventName.SESSION_RESUMED: _EventRule(AgentEventLevel.INFO),
    AgentEventName.SESSION_INSPECTED: _EventRule(AgentEventLevel.DEBUG),
    AgentEventName.SESSION_INTERRUPTED: _EventRule(AgentEventLevel.INFO),
    AgentEventName.SESSION_CANCELLED: _EventRule(AgentEventLevel.INFO),
    AgentEventName.SESSION_COMPLETED: _EventRule(AgentEventLevel.INFO),
    AgentEventName.SESSION_FAILED: _EventRule(
        AgentEventLevel.ERROR,
        error_required=True,
    ),
    AgentEventName.AGENDA_ACCEPTED: _EventRule(AgentEventLevel.INFO),
    AgentEventName.SCHEDULING_COMPLETED: _EventRule(AgentEventLevel.DEBUG),
    AgentEventName.DELEGATION_STARTED: _EventRule(
        AgentEventLevel.INFO,
        delegation_required=True,
    ),
    AgentEventName.JOIN_COMPLETED: _EventRule(AgentEventLevel.INFO),
    AgentEventName.MODEL_CALL_STARTED: _EventRule(
        AgentEventLevel.DEBUG,
        call_id_required=True,
    ),
    AgentEventName.MODEL_CALL_COMPLETED: _EventRule(
        AgentEventLevel.INFO,
        call_id_required=True,
    ),
    AgentEventName.MODEL_CALL_FAILED: _EventRule(
        AgentEventLevel.ERROR,
        call_id_required=True,
        error_required=True,
    ),
    AgentEventName.MODEL_RESPONSE_RECEIVED: _EventRule(
        AgentEventLevel.DEBUG,
        call_id_required=True,
    ),
    AgentEventName.MODEL_SCHEMA_ACCEPTED: _EventRule(
        AgentEventLevel.DEBUG,
        call_id_required=True,
    ),
    AgentEventName.MODEL_SCHEMA_REJECTED: _EventRule(
        AgentEventLevel.WARNING,
        call_id_required=True,
        error_required=True,
    ),
    AgentEventName.ACTION_DOMAIN_ACCEPTED: _EventRule(
        AgentEventLevel.INFO,
        call_id_required=True,
    ),
    AgentEventName.ACTION_DOMAIN_REJECTED: _EventRule(
        AgentEventLevel.WARNING,
        call_id_required=True,
        error_required=True,
    ),
    AgentEventName.TOOL_POLICY_AUTHORIZED: _EventRule(
        AgentEventLevel.DEBUG,
        call_id_required=True,
    ),
    AgentEventName.TOOL_POLICY_DENIED: _EventRule(
        AgentEventLevel.WARNING,
        call_id_required=True,
        error_required=True,
    ),
    AgentEventName.TOOL_EXECUTION_STARTED: _EventRule(
        AgentEventLevel.INFO,
        call_id_required=True,
    ),
    AgentEventName.TOOL_EXECUTION_COMPLETED: _EventRule(
        AgentEventLevel.INFO,
        call_id_required=True,
    ),
    AgentEventName.TOOL_EXECUTION_FAILED: _EventRule(
        AgentEventLevel.ERROR,
        call_id_required=True,
        error_required=True,
    ),
    AgentEventName.PHASE_CHANGED: _EventRule(
        AgentEventLevel.INFO,
        transition_sequence_required=True,
    ),
    AgentEventName.BUDGET_UPDATED: _EventRule(AgentEventLevel.DEBUG),
    AgentEventName.CHECKPOINT_SAVED: _EventRule(
        AgentEventLevel.DEBUG,
        authority=AgentEventAuthority.RECOVERY_STATE,
        transition_sequence_required=True,
    ),
    AgentEventName.CHECKPOINT_RECOVERED: _EventRule(
        AgentEventLevel.INFO,
        authority=AgentEventAuthority.RECOVERY_STATE,
        transition_sequence_required=True,
    ),
    AgentEventName.SPECIALIST_RETURNED: _EventRule(
        AgentEventLevel.INFO,
        delegation_required=True,
    ),
    AgentEventName.SPECIALIST_RETURN_ACCEPTED: _EventRule(
        AgentEventLevel.INFO,
        delegation_required=True,
    ),
    AgentEventName.SPECIALIST_RETURN_REJECTED: _EventRule(
        AgentEventLevel.WARNING,
        delegation_required=True,
        error_required=True,
    ),
    AgentEventName.EVIDENCE_REVIEW_STARTED: _EventRule(AgentEventLevel.INFO),
    AgentEventName.EVIDENCE_REVIEW_COMPLETED: _EventRule(AgentEventLevel.INFO),
    AgentEventName.DECISION_COMMITTED: _EventRule(
        AgentEventLevel.INFO,
        authority=AgentEventAuthority.CANONICAL_RECORD,
        transition_sequence_required=True,
    ),
}


class AgentObservabilityEvent(StrictPublicModel):
    """One validated, sink-neutral, redacted agent event.

    `sequence` is strictly increasing within `process_instance_id`. It does not
    imply a total order across fresh processes; checkpoint/decision sequence and
    correlation identities preserve cross-process lineage.
    """

    schema_version: Literal["1"] = OBSERVABILITY_SCHEMA_VERSION
    name: AgentEventName
    level: AgentEventLevel
    authority: AgentEventAuthority
    timestamp: datetime
    sequence: int = Field(ge=1)
    correlation: AgentEventCorrelation
    fields: dict[str, Any] = Field(default_factory=dict)
    error: AgentEventError | None = None

    @field_validator("timestamp")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        """Normalize an aware event timestamp to UTC."""
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("agent event timestamp must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_semantics(self) -> "AgentObservabilityEvent":
        """Enforce the closed event rule, correlation, redaction, and size."""
        rule = _EVENT_RULES[self.name]
        if self.level is not rule.level:
            raise ValueError(f"{self.name.value} requires level {rule.level.value}")
        if self.authority is not rule.authority:
            raise ValueError(
                f"{self.name.value} requires authority {rule.authority.value}"
            )
        if rule.call_id_required and self.correlation.call_id is None:
            raise ValueError(f"{self.name.value} requires call_id correlation")
        if rule.delegation_required and self.correlation.delegation_id is None:
            raise ValueError(
                f"{self.name.value} requires delegation and attempt correlation"
            )
        if (
            rule.transition_sequence_required
            and self.correlation.transition_sequence is None
        ):
            raise ValueError(
                f"{self.name.value} requires transition_sequence correlation"
            )
        if rule.error_required and self.error is None:
            raise ValueError(f"{self.name.value} requires a public error")
        if self.error is not None and self.level not in {
            AgentEventLevel.WARNING,
            AgentEventLevel.ERROR,
        }:
            raise ValueError("public errors belong only to warning or error events")
        validate_observability_fields(self.fields)
        encoded = _json_bytes(self.model_dump(mode="json"), "agent event")
        if len(encoded) > MAX_OBSERVABILITY_EVENT_BYTES:
            raise ValueError(
                f"agent event exceeds {MAX_OBSERVABILITY_EVENT_BYTES} bytes"
            )
        return self

    @property
    def stream_position(self) -> tuple[str, int]:
        """Return the process-local ordering identity for the event."""
        return self.correlation.process_instance_id, self.sequence

    def to_dict(self) -> dict[str, Any]:
        """Return the stable JSON-native event representation."""
        validated = _validated_event_copy(self)
        return validated.model_dump(mode="json")

    def to_json(self) -> str:
        """Return the deterministic compact JSON representation."""
        return _json_bytes(self.to_dict(), "agent event").decode("utf-8")


class ObservabilityEventSink(Protocol):
    """Destination-independent boundary accepting only validated events."""

    def emit(self, event: AgentObservabilityEvent) -> None:
        """Consume one already-redacted public event."""


@dataclass(frozen=True)
class NoOpObservabilityEventSink:
    """Validated event sink used when event delivery is disabled."""

    def emit(self, event: AgentObservabilityEvent) -> None:
        """Accept one validated event without retaining it."""
        _validated_event_copy(event)


@dataclass
class RecordingObservabilityEventSink:
    """Thread-safe event sink for deterministic contract tests.

    Attributes:
        events: Validated events in process-local emission order.
    """

    events: list[AgentObservabilityEvent] = field(default_factory=list)
    _last_sequence_by_process: dict[str, int] = field(
        default_factory=dict,
        init=False,
        repr=False,
    )
    _lock: Lock = field(default_factory=Lock, init=False, repr=False)

    def emit(self, event: AgentObservabilityEvent) -> None:
        """Retain an event after checking its process-local sequence."""
        validated = _validated_event_copy(event)
        process_id, sequence = validated.stream_position
        with self._lock:
            previous = self._last_sequence_by_process.get(process_id, 0)
            if sequence <= previous:
                raise ValueError("agent event sequence must increase within a process")
            self._last_sequence_by_process[process_id] = sequence
            self.events.append(validated)


def build_agent_observability_event(
    *,
    name: AgentEventName,
    timestamp: datetime,
    sequence: int,
    correlation: AgentEventCorrelation,
    fields: Mapping[str, Any] | None = None,
    error: AgentEventError | None = None,
) -> AgentObservabilityEvent:
    """Build an event using the fixed level and authority for its semantic name.

    Args:
        name: Closed semantic event identity.
        timestamp: Aware time supplied by the runtime clock boundary.
        sequence: Strictly increasing process-local event sequence.
        correlation: Exact session, runtime, and optional call identities.
        fields: Bounded public fields from an explicit projector.
        error: Required public error for rejection and failure events.

    Returns:
        Validated event suitable for every configured sink.
    """
    rule = _EVENT_RULES[name]
    return AgentObservabilityEvent(
        name=name,
        level=rule.level,
        authority=rule.authority,
        timestamp=timestamp,
        sequence=sequence,
        correlation=correlation,
        fields=dict(fields or {}),
        error=error,
    )


def validate_agent_event_stream(
    events: Sequence[AgentObservabilityEvent],
) -> tuple[AgentObservabilityEvent, ...]:
    """Validate monotonic sequence and timestamps within each emitting process.

    Args:
        events: Events in observed delivery order.

    Returns:
        Immutable sequence of the validated events.

    Raises:
        ValueError: If one process repeats or reverses sequence or time.
    """
    last_by_process: dict[str, tuple[int, datetime]] = {}
    validated_events: list[AgentObservabilityEvent] = []
    for candidate in events:
        event = _validated_event_copy(candidate)
        process_id, sequence = event.stream_position
        previous = last_by_process.get(process_id)
        if previous is not None:
            previous_sequence, previous_timestamp = previous
            if sequence <= previous_sequence:
                raise ValueError("agent event sequence must increase within a process")
            if event.timestamp < previous_timestamp:
                raise ValueError(
                    "agent event timestamp must not move backward within a process"
                )
        last_by_process[process_id] = (sequence, event.timestamp)
        validated_events.append(event)
    return tuple(validated_events)


def validate_observability_fields(
    fields: Mapping[str, Any],
    *,
    label: str = "observability fields",
    max_bytes: int = MAX_OBSERVABILITY_FIELDS_BYTES,
) -> None:
    """Reject unsafe, non-JSON, deeply nested, or oversized public fields.

    Args:
        fields: Candidate public field mapping.
        label: Context included in actionable validation errors.
        max_bytes: Maximum compact encoded size accepted by the destination.

    Raises:
        ValueError: If the mapping violates redaction or boundedness rules.
    """
    if max_bytes <= 0:
        raise ValueError("observability field byte limit must be positive")
    _validate_public_value(fields, path=label, depth=0)
    encoded = _json_bytes(fields, label)
    if len(encoded) > max_bytes:
        raise ValueError(f"{label} exceeds {max_bytes} bytes")


def _validate_public_value(value: object, *, path: str, depth: int) -> None:
    if depth > MAX_OBSERVABILITY_NESTING_DEPTH:
        raise ValueError(
            f"{path} exceeds nesting depth {MAX_OBSERVABILITY_NESTING_DEPTH}"
        )
    if isinstance(value, Mapping):
        if len(value) > MAX_OBSERVABILITY_COLLECTION_ITEMS:
            raise ValueError(
                f"{path} exceeds {MAX_OBSERVABILITY_COLLECTION_ITEMS} fields"
            )
        for key, item in value.items():
            if not isinstance(key, str) or not key.strip():
                raise ValueError(f"{path} keys must be non-empty strings")
            if len(key) > 150:
                raise ValueError(f"{path}.{key} key exceeds 150 characters")
            if _field_is_forbidden(key):
                raise ValueError(f"observability field is not allowed: {path}.{key}")
            _validate_public_value(item, path=f"{path}.{key}", depth=depth + 1)
        return
    if isinstance(value, list):
        if len(value) > MAX_OBSERVABILITY_COLLECTION_ITEMS:
            raise ValueError(
                f"{path} exceeds {MAX_OBSERVABILITY_COLLECTION_ITEMS} items"
            )
        for index, item in enumerate(value):
            _validate_public_value(
                item,
                path=f"{path}[{index}]",
                depth=depth + 1,
            )
        return
    if value is None or isinstance(value, (bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{path} must not contain NaN or infinity")
        return
    if isinstance(value, str):
        if len(value) > MAX_OBSERVABILITY_TEXT_CHARS:
            raise ValueError(
                f"{path} exceeds {MAX_OBSERVABILITY_TEXT_CHARS} characters"
            )
        return
    raise ValueError(f"{path} must contain only JSON-native values")


def _field_is_forbidden(key: str) -> bool:
    normalized = str(key).strip().casefold().replace("-", "_")
    return normalized in _FORBIDDEN_EXACT_FIELDS or any(
        part in normalized for part in _FORBIDDEN_FIELD_PARTS
    )


def _json_bytes(value: object, label: str) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be JSON-native") from exc


def _require_event(event: AgentObservabilityEvent) -> None:
    if not isinstance(event, AgentObservabilityEvent):
        raise TypeError("observability sinks accept AgentObservabilityEvent only")


def _validated_event_copy(
    event: AgentObservabilityEvent,
) -> AgentObservabilityEvent:
    """Revalidate and detach one event before a sink consumes it."""
    _require_event(event)
    return AgentObservabilityEvent.model_validate(event.model_dump(mode="python"))
