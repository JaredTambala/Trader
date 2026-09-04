"""Protocol-safe stderr logging for the standalone MCP process."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
import json
import logging
import os
import sys
from typing import TextIO
from uuid import uuid4


MCP_LOG_LEVEL_ENV = "TRADER_MCP_LOG_LEVEL"
MCP_LOG_FORMAT_ENV = "TRADER_MCP_LOG_FORMAT"
MCP_SERVER_ROLE_ENV = "TRADER_MCP_SERVER_ROLE"

logger = logging.getLogger(__name__)

_FORBIDDEN_FIELD_PARTS = (
    "api_key",
    "credential",
    "password",
    "private_key",
    "secret",
    "token",
)


class McpLogLevel(str, Enum):
    """Supported MCP stderr thresholds."""

    DEBUG = "debug"
    INFO = "info"


class McpLogFormat(str, Enum):
    """Supported MCP stderr representations."""

    HUMAN = "human"
    JSON = "json"


@dataclass(frozen=True)
class McpConsoleConfig:
    """Validated MCP process logging configuration.

    Attributes:
        level: Minimum INFO or DEBUG visibility.
        format: Human-readable or structured JSON lines.
        role: Role label assigned by the parent agent runtime.
        process_instance_id: Unique identity for this server process.
    """

    level: McpLogLevel = McpLogLevel.INFO
    format: McpLogFormat = McpLogFormat.HUMAN
    role: str = "standalone"
    process_instance_id: str = field(
        default_factory=lambda: f"{os.getpid()}-{uuid4().hex}"
    )

    def __post_init__(self) -> None:
        """Require an unambiguous non-empty process role."""
        if not self.role.strip():
            raise ValueError("MCP server role is required")
        if not self.process_instance_id.strip():
            raise ValueError("MCP server process_instance_id is required")


def mcp_console_config(
    environ: Mapping[str, str] | None = None,
) -> McpConsoleConfig:
    """Normalize protocol-safe MCP logging from environment values.

    Args:
        environ: Environment mapping; defaults to the current process.

    Returns:
        Validated stderr logging configuration.

    Raises:
        ValueError: If level, format, or role is invalid.
    """
    values = os.environ if environ is None else environ
    try:
        level = McpLogLevel(str(values.get(MCP_LOG_LEVEL_ENV, "INFO")).strip().lower())
    except ValueError as exc:
        raise ValueError("MCP log level must be DEBUG or INFO") from exc
    try:
        output_format = McpLogFormat(
            str(values.get(MCP_LOG_FORMAT_ENV, "human")).strip().lower()
        )
    except ValueError as exc:
        raise ValueError("MCP log format must be human or json") from exc
    role = str(values.get(MCP_SERVER_ROLE_ENV, "standalone")).strip()
    return McpConsoleConfig(level=level, format=output_format, role=role)


@dataclass
class McpConsoleLogger:
    """Write bounded MCP process lifecycle events to stderr only.

    Attributes:
        config: Validated MCP process logging configuration.
        stream: Destination stream. Production uses ``sys.stderr``.
    """

    config: McpConsoleConfig = field(default_factory=McpConsoleConfig)
    stream: TextIO = field(default_factory=lambda: sys.stderr)
    _handler: logging.StreamHandler[TextIO] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        """Build a private logging handler without touching protocol stdout."""
        self._handler = logging.StreamHandler(self.stream)
        self._handler.setFormatter(logging.Formatter("%(message)s"))

    def info(self, event: str, **fields: str | int | bool) -> None:
        """Write one bounded INFO process event.

        Args:
            event: Stable semantic MCP process event name.
            **fields: Public scalar identities and counts.

        Raises:
            ValueError: If an event name, field, or encoded line is unsafe.
        """
        self._write(McpLogLevel.INFO, event, fields)

    def debug(self, event: str, **fields: str | int | bool) -> None:
        """Write one bounded DEBUG process event when DEBUG is enabled.

        Args:
            event: Stable semantic MCP process event name.
            **fields: Public scalar identities and counts.
        """
        if self.config.level is McpLogLevel.INFO:
            return
        self._write(McpLogLevel.DEBUG, event, fields)

    def _write(
        self,
        level: McpLogLevel,
        event: str,
        fields: Mapping[str, str | int | bool],
    ) -> None:
        """Validate, render, and deliver one stderr record."""
        payload = _payload(
            event,
            level=level,
            role=self.config.role,
            process_instance_id=self.config.process_instance_id,
            fields=fields,
        )
        message = (
            json.dumps(payload, sort_keys=True, separators=(",", ":"))
            if self.config.format is McpLogFormat.JSON
            else _human_message(payload)
        )
        if len(message.encode("utf-8")) > 4_000:
            raise ValueError("MCP log event exceeds 4000 bytes")
        record = logging.LogRecord(
            name=logger.name,
            level=logging.DEBUG if level is McpLogLevel.DEBUG else logging.INFO,
            pathname=__file__,
            lineno=0,
            msg=message,
            args=(),
            exc_info=None,
        )
        self._handler.handle(record)


def _payload(
    event: str,
    *,
    level: McpLogLevel,
    role: str,
    process_instance_id: str,
    fields: Mapping[str, str | int | bool],
) -> dict[str, str | int | bool]:
    normalized_event = str(event).strip()
    if not normalized_event or len(normalized_event) > 150:
        raise ValueError("MCP log event name must contain 1 to 150 characters")
    payload: dict[str, str | int | bool] = {
        "event": normalized_event,
        "level": level.value,
        "process_instance_id": process_instance_id,
        "role": role,
    }
    for key, value in fields.items():
        normalized_key = str(key).strip()
        if not normalized_key or len(normalized_key) > 100:
            raise ValueError("MCP log field names must contain 1 to 100 characters")
        normalized_lower = normalized_key.casefold().replace("-", "_")
        if any(part in normalized_lower for part in _FORBIDDEN_FIELD_PARTS):
            raise ValueError(f"MCP log field is not allowed: {normalized_key}")
        if not isinstance(value, (str, int, bool)):
            raise ValueError(f"MCP log field {normalized_key} must be a scalar")
        if isinstance(value, str) and len(value) > 500:
            raise ValueError(f"MCP log field {normalized_key} exceeds 500 characters")
        payload[normalized_key] = value
    return payload


def _human_message(payload: Mapping[str, str | int | bool]) -> str:
    parts = [
        str(payload["level"]).upper(),
        str(payload["event"]),
        f"role={payload['role']}",
        f"process={payload['process_instance_id']}",
    ]
    parts.extend(
        f"{key}={json.dumps(value)}"
        for key, value in sorted(payload.items())
        if key not in {"event", "level", "process_instance_id", "role"}
    )
    return " ".join(parts)
