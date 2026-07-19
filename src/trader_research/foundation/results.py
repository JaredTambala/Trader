"""Transport-neutral outcomes returned by research application services."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from .identity import jsonable


@dataclass(frozen=True)
class ApplicationResult:
    """Result of one deterministic research application operation."""

    ok: bool
    operation: str
    data: Mapping[str, Any] = field(default_factory=dict)
    artifacts: Mapping[str, Any] = field(default_factory=dict)
    warnings: Sequence[str] = field(default_factory=tuple)
    errors: Sequence[Mapping[str, Any]] = field(default_factory=tuple)
    schema_version: str = "1"

    def __post_init__(self) -> None:
        """Require a stable operation name for every result."""
        if not self.operation.strip():
            raise ValueError("application result operation is required")

    def to_dict(self) -> dict[str, Any]:
        """Serialize the outcome without transport-specific metadata."""
        return {
            "ok": self.ok,
            "operation": self.operation,
            "schema_version": self.schema_version,
            "data": jsonable(self.data),
            "artifacts": jsonable(self.artifacts),
            "warnings": list(self.warnings),
            "errors": jsonable(self.errors),
        }


def success_result(
    *,
    command: str,
    data: Mapping[str, Any] | None = None,
    artifacts: Mapping[str, Any] | None = None,
    warnings: Sequence[str] | None = None,
) -> ApplicationResult:
    """Build a successful application result."""
    return ApplicationResult(
        ok=True,
        operation=command,
        data=dict(data or {}),
        artifacts=dict(artifacts or {}),
        warnings=tuple(warnings or ()),
    )


def error_result(
    *,
    command: str,
    message: str,
    code: str = "error",
    data: Mapping[str, Any] | None = None,
    artifacts: Mapping[str, Any] | None = None,
    warnings: Sequence[str] | None = None,
) -> ApplicationResult:
    """Build a failed application result with one structured error."""
    return ApplicationResult(
        ok=False,
        operation=command,
        data=dict(data or {}),
        artifacts=dict(artifacts or {}),
        warnings=tuple(warnings or ()),
        errors=({"code": code, "message": message},),
    )
