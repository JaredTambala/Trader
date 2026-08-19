"""Declare provider-neutral policy and action-handler boundaries.

Specialist policies receive only the bounded public task, canonical handoffs,
declared output bindings, and action-attempt summaries. Registered action
handlers are responsible for parsing specialist-specific input into typed domain
requests before calling MCP or another injected adapter.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from trader_research.foundation import parse_research_artifact_uri
from trader_research.governance import ArtifactReportRef, SpecialistHandoff

from .domain import (
    SpecialistActionOutcome,
    SpecialistActionSummary,
    SpecialistDecision,
    SpecialistTask,
)


@dataclass(frozen=True)
class SpecialistPolicyContext:
    """Immutable public context supplied to a specialist policy.

    Attributes:
        task: Validated request addressed to the specialist.
        handoffs: Canonical handoffs accepted from prior registered actions.
        output_bindings: Requested task-slot IDs to accepted handoff IDs.
        action_summaries: Bounded prior action outcomes without raw payloads.
        decision_count: Number of policy decisions already accepted.
    """

    task: SpecialistTask
    handoffs: tuple[SpecialistHandoff, ...] = ()
    output_bindings: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    action_summaries: tuple[SpecialistActionSummary, ...] = ()
    decision_count: int = 0

    def __post_init__(self) -> None:
        """Normalize bindings and validate bounded context identity."""
        normalized = {
            str(slot_id): tuple(str(item) for item in handoff_ids)
            for slot_id, handoff_ids in self.output_bindings.items()
        }
        object.__setattr__(self, "output_bindings", normalized)
        if self.decision_count < 0:
            raise ValueError("specialist decision_count cannot be negative")

    @property
    def available_refs(self) -> tuple[ArtifactReportRef, ...]:
        """Return canonical task inputs plus refs from accepted handoffs.

        Raises:
            ValueError: If an accepted handoff lacks a canonical artifact URI.
        """
        references = list(self.task.input_refs)
        for handoff in self.handoffs:
            if handoff.artifact_uri is None:
                raise ValueError(
                    "specialist policy handoffs require canonical artifact URIs"
                )
            artifact_type, artifact_id = parse_research_artifact_uri(
                handoff.artifact_uri
            )
            references.append(
                ArtifactReportRef(
                    artifact_id=artifact_id,
                    artifact_type=artifact_type,
                    domain_owner=handoff.domain_owner,
                    uri=handoff.artifact_uri,
                )
            )
        return tuple(references)

    def to_dict(self) -> dict[str, Any]:
        """Serialize policy-visible state without transport or hidden data."""
        return {
            "task": self.task.to_dict(),
            "handoffs": [handoff.to_dict() for handoff in self.handoffs],
            "output_bindings": {
                key: list(value) for key, value in self.output_bindings.items()
            },
            "action_summaries": [
                summary.to_dict() for summary in self.action_summaries
            ],
            "decision_count": self.decision_count,
        }


class SpecialistPolicy(Protocol):
    """Propose one typed next action for a bounded specialist task."""

    async def decide(
        self,
        context: SpecialistPolicyContext,
    ) -> SpecialistDecision | Mapping[str, Any]:
        """Return one decision or strict JSON-compatible decision mapping."""


class SpecialistActionHandler(Protocol):
    """Execute one registered action through a specialist-owned adapter."""

    async def run(
        self,
        *,
        context: SpecialistPolicyContext,
        decision: SpecialistDecision,
    ) -> SpecialistActionOutcome | Mapping[str, Any]:
        """Return one bounded outcome without exposing raw adapter responses."""


class SpecialistPolicyError(RuntimeError):
    """Expected policy failure that should become a bounded graph error."""

    def __init__(self, code: str, message: str) -> None:
        """Initialize a stable policy error code and actionable message."""
        super().__init__(message)
        self.code = code


class SpecialistActionExecutionError(RuntimeError):
    """Expected registered-action failure safe to expose as a graph error."""

    def __init__(self, code: str, message: str) -> None:
        """Initialize a stable action error code and actionable message."""
        super().__init__(message)
        self.code = code
