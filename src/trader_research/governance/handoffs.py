"""Typed research-domain schemas for supervisor handoffs."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Sequence

from .artifacts import (
    DATASET_MANIFEST,
    DATA_QUALITY_REPORT,
    DRIFT_REPORT,
    EVALUATION_REPORT,
    FEATURE_MANIFEST,
    HYPOTHESIS_CARD,
    INDICATOR_METADATA,
    MODEL_CARD,
    OWNER_BY_ARTIFACT_TYPE,
    PREDICTION_ARTIFACT,
    ROBUSTNESS_REPORT,
    SUPPORTED_ARTIFACT_TYPES,
)

class ResearchVerdictValue(str, Enum):
    """Stable verdict vocabulary emitted by the supervisor research workflow.

    These string values are serialized into handoff artifacts and should remain
    stable across agents. They describe whether the supervisor can proceed, needs
    more evidence, rejected the idea, found it promising, or considers the result
    ready for human review.
    """

    BLOCKED = "blocked"
    NEEDS_EVIDENCE = "needs_evidence"
    REJECTED = "rejected"
    PROMISING = "promising"
    READY_FOR_REVIEW = "ready_for_review"


@dataclass(frozen=True)
class ResearchIssue:
    """Structured warning, blocker, or error attached to a handoff.

    Attributes:
        code: Stable machine-readable issue code.
        message: Human-readable issue message.
        details: Optional JSON-compatible detail mapping.
    """

    code: str
    message: str
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate issue code and message fields before handoff serialization."""
        if not self.code.strip():
            raise ValueError("issue code is required")
        if not self.message.strip():
            raise ValueError("issue message is required")

    def to_dict(self) -> dict[str, Any]:
        """Serialize the issue into the stable warning/blocker payload shape used by handoffs."""
        return {
            "code": self.code,
            "message": self.message,
            "details": _jsonable(self.details),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ResearchIssue":
        """Build an issue from JSON-compatible data.

        Args:
            payload: Mapping containing code, message, and optional details.

        Returns:
            Parsed issue.
        """
        return cls(
            code=str(payload.get("code") or ""),
            message=str(payload.get("message") or ""),
            details=_mapping(payload.get("details")),
        )


@dataclass(frozen=True)
class DataRequirement:
    """Bounded market-data requirement for a research request.

    Attributes:
        symbols: Requested symbol universe.
        asset_class: Requested asset class.
        timeframe: Requested bar timeframe.
        start: Inclusive requested start timestamp as ISO-8601 text.
        end: Inclusive requested end timestamp as ISO-8601 text.
        source: Optional source or feed name.
    """

    symbols: tuple[str, ...]
    asset_class: str
    timeframe: str
    start: str
    end: str
    source: str | None = None

    def __post_init__(self) -> None:
        """Validate symbol universe, asset class, timeframe, and window bounds."""
        if not self.symbols:
            raise ValueError("data requirement symbols are required")
        if len(self.symbols) > 20:
            raise ValueError("data requirement supports at most 20 symbols")
        if not self.asset_class.strip():
            raise ValueError("data requirement asset_class is required")
        if not self.timeframe.strip():
            raise ValueError("data requirement timeframe is required")
        if not self.start.strip() or not self.end.strip():
            raise ValueError("data requirement start and end are required")

    def to_dict(self) -> dict[str, Any]:
        """Serialize bounded data requirements, including optional source only when present in artifacts."""
        payload: dict[str, Any] = {
            "symbols": list(self.symbols),
            "asset_class": self.asset_class,
            "timeframe": self.timeframe,
            "start": self.start,
            "end": self.end,
        }
        if self.source is not None:
            payload["source"] = self.source
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "DataRequirement":
        """Build a data requirement from JSON-compatible data.

        Args:
            payload: Mapping containing symbols, asset class, timeframe, and window.

        Returns:
            Parsed data requirement.
        """
        return cls(
            symbols=tuple(str(symbol) for symbol in _sequence(payload.get("symbols"))),
            asset_class=str(payload.get("asset_class") or ""),
            timeframe=str(payload.get("timeframe") or ""),
            start=str(payload.get("start") or ""),
            end=str(payload.get("end") or ""),
            source=str(payload["source"])
            if payload.get("source") is not None
            else None,
        )


@dataclass(frozen=True)
class BoundedResearchRequest:
    """Supervisor research request with explicit data bounds.

    Attributes:
        request_id: Stable request identifier.
        objective: Human-supplied research objective treated as data.
        data_requirement: Bounded data requirement for the workflow.
        required_artifacts: Artifact types required before the request can proceed.
        optional_artifacts: Artifact types that may improve the workflow but are not blockers.
    """

    request_id: str
    objective: str
    data_requirement: DataRequirement
    required_artifacts: tuple[str, ...] = (
        DATASET_MANIFEST,
        DATA_QUALITY_REPORT,
        INDICATOR_METADATA,
        HYPOTHESIS_CARD,
        EVALUATION_REPORT,
        ROBUSTNESS_REPORT,
    )
    optional_artifacts: tuple[str, ...] = (
        FEATURE_MANIFEST,
        MODEL_CARD,
        PREDICTION_ARTIFACT,
        DRIFT_REPORT,
    )

    def __post_init__(self) -> None:
        """Validate request identifiers, objective, and artifact types."""
        if not self.request_id.strip():
            raise ValueError("research request_id is required")
        if not self.objective.strip():
            raise ValueError("research objective is required")
        _validate_artifact_types(self.required_artifacts)
        _validate_artifact_types(self.optional_artifacts)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the bounded request and its required/optional artifact contracts for agents."""
        return {
            "request_id": self.request_id,
            "objective": self.objective,
            "data_requirement": self.data_requirement.to_dict(),
            "required_artifacts": list(self.required_artifacts),
            "optional_artifacts": list(self.optional_artifacts),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "BoundedResearchRequest":
        """Build a bounded request from JSON-compatible data.

        Args:
            payload: Mapping containing request fields.

        Returns:
            Parsed bounded research request.
        """
        return cls(
            request_id=str(payload.get("request_id") or ""),
            objective=str(payload.get("objective") or ""),
            data_requirement=DataRequirement.from_dict(
                _mapping(payload.get("data_requirement"))
            ),
            required_artifacts=tuple(
                str(item) for item in _sequence(payload.get("required_artifacts"))
            )
            or BoundedResearchRequest.required_artifacts,
            optional_artifacts=tuple(
                str(item) for item in _sequence(payload.get("optional_artifacts"))
            )
            or BoundedResearchRequest.optional_artifacts,
        )


@dataclass(frozen=True)
class SpecialistHandoff:
    """Artifact handoff from a producing specialist to the supervisor.

    Attributes:
        handoff_id: Stable handoff identifier.
        agent_owner: Producing agent display name.
        artifact_type: Stable artifact type.
        artifact_path: Optional local artifact path.
        payload: Optional structured artifact summary.
        source_request: Source request or parameters that produced the artifact.
        provenance_refs: Provenance references back to results, graph state, or runs.
        warnings: Structured non-fatal warnings.
        blockers: Structured blockers.
    """

    handoff_id: str
    agent_owner: str
    artifact_type: str
    artifact_path: str | None = None
    payload: Mapping[str, Any] = field(default_factory=dict)
    source_request: Mapping[str, Any] = field(default_factory=dict)
    provenance_refs: Mapping[str, Any] = field(default_factory=dict)
    warnings: tuple[ResearchIssue, ...] = field(default_factory=tuple)
    blockers: tuple[ResearchIssue, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        """Validate artifact ownership and payload shape."""
        if not self.handoff_id.strip():
            raise ValueError("handoff_id is required")
        if not self.agent_owner.strip():
            raise ValueError("agent_owner is required")
        if self.artifact_type not in SUPPORTED_ARTIFACT_TYPES:
            raise ValueError(f"unsupported artifact type: {self.artifact_type}")
        expected_owner = OWNER_BY_ARTIFACT_TYPE.get(self.artifact_type)
        if expected_owner is not None and self.agent_owner != expected_owner:
            raise ValueError(f"{self.artifact_type} must be owned by {expected_owner}")
        if self.artifact_path is None and not self.payload:
            raise ValueError("artifact_path or payload is required")

    def to_dict(self) -> dict[str, Any]:
        """Serialize the handoff while normalizing payloads, provenance, warnings, and blockers for agents."""
        payload = {
            "handoff_id": self.handoff_id,
            "agent_owner": self.agent_owner,
            "artifact_type": self.artifact_type,
            "artifact_path": self.artifact_path,
            "payload": _jsonable(self.payload),
            "source_request": _jsonable(self.source_request),
            "provenance_refs": _jsonable(self.provenance_refs),
            "warnings": [warning.to_dict() for warning in self.warnings],
            "blockers": [blocker.to_dict() for blocker in self.blockers],
        }
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SpecialistHandoff":
        """Build a handoff from JSON-compatible data.

        Args:
            payload: Mapping containing handoff fields.

        Returns:
            Parsed specialist handoff.
        """
        return cls(
            handoff_id=str(payload.get("handoff_id") or ""),
            agent_owner=str(payload.get("agent_owner") or ""),
            artifact_type=str(payload.get("artifact_type") or ""),
            artifact_path=str(payload["artifact_path"])
            if payload.get("artifact_path") is not None
            else None,
            payload=_mapping(payload.get("payload")),
            source_request=_mapping(payload.get("source_request")),
            provenance_refs=_mapping(payload.get("provenance_refs")),
            warnings=tuple(
                ResearchIssue.from_dict(item)
                for item in _mapping_sequence(payload.get("warnings"))
            ),
            blockers=tuple(
                ResearchIssue.from_dict(item)
                for item in _mapping_sequence(payload.get("blockers"))
            ),
        )


@dataclass(frozen=True)
class SpecialistArtifactSlot:
    """Supervisor slot tracking whether a specialist artifact is present.

    Attributes:
        slot_key: Stable state slot key.
        artifact_type: Required or optional artifact type.
        agent_owner: Owning specialist agent.
        required: Whether absence is a blocker.
        status: Slot status such as missing, accepted, blocked, or optional_missing.
        handoff: Optional accepted specialist handoff.
        blockers: Structured blockers attached to the slot.
    """

    slot_key: str
    artifact_type: str
    agent_owner: str
    required: bool
    status: str = "missing"
    handoff: SpecialistHandoff | None = None
    blockers: tuple[ResearchIssue, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        """Serialize slot state, accepted handoff details, and blocker payloads for supervisors."""
        return {
            "slot_key": self.slot_key,
            "artifact_type": self.artifact_type,
            "agent_owner": self.agent_owner,
            "required": self.required,
            "status": self.status,
            "handoff": self.handoff.to_dict() if self.handoff is not None else None,
            "blockers": [blocker.to_dict() for blocker in self.blockers],
        }


@dataclass(frozen=True)
class ExperimentPlan:
    """Supervisor-owned plan that names data and strategy specification IDs.

    The plan is intentionally lightweight: it references normalized data
    requirements and specification identifiers rather than embedding run outputs. This
    keeps upstream planning artifacts serializable and lets later evaluation steps
    attach concrete backtest references as separate handoffs.
    """

    plan_id: str
    request_id: str
    data_requirements: tuple[DataRequirement, ...]
    strategy_specifications: tuple[str, ...] = ()
    status: str = "draft"

    def to_dict(self) -> dict[str, Any]:
        """Serialize data requirements and strategy specification references."""
        return {
            "plan_id": self.plan_id,
            "request_id": self.request_id,
            "data_requirements": [item.to_dict() for item in self.data_requirements],
            "strategy_specifications": list(self.strategy_specifications),
            "status": self.status,
        }


@dataclass(frozen=True)
class ArtifactReportRef:
    """Typed pointer to a specialist-produced report or artifact file.

    Construction verifies that the artifact type is known, that ownership matches
    the registered agent for that artifact, and that a stable artifact ID exists.
    The reference is used when a supervisor needs to cite or require an artifact
    without loading the full report payload into the current message.
    """

    artifact_id: str
    artifact_type: str
    agent_owner: str
    path: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate artifact type, expected owner, and non-empty artifact identity."""
        if self.artifact_type not in SUPPORTED_ARTIFACT_TYPES:
            raise ValueError(f"unsupported artifact type: {self.artifact_type}")
        if OWNER_BY_ARTIFACT_TYPE[self.artifact_type] != self.agent_owner:
            raise ValueError(
                f"{self.artifact_type} must be owned by {OWNER_BY_ARTIFACT_TYPE[self.artifact_type]}"
            )
        if not self.artifact_id.strip():
            raise ValueError("artifact_id is required")

    def to_dict(self) -> dict[str, Any]:
        """Serialize artifact identity, ownership, optional path, and normalized metadata for review."""
        return {
            "artifact_id": self.artifact_id,
            "artifact_type": self.artifact_type,
            "agent_owner": self.agent_owner,
            "path": self.path,
            "metadata": _jsonable(self.metadata),
        }


@dataclass(frozen=True)
class ResearchVerdict:
    """Final supervisor judgment tied to a bounded research request.

    The verdict combines a stable verdict ID, the originating request ID, a
    constrained `ResearchVerdictValue`, and structured reasons. It is designed for
    audit trails: downstream tools can inspect the machine-readable value while
    reviewers can read the attached issue messages.
    """

    verdict_id: str
    request_id: str
    verdict: ResearchVerdictValue
    reasons: tuple[ResearchIssue, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the verdict value and structured reasons for downstream audit trails."""
        return {
            "verdict_id": self.verdict_id,
            "request_id": self.request_id,
            "verdict": self.verdict.value,
            "reasons": [reason.to_dict() for reason in self.reasons],
        }


def artifact_report_ref(
    artifact_type: str, artifact_id: str, *, path: str | Path | None = None
) -> ArtifactReportRef:
    """Build a generic typed artifact reference.

    Args:
        artifact_type: Stable artifact type.
        artifact_id: Stable artifact identifier.
        path: Optional local artifact path.

    Returns:
        Typed artifact report reference.
    """
    return ArtifactReportRef(
        artifact_id=artifact_id,
        artifact_type=artifact_type,
        agent_owner=OWNER_BY_ARTIFACT_TYPE[artifact_type],
        path=str(path) if path is not None else None,
    )


def _validate_artifact_types(values: Sequence[str]) -> None:
    """Validate a sequence of artifact type names."""
    for value in values:
        if value not in SUPPORTED_ARTIFACT_TYPES:
            raise ValueError(f"unsupported artifact type: {value}")


def _mapping(value: object) -> Mapping[str, Any]:
    """Return a mapping or an empty mapping."""
    if isinstance(value, Mapping):
        return value
    return {}


def _sequence(value: object) -> Sequence[Any]:
    """Return a sequence or an empty tuple."""
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return value
    return ()


def _mapping_sequence(value: object) -> list[Mapping[str, Any]]:
    """Return only mapping values from a candidate sequence."""
    return [item for item in _sequence(value) if isinstance(item, Mapping)]


def _jsonable(value: Any) -> Any:
    """Convert supported Python values to JSON-compatible values."""
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): _jsonable(val) for key, val in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return value.to_dict()
    return value
