"""Shared contracts for AI/tool-facing commands."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import json
from pathlib import Path
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = "1"


class SideEffect(str, Enum):
    """Declared side-effect class for tool-facing commands."""

    READ_ONLY = "read_only"
    LOCAL_MUTATING = "local_mutating"
    BROKER_READ = "broker_read"
    BROKER_MUTATING = "broker_mutating"


@dataclass(frozen=True)
class ToolEnvelope:
    """Stable JSON envelope returned by tool-facing commands."""

    ok: bool
    command: str
    side_effect: SideEffect
    data: Mapping[str, Any] = field(default_factory=dict)
    artifacts: Mapping[str, Any] = field(default_factory=dict)
    warnings: Sequence[str] = field(default_factory=tuple)
    errors: Sequence[Mapping[str, Any]] = field(default_factory=tuple)
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable mapping."""
        return {
            "ok": self.ok,
            "command": self.command,
            "side_effect": self.side_effect.value,
            "schema_version": self.schema_version,
            "generated_at": _jsonable(self.generated_at),
            "data": _jsonable(self.data),
            "artifacts": _jsonable(self.artifacts),
            "warnings": list(self.warnings),
            "errors": [dict(error) for error in self.errors],
        }


def success_envelope(
    *,
    command: str,
    side_effect: SideEffect,
    data: Mapping[str, Any] | None = None,
    artifacts: Mapping[str, Any] | None = None,
    warnings: Sequence[str] | None = None,
) -> ToolEnvelope:
    """Create a successful tool envelope."""
    return ToolEnvelope(
        ok=True,
        command=command,
        side_effect=side_effect,
        data=dict(data or {}),
        artifacts=dict(artifacts or {}),
        warnings=tuple(warnings or ()),
    )


def error_envelope(
    *,
    command: str,
    side_effect: SideEffect,
    message: str,
    code: str = "error",
    data: Mapping[str, Any] | None = None,
) -> ToolEnvelope:
    """Create a failed tool envelope."""
    return ToolEnvelope(
        ok=False,
        command=command,
        side_effect=side_effect,
        data=dict(data or {}),
        errors=({"code": code, "message": message},),
    )


def envelope_json(envelope: ToolEnvelope) -> str:
    """Serialize an envelope as stable pretty JSON."""
    return json.dumps(envelope.to_dict(), indent=2, sort_keys=True, default=str)


def write_json_artifact(payload: Mapping[str, Any], path: str | Path) -> Path:
    """Write a stable JSON artifact and return its path."""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(_jsonable(payload), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return output_path


def _jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _jsonable(val) for key, val in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value
