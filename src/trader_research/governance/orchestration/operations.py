"""Define the durable operation boundary for costly research execution.

The operation record is replaceable operational state, not a research artifact. It
pins the request and execution identities, exposes bounded public status, and
makes ambiguous outcomes explicit so a caller can reconcile instead of blindly
replaying a side effect.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from ..handoffs import ArtifactReportRef, ResearchIssue
from ._validation import _enum_value, _mapping_sequence, _required_text


class ResearchOperationKind(str, Enum):
    """Costly research operations that use the durable job boundary."""

    BACKTEST = "backtest"
    OPTIMIZATION = "optimization"
    WALK_FORWARD = "walk_forward"
    TRAINING = "training"


class ResearchOperationMode(str, Enum):
    """Transport mode selected for a research operation."""

    SYNCHRONOUS_BOUNDED = "synchronous_bounded"
    DURABLE_JOB = "durable_job"


class ResearchJobStatus(str, Enum):
    """Public lifecycle states for one durable research job."""

    QUEUED = "queued"
    RUNNING = "running"
    PARTIAL = "partial"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    AMBIGUOUS = "ambiguous"
    RECONCILIATION_REQUIRED = "reconciliation_required"


DURABLE_OPERATION_KINDS = frozenset(ResearchOperationKind)


@dataclass(frozen=True)
class ResearchJob:
    """Bounded public state for one durable operation attempt.

    Job state pins the immutable request and execution identities. It contains
    no prompts, credentials, provider payloads, hidden reasoning, or checkpoint
    bytes. A terminal or ambiguous record is append-only; a retry is represented
    by a new attempt under the same idempotency key after reconciliation.
    """

    job_id: str
    operation_kind: ResearchOperationKind
    request_ref: str
    request_digest: str
    idempotency_key: str
    requested_by: str
    actor: str
    code_identity: str
    environment_identity: str
    status: ResearchJobStatus = ResearchJobStatus.QUEUED
    attempt: int = 0
    produced_artifact_refs: tuple[ArtifactReportRef, ...] = ()
    warnings: tuple[ResearchIssue, ...] = ()
    blockers: tuple[ResearchIssue, ...] = ()
    retryable: bool = False

    def __post_init__(self) -> None:
        """Validate identity, lifecycle, and bounded outcome rules."""
        for value, label in (
            (self.job_id, "job_id"),
            (self.request_ref, "request_ref"),
            (self.request_digest, "request_digest"),
            (self.idempotency_key, "idempotency_key"),
            (self.requested_by, "requested_by"),
            (self.actor, "actor"),
            (self.code_identity, "code_identity"),
            (self.environment_identity, "environment_identity"),
        ):
            _required_text(value, f"research job {label}")
        if self.attempt < 0:
            raise ValueError("research job attempt cannot be negative")
        refs = [item.uri for item in self.produced_artifact_refs]
        if len(refs) != len(set(refs)):
            raise ValueError("research job artifact refs must be unique")
        if self.status in {
            ResearchJobStatus.PARTIAL,
            ResearchJobStatus.FAILED,
            ResearchJobStatus.AMBIGUOUS,
            ResearchJobStatus.RECONCILIATION_REQUIRED,
        } and not self.blockers:
            raise ValueError(f"{self.status.value} jobs require blockers")
        if self.status is ResearchJobStatus.SUCCEEDED and self.retryable:
            raise ValueError("successful jobs cannot be retryable")
        if self.status is ResearchJobStatus.AMBIGUOUS and self.retryable:
            raise ValueError("ambiguous jobs require reconciliation before retry")

    @property
    def terminal(self) -> bool:
        """Return whether this public state cannot transition in place."""
        return self.status in {
            ResearchJobStatus.SUCCEEDED,
            ResearchJobStatus.FAILED,
            ResearchJobStatus.CANCELLED,
            ResearchJobStatus.AMBIGUOUS,
            ResearchJobStatus.RECONCILIATION_REQUIRED,
        }

    def to_dict(self) -> dict[str, Any]:
        """Serialize bounded job state for MCP and Console projections."""
        return {
            "job_id": self.job_id,
            "operation_kind": self.operation_kind.value,
            "request_ref": self.request_ref,
            "request_digest": self.request_digest,
            "idempotency_key": self.idempotency_key,
            "requested_by": self.requested_by,
            "actor": self.actor,
            "code_identity": self.code_identity,
            "environment_identity": self.environment_identity,
            "status": self.status.value,
            "attempt": self.attempt,
            "produced_artifact_refs": [item.to_dict() for item in self.produced_artifact_refs],
            "warnings": [item.to_dict() for item in self.warnings],
            "blockers": [item.to_dict() for item in self.blockers],
            "retryable": self.retryable,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ResearchJob":
        """Parse and validate one bounded job projection."""
        return cls(
            job_id=str(payload.get("job_id") or ""),
            operation_kind=_enum_value(
                ResearchOperationKind,
                payload.get("operation_kind"),
                "research operation kind",
            ),
            request_ref=str(payload.get("request_ref") or ""),
            request_digest=str(payload.get("request_digest") or ""),
            idempotency_key=str(payload.get("idempotency_key") or ""),
            requested_by=str(payload.get("requested_by") or ""),
            actor=str(payload.get("actor") or ""),
            code_identity=str(payload.get("code_identity") or ""),
            environment_identity=str(payload.get("environment_identity") or ""),
            status=_enum_value(
                ResearchJobStatus,
                payload.get("status"),
                "research job status",
            ),
            attempt=int(payload.get("attempt", 0)),
            produced_artifact_refs=tuple(
                ArtifactReportRef.from_dict(item)
                for item in _mapping_sequence(payload.get("produced_artifact_refs"))
            ),
            warnings=tuple(
                ResearchIssue.from_dict(item)
                for item in _mapping_sequence(payload.get("warnings"))
            ),
            blockers=tuple(
                ResearchIssue.from_dict(item)
                for item in _mapping_sequence(payload.get("blockers"))
            ),
            retryable=bool(payload.get("retryable", False)),
        )


def operation_mode(kind: ResearchOperationKind) -> ResearchOperationMode:
    """Return the selected mode for one operation kind.

    Validation, compilation, status reads, and reconciliation queries may remain
    synchronous bounded calls. The operation itself is always a durable job so
    all four costly paths share one recovery and idempotency contract.
    """
    if kind not in DURABLE_OPERATION_KINDS:
        raise ValueError(f"unsupported durable operation kind: {kind}")
    return ResearchOperationMode.DURABLE_JOB


__all__ = [
    "DURABLE_OPERATION_KINDS",
    "ResearchJob",
    "ResearchJobStatus",
    "ResearchOperationKind",
    "ResearchOperationMode",
    "operation_mode",
]
