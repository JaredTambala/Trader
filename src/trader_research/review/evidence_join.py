"""Join exact experiment evidence across independent research contexts.

This module owns the deterministic seam between Experiment Design, execution,
independent Review, and the terminal decision record. Callers normalize
canonical artifact rows into :class:`EvidenceJoinRef` values before invoking the
pure verifier. The verifier never loads a store, infers a latest revision, or
turns a positive review into approval.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from trader_research.foundation import parse_research_artifact_uri
from trader_research.governance.handoffs import ArtifactReportRef


class EvidenceJoinStatus(StrEnum):
    """Availability state retained for one joined artifact."""

    AVAILABLE = "available"
    PARTIAL = "partial"
    MISSING = "missing"
    INCOMPATIBLE = "incompatible"
    STALE = "stale"
    NEGATIVE = "negative"


class EvidenceJoinVerdict(StrEnum):
    """Aggregate lineage result; this is not a trading or approval verdict."""

    COMPLETE = "complete"
    PARTIAL = "partial"
    BLOCKED = "blocked"


_REQUIRED_ROLE_FIELDS: dict[str, tuple[str, ...]] = {
    "proposal": ("experiment_id", "proposal_id"),
    "approval": ("experiment_id", "proposal_id"),
    "scope": ("experiment_id", "proposal_id", "scope_id"),
    "strategy": ("experiment_id", "proposal_id", "strategy_version_id"),
    "run": (
        "experiment_id",
        "proposal_id",
        "scope_id",
        "strategy_version_id",
        "run_id",
    ),
    "evaluation": (
        "experiment_id",
        "proposal_id",
        "scope_id",
        "strategy_version_id",
        "run_id",
    ),
    "robustness": (
        "experiment_id",
        "proposal_id",
        "scope_id",
        "strategy_version_id",
        "run_id",
    ),
    "decision": (
        "experiment_id",
        "proposal_id",
        "scope_id",
        "strategy_version_id",
        "run_id",
    ),
}
_REQUIRED_ROLES = tuple(_REQUIRED_ROLE_FIELDS)
_BLOCKING_STATUSES = frozenset(
    {
        EvidenceJoinStatus.MISSING,
        EvidenceJoinStatus.INCOMPATIBLE,
        EvidenceJoinStatus.STALE,
    }
)


@dataclass(frozen=True)
class EvidenceJoinRef:
    """One exact, public artifact revision participating in a join.

    ``lineage`` is a bounded projection of producer-owned identity fields. It is
    deliberately explicit so a review cannot accidentally join by artifact type
    alone. The reference metadata must pin a payload or source hash, and the
    revision is part of the immutable key even when the underlying store uses a
    content-addressed artifact ID.
    """

    role: str
    reference: ArtifactReportRef
    revision: int
    status: EvidenceJoinStatus
    lineage: Mapping[str, str]
    limitations: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()
    statistical_status: str | None = None
    robustness_status: str | None = None
    comparison_status: str | None = None

    def __post_init__(self) -> None:
        """Reject ambiguous identity, unpinned revisions, or private fields."""
        if self.role not in _REQUIRED_ROLE_FIELDS:
            raise ValueError(f"unsupported evidence join role: {self.role}")
        if isinstance(self.revision, bool) or not isinstance(self.revision, int) or self.revision < 1:
            raise ValueError("evidence join revision must be positive")
        if not isinstance(self.status, EvidenceJoinStatus):
            raise ValueError("evidence join status is unsupported")
        parsed_type, parsed_id = parse_research_artifact_uri(self.reference.uri)
        if parsed_type != self.reference.artifact_type or parsed_id != self.reference.artifact_id:
            raise ValueError("evidence join reference URI identity does not match")
        if not (self.reference.metadata.get("payload_sha256") or self.reference.metadata.get("source_hash")):
            raise ValueError("evidence join references require a pinned payload or source hash")
        if not isinstance(self.lineage, Mapping) or any(
            not isinstance(key, str) or not key.strip() or not isinstance(value, str) or not value.strip()
            for key, value in self.lineage.items()
        ):
            raise ValueError("evidence join lineage must contain bounded text")
        for values, label in ((self.limitations, "limitations"), (self.blockers, "blockers")):
            if len(values) > 32 or any(not isinstance(value, str) or not value.strip() for value in values):
                raise ValueError(f"evidence join {label} must contain bounded text")
        for value, label in (
            (self.statistical_status, "statistical_status"),
            (self.robustness_status, "robustness_status"),
            (self.comparison_status, "comparison_status"),
        ):
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"evidence join {label} must contain bounded text")

    @property
    def key(self) -> str:
        """Return role plus exact artifact revision identity."""
        return f"{self.role}:{self.reference.artifact_type}:{self.reference.artifact_id}:r{self.revision}"

    def to_dict(self) -> dict[str, Any]:
        """Serialize the redacted public projection."""
        return {
            "role": self.role,
            "key": self.key,
            "reference": self.reference.to_dict(),
            "revision": self.revision,
            "status": self.status.value,
            "lineage": dict(sorted(self.lineage.items())),
            "limitations": list(self.limitations),
            "blockers": list(self.blockers),
            "statistical_status": self.statistical_status,
            "robustness_status": self.robustness_status,
            "comparison_status": self.comparison_status,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "EvidenceJoinRef":
        """Parse one strict persisted public projection."""
        allowed = {
            "role", "key", "reference", "revision", "status", "lineage",
            "limitations", "blockers", "statistical_status", "robustness_status",
            "comparison_status",
        }
        unknown = set(payload).difference(allowed)
        if unknown:
            raise ValueError("evidence join ref contains unknown fields: " + ", ".join(sorted(unknown)))
        reference_payload = payload.get("reference")
        if not isinstance(reference_payload, Mapping):
            raise ValueError("evidence join ref reference must be an object")
        ref = cls(
            role=str(payload.get("role") or ""),
            reference=ArtifactReportRef.from_dict(reference_payload),
            revision=_positive_int(payload.get("revision"), "revision"),
            status=EvidenceJoinStatus(str(payload.get("status") or "")),
            lineage=_text_mapping(payload.get("lineage")),
            limitations=_text_tuple(payload.get("limitations")),
            blockers=_text_tuple(payload.get("blockers")),
            statistical_status=_optional_text(payload.get("statistical_status")),
            robustness_status=_optional_text(payload.get("robustness_status")),
            comparison_status=_optional_text(payload.get("comparison_status")),
        )
        if payload.get("key") not in (None, ref.key):
            raise ValueError("evidence join ref key does not match identity")
        return ref


@dataclass(frozen=True)
class EvidenceJoinResult:
    """Stable verifier output for one complete experiment evidence chain."""

    experiment_id: str
    proposal_id: str
    scope_id: str
    strategy_version_id: str
    run_id: str
    evidence_revision: int
    records: tuple[EvidenceJoinRef, ...]
    blockers: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Validate aggregate identity and unique role/revision records."""
        for value, label in (
            (self.experiment_id, "experiment_id"),
            (self.proposal_id, "proposal_id"),
            (self.scope_id, "scope_id"),
            (self.strategy_version_id, "strategy_version_id"),
            (self.run_id, "run_id"),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"evidence join {label} is required")
        if isinstance(self.evidence_revision, bool) or self.evidence_revision < 1:
            raise ValueError("evidence join evidence_revision must be positive")
        keys = [record.key for record in self.records]
        if len(keys) != len(set(keys)):
            raise ValueError("evidence join records must have unique exact revisions")
        roles = [record.role for record in self.records]
        if len(roles) != len(set(roles)):
            raise ValueError("evidence join records must have one record per role")
        for values, label in ((self.blockers, "blockers"), (self.warnings, "warnings")):
            if len(values) > 64 or any(not isinstance(value, str) or not value.strip() for value in values):
                raise ValueError(f"evidence join {label} must contain bounded text")

    @property
    def verdict(self) -> EvidenceJoinVerdict:
        """Classify lineage completeness while retaining negative findings."""
        if self.blockers or any(record.status in _BLOCKING_STATUSES for record in self.records):
            return EvidenceJoinVerdict.BLOCKED
        if any(record.status is not EvidenceJoinStatus.AVAILABLE for record in self.records) or self.warnings:
            return EvidenceJoinVerdict.PARTIAL
        return EvidenceJoinVerdict.COMPLETE

    @property
    def terminal_summary(self) -> dict[str, Any]:
        """Return review fields required by the terminal human readout."""
        limitations = sorted({item for record in self.records for item in record.limitations})
        blockers = sorted({*self.blockers, *(item for record in self.records for item in record.blockers)})
        evaluation = next((item for item in self.records if item.role == "evaluation"), None)
        robustness = next((item for item in self.records if item.role == "robustness"), None)
        return {
            "statistical_status": evaluation.statistical_status if evaluation else None,
            "robustness_status": robustness.robustness_status if robustness else None,
            "comparison_status": evaluation.comparison_status if evaluation else None,
            "limitations": limitations,
            "blockers": blockers,
        }

    def to_dict(self) -> dict[str, Any]:
        """Serialize deterministic verifier output without artifact payloads."""
        return {
            "schema_version": "1",
            "experiment_id": self.experiment_id,
            "proposal_id": self.proposal_id,
            "scope_id": self.scope_id,
            "strategy_version_id": self.strategy_version_id,
            "run_id": self.run_id,
            "evidence_revision": self.evidence_revision,
            "verdict": self.verdict.value,
            "records": [record.to_dict() for record in sorted(self.records, key=lambda item: item.key)],
            "blockers": sorted(set(self.blockers)),
            "warnings": sorted(set(self.warnings)),
            "terminal_summary": self.terminal_summary,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "EvidenceJoinResult":
        """Reopen and revalidate a retained verifier output."""
        if payload.get("schema_version") != "1":
            raise ValueError("evidence join schema version is unsupported")
        records = payload.get("records")
        if not isinstance(records, list):
            raise ValueError("evidence join records must be a list")
        result = cls(
            experiment_id=str(payload.get("experiment_id") or ""),
            proposal_id=str(payload.get("proposal_id") or ""),
            scope_id=str(payload.get("scope_id") or ""),
            strategy_version_id=str(payload.get("strategy_version_id") or ""),
            run_id=str(payload.get("run_id") or ""),
            evidence_revision=_positive_int(payload.get("evidence_revision"), "evidence_revision"),
            records=tuple(EvidenceJoinRef.from_dict(item) for item in records if isinstance(item, Mapping)),
            blockers=_text_tuple(payload.get("blockers")),
            warnings=_text_tuple(payload.get("warnings")),
        )
        if payload.get("verdict") not in (None, result.verdict.value):
            raise ValueError("evidence join verdict does not match records")
        if payload.get("terminal_summary") not in (None, result.terminal_summary):
            raise ValueError("evidence join terminal summary does not match records")
        return result


def qualify_evidence_join(
    *,
    experiment_id: str,
    proposal_id: str,
    scope_id: str,
    strategy_version_id: str,
    run_id: str,
    evidence_revision: int,
    records: Sequence[EvidenceJoinRef],
) -> EvidenceJoinResult:
    """Verify exact identity across proposal, execution, review, and decision refs.

    The function is deliberately a pure verifier. A caller must supply the
    records returned by exact canonical reads; it cannot ask this function for a
    latest artifact or silently replace a missing producer. Every role declares
    the identity fields it must carry, and mismatches become blockers.
    """
    result = EvidenceJoinResult(
        experiment_id=experiment_id,
        proposal_id=proposal_id,
        scope_id=scope_id,
        strategy_version_id=strategy_version_id,
        run_id=run_id,
        evidence_revision=evidence_revision,
        records=tuple(records),
    )
    by_role = {record.role: record for record in result.records}
    blockers: list[str] = []
    warnings: list[str] = []
    expected = {
        "experiment_id": experiment_id,
        "proposal_id": proposal_id,
        "scope_id": scope_id,
        "strategy_version_id": strategy_version_id,
        "run_id": run_id,
    }
    for role in _REQUIRED_ROLES:
        record = by_role.get(role)
        if record is None:
            blockers.append(f"required evidence role is missing: {role}")
            continue
        missing_fields = [field for field in _REQUIRED_ROLE_FIELDS[role] if field not in record.lineage]
        if missing_fields:
            blockers.append(f"{role} lineage is missing: {', '.join(missing_fields)}")
        mismatches = [
            field for field in _REQUIRED_ROLE_FIELDS[role]
            if field in record.lineage and record.lineage[field] != expected[field]
        ]
        if mismatches:
            blockers.append(f"{role} lineage does not match: {', '.join(mismatches)}")
        if record.status is EvidenceJoinStatus.PARTIAL:
            warnings.append(f"{role} evidence is partial")
        elif record.status is EvidenceJoinStatus.NEGATIVE:
            warnings.append(f"{role} evidence is negative")
        if record.blockers:
            blockers.extend(f"{role}: {item}" for item in record.blockers)
    unknown_roles = sorted(set(by_role).difference(_REQUIRED_ROLES))
    blockers.extend(f"unsupported evidence role: {role}" for role in unknown_roles)
    return EvidenceJoinResult(
        experiment_id=result.experiment_id,
        proposal_id=result.proposal_id,
        scope_id=result.scope_id,
        strategy_version_id=result.strategy_version_id,
        run_id=result.run_id,
        evidence_revision=result.evidence_revision,
        records=result.records,
        blockers=tuple(sorted(set(blockers))),
        warnings=tuple(sorted(set(warnings))),
    )


def _positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"evidence join {label} must be positive")
    return value


def _text_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str) or not isinstance(value, Sequence):
        raise ValueError("evidence join text values must be lists")
    return tuple(str(item) for item in value)


def _text_mapping(value: Any) -> Mapping[str, str]:
    if not isinstance(value, Mapping):
        raise ValueError("evidence join lineage must be an object")
    return {str(key): str(item) for key, item in value.items()}


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError("evidence join optional text must be non-empty text")
    return value


__all__ = [
    "EvidenceJoinRef",
    "EvidenceJoinResult",
    "EvidenceJoinStatus",
    "EvidenceJoinVerdict",
    "qualify_evidence_join",
]
