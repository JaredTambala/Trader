"""Construct transport-neutral outcomes for research application services.

Results carry normalized data, canonical artifact references, warnings, and
structured errors without MCP-specific fields. Adapters may wrap these values
but should not reinterpret success, failure, or artifact identity.
"""

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
    """Build a successful transport-neutral application result.

    Data and artifact mappings are copied, warnings are de-duplicated in caller
    order, and the error collection is empty. No payload is persisted or sent by
    this helper.

    Returns:
        An immutable result with ``ok`` set to true.
    """
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
    """Build a failed result containing one structured application error.

    Optional partial data, artifact references, and warnings are preserved so a
    caller can inspect bounded evidence produced before the failure. The error
    code and message are normalized but not logged or raised by this helper.

    Returns:
        An immutable result with ``ok`` false and exactly one error entry.
    """
    return ApplicationResult(
        ok=False,
        operation=command,
        data=dict(data or {}),
        artifacts=dict(artifacts or {}),
        warnings=tuple(warnings or ()),
        errors=({"code": code, "message": message},),
    )
