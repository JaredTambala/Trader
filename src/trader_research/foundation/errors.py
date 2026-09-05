"""Typed failures raised at research application boundaries.

The exceptions preserve stable error codes and actionable context for transport
adapters while allowing deterministic services to fail without constructing MCP
responses or swallowing validation detail.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class ResearchFailure:
    """Machine-readable application failure returned at context boundaries."""

    code: str
    message: str
    details: Mapping[str, Any] = field(default_factory=dict)


class ResearchApplicationError(RuntimeError):
    """Raised when an application service cannot produce a valid result."""

    def __init__(self, failure: ResearchFailure) -> None:
        super().__init__(failure.message)
        self.failure = failure
