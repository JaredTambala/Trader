"""Validated stderr console delivery for public agent events."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
import json
import logging
import os
import sys
from typing import TextIO

from .observability import (
    AgentEventLevel,
    AgentObservabilityEvent,
    ObservabilityEventSink,
)


AGENT_LOG_LEVEL_ENV = "TRADER_AGENTS_LOG_LEVEL"
AGENT_LOG_FORMAT_ENV = "TRADER_AGENTS_LOG_FORMAT"

logger = logging.getLogger(__name__)

_LOGGING_LEVELS = {
    AgentEventLevel.DEBUG: logging.DEBUG,
    AgentEventLevel.INFO: logging.INFO,
    AgentEventLevel.WARNING: logging.WARNING,
    AgentEventLevel.ERROR: logging.ERROR,
}


class ConsoleLogFormat(str, Enum):
    """Supported operator-facing event representations."""

    HUMAN = "human"
    JSON = "json"


@dataclass(frozen=True)
class AgentConsoleConfig:
    """Validated console threshold and representation.

    Attributes:
        level: Minimum DEBUG or INFO event visibility.
        format: Human-readable or one-event-per-line JSON output.
    """

    level: AgentEventLevel = AgentEventLevel.INFO
    format: ConsoleLogFormat = ConsoleLogFormat.HUMAN

    def __post_init__(self) -> None:
        """Restrict operator thresholds to DEBUG and INFO."""
        if self.level not in {AgentEventLevel.DEBUG, AgentEventLevel.INFO}:
            raise ValueError("agent log level must be DEBUG or INFO")


def agent_console_config(
    environ: Mapping[str, str] | None = None,
    *,
    level_override: str | None = None,
    format_override: str | None = None,
) -> AgentConsoleConfig:
    """Normalize agent console settings from environment and CLI overrides.

    Args:
        environ: Environment values; defaults to the current process.
        level_override: Optional CLI value taking precedence over the environment.
        format_override: Optional CLI value taking precedence over the environment.

    Returns:
        Validated immutable console configuration.

    Raises:
        ValueError: If the level or format is unsupported.
    """
    values = os.environ if environ is None else environ
    level_value = (
        level_override
        if level_override is not None
        else values.get(AGENT_LOG_LEVEL_ENV, "INFO")
    )
    format_value = (
        format_override
        if format_override is not None
        else values.get(AGENT_LOG_FORMAT_ENV, "human")
    )
    try:
        level = AgentEventLevel(str(level_value).strip().lower())
    except ValueError as exc:
        raise ValueError("agent log level must be DEBUG or INFO") from exc
    try:
        output_format = ConsoleLogFormat(str(format_value).strip().lower())
    except ValueError as exc:
        raise ValueError("agent log format must be human or json") from exc
    return AgentConsoleConfig(level=level, format=output_format)


@dataclass
class ConsoleObservabilityEventSink:
    """Write filtered, validated events to one stderr-like text stream.

    Attributes:
        config: Validated threshold and rendering format.
        stream: Destination stream. Production composition uses ``sys.stderr``.
    """

    config: AgentConsoleConfig = field(default_factory=AgentConsoleConfig)
    stream: TextIO = field(default_factory=lambda: sys.stderr)
    _handler: logging.StreamHandler[TextIO] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        """Build a private logging handler without changing global logging."""
        self._handler = logging.StreamHandler(self.stream)
        self._handler.setFormatter(logging.Formatter("%(message)s"))

    def emit(self, event: AgentObservabilityEvent) -> None:
        """Validate, filter, render, and synchronously write one event."""
        payload = event.to_dict()
        event_level = _LOGGING_LEVELS[event.level]
        if event_level < _LOGGING_LEVELS[self.config.level]:
            return
        message = (
            event.to_json()
            if self.config.format is ConsoleLogFormat.JSON
            else _render_human(payload)
        )
        record = logging.LogRecord(
            name=logger.name,
            level=event_level,
            pathname=__file__,
            lineno=0,
            msg=message,
            args=(),
            exc_info=None,
        )
        self._handler.handle(record)


@dataclass(frozen=True)
class CompositeObservabilityEventSink:
    """Deliver one validated event to every configured sink in order.

    Attributes:
        sinks: Ordered destinations. Any sink failure propagates to the emitter.
    """

    sinks: Sequence[ObservabilityEventSink]

    def __post_init__(self) -> None:
        """Require at least one explicit destination."""
        if not self.sinks:
            raise ValueError("composite observability sink requires a destination")

    def emit(self, event: AgentObservabilityEvent) -> None:
        """Revalidate and detach the event before ordered fan-out."""
        validated = AgentObservabilityEvent.model_validate(event.to_dict())
        for sink in self.sinks:
            sink.emit(validated)


def _render_human(payload: Mapping[str, object]) -> str:
    correlation = dict(payload["correlation"])
    fields = dict(payload["fields"])
    timestamp = str(payload["timestamp"])
    parts = [
        timestamp,
        str(payload["level"]).upper(),
        str(payload["name"]),
        f"session={correlation['session_id']}",
        f"branch={correlation['branch_id']}",
        f"role={correlation['role']}",
        f"program={correlation['program_id']}",
        f"model_profile={correlation['model_profile_id']}",
        f"tool_catalog={correlation['tool_catalog_id']}",
        f"process={correlation['process_instance_id']}",
    ]
    for key in ("delegation_id", "attempt_id", "call_id", "transition_sequence"):
        if correlation.get(key) is not None:
            parts.append(f"{key.removesuffix('_id')}={correlation[key]}")
    parts.extend(
        f"{key}={json.dumps(value, sort_keys=True, separators=(',', ':'))}"
        for key, value in _human_fields(fields, correlation)
    )
    error = payload.get("error")
    if isinstance(error, Mapping):
        parts.extend(
            (
                f"error_code={error['code']}",
                f"error_category={error['category']}",
                f"retryable={json.dumps(error['retryable'])}",
                f"error_message={json.dumps(error['message'])}",
            )
        )
    return " ".join(parts)


def _human_fields(
    fields: Mapping[str, object],
    correlation: Mapping[str, object],
) -> list[tuple[str, object]]:
    """Remove redundant empty detail from the human representation only."""
    correlation_fields = {
        "attempt_id": "attempt_id",
        "call_id": "call_id",
        "delegation_id": "delegation_id",
        "role": "role",
        "transition_sequence": "transition_sequence",
    }
    visible = []
    for key, value in sorted(fields.items()):
        correlation_key = correlation_fields.get(key)
        if correlation_key is not None and correlation.get(correlation_key) == value:
            continue
        if value is None or value == [] or value == {}:
            continue
        if key.endswith("_omitted_count") and value == 0:
            continue
        visible.append((key, value))
    return visible
