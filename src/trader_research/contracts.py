"""Shared contracts for deterministic research-agent tools."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from .agents import agent_owner_for_tool


SCHEMA_VERSION = "1"


class SideEffect(str, Enum):
    """Declared side-effect class for research-agent tools.

    Attributes:
        READ_ONLY: Reads local/config/runtime state without writing.
        LOCAL_MUTATING: Writes bounded local artifacts or research records.
        EXTERNAL_RESEARCH_MUTATING: Projects canonical research evidence to an external analytical system.
        BROKER_READ: Reads broker/operator state without mutation.
        BROKER_MUTATING: Mutates broker state; not allowed for research tools.
    """

    READ_ONLY = "read_only"
    LOCAL_MUTATING = "local_mutating"
    EXTERNAL_RESEARCH_MUTATING = "external_research_mutating"
    BROKER_READ = "broker_read"
    BROKER_MUTATING = "broker_mutating"


@dataclass(frozen=True)
class ArtifactReference:
    """JSON-safe pointer to an artifact owned or consumed by an agent.

    Attributes:
        artifact_type: Stable artifact type, such as `dataset_manifest`.
        path: Optional local filesystem path to the artifact.
        uri: Optional URI for clients that prefer URI-addressable artifacts.
        metadata: Optional JSON-compatible provenance or summary metadata.
    """

    artifact_type: str
    path: str | Path | None = None
    uri: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the artifact pointer into a JSON-safe envelope payload.

        Returns:
            Dictionary form containing normalized path, URI, and metadata values.
        """
        return {
            "artifact_type": self.artifact_type,
            "path": _jsonable(self.path),
            "uri": self.uri,
            "metadata": _jsonable(self.metadata),
        }


@dataclass(frozen=True)
class ToolEnvelope:
    """Stable JSON envelope returned by deterministic research-agent tools.

    Attributes:
        ok: Whether the tool completed successfully.
        command: Stable tool command identifier.
        agent_owner: Display name of the agent that owns the artifact boundary.
        side_effect: Declared side-effect class for the tool call.
        data: Machine-readable result payload.
        artifacts: Artifact references produced or consumed by the tool.
        warnings: Non-fatal warnings emitted by the tool.
        errors: Structured fatal errors when `ok` is false.
        generated_at: Timestamp when the envelope was created.
        schema_version: Stable envelope schema version.
    """

    ok: bool
    command: str
    agent_owner: str
    side_effect: SideEffect
    data: Mapping[str, Any] = field(default_factory=dict)
    artifacts: Mapping[str, Any] = field(default_factory=dict)
    warnings: Sequence[str] = field(default_factory=tuple)
    errors: Sequence[Mapping[str, Any]] = field(default_factory=tuple)
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        """Serialize the tool result envelope into its stable JSON payload.

        Returns:
            Dictionary form containing normalized data, artifacts, warnings, and errors.
        """
        return {
            "ok": self.ok,
            "command": self.command,
            "agent_owner": self.agent_owner,
            "side_effect": self.side_effect.value,
            "schema_version": self.schema_version,
            "generated_at": _jsonable(self.generated_at),
            "data": _jsonable(self.data),
            "artifacts": _jsonable(self.artifacts),
            "warnings": list(self.warnings),
            "errors": _jsonable(self.errors),
        }


def success_envelope(
    *,
    command: str,
    side_effect: SideEffect,
    agent_owner: str | None = None,
    data: Mapping[str, Any] | None = None,
    artifacts: Mapping[str, Any] | None = None,
    warnings: Sequence[str] | None = None,
) -> ToolEnvelope:
    """Create a successful research-agent tool envelope.

    Args:
        command: Stable tool command identifier.
        side_effect: Declared side-effect class for the tool call.
        agent_owner: Optional explicit owner for tools not in the registry.
        data: Optional machine-readable result payload.
        artifacts: Optional produced or consumed artifact references.
        warnings: Optional non-fatal warnings.

    Returns:
        Successful `ToolEnvelope`.

    Raises:
        KeyError: If `agent_owner` is omitted and `command` is not registered.
    """
    return ToolEnvelope(
        ok=True,
        command=command,
        agent_owner=_resolve_agent_owner(command, agent_owner),
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
    agent_owner: str | None = None,
    code: str = "error",
    data: Mapping[str, Any] | None = None,
) -> ToolEnvelope:
    """Create a failed research-agent tool envelope.

    Args:
        command: Stable tool command identifier.
        side_effect: Declared side-effect class for the tool call.
        message: Human-readable error message.
        agent_owner: Optional explicit owner for tools not in the registry.
        code: Stable machine-readable error code.
        data: Optional context payload for the error.

    Returns:
        Failed `ToolEnvelope`.

    Raises:
        KeyError: If `agent_owner` is omitted and `command` is not registered.
    """
    return ToolEnvelope(
        ok=False,
        command=command,
        agent_owner=_resolve_agent_owner(command, agent_owner),
        side_effect=side_effect,
        data=dict(data or {}),
        errors=({"code": code, "message": message},),
    )


def envelope_json(envelope: ToolEnvelope) -> str:
    """Serialize an envelope as stable pretty JSON.

    Args:
        envelope: Envelope to serialize.

    Returns:
        Pretty JSON string with sorted keys.
    """
    return json.dumps(envelope.to_dict(), indent=2, sort_keys=True, default=str)


def write_json_artifact(payload: Mapping[str, Any], path: str | Path) -> Path:
    """Write a stable JSON artifact and return its path.

    Args:
        payload: JSON-compatible artifact payload.
        path: Destination file path.

    Returns:
        Resolved destination path as a `Path` instance.

    Raises:
        OSError: If the destination directory or file cannot be written.
    """
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(_jsonable(payload), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return output_path


def _resolve_agent_owner(command: str, explicit_owner: str | None) -> str:
    """Resolve the owning agent for an envelope.

    Args:
        command: Stable tool command identifier.
        explicit_owner: Optional explicit owner for unregistered commands.

    Returns:
        Resolved agent owner display name.

    Raises:
        KeyError: If no explicit owner is supplied and the command is not registered.
    """
    if explicit_owner is not None:
        return explicit_owner
    return agent_owner_for_tool(command)


def _jsonable(value: Any) -> Any:
    """Convert known Python objects to JSON-compatible values.

    Args:
        value: Arbitrary value to normalize.

    Returns:
        A JSON-compatible value when the input type is supported, otherwise the
        original value.
    """
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, ArtifactReference):
        return value.to_dict()
    if isinstance(value, Mapping):
        return {str(key): _jsonable(val) for key, val in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value
