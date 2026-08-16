"""Define bounded, typed payloads exchanged between research roles.

Handoffs carry canonical references, decision metadata, warnings, and blockers
instead of complete artifacts or hidden reasoning. Construction validates role
ownership so coordination cannot silently transfer specialist authority.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Sequence

from trader_research.foundation import (
    ResearchArtifactStoreError,
    parse_research_artifact_uri,
    research_artifact_uri,
)

from .artifacts import (
    DATASET_MANIFEST,
    DATA_QUALITY_REPORT,
    DRIFT_REPORT,
    EVALUATION_REPORT,
    FEATURE_MANIFEST,
    HYPOTHESIS_CARD,
    INDICATOR_METADATA,
    MODEL_CARD,
    DOMAIN_OWNER_BY_ARTIFACT_TYPE,
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
        """Build and validate a bounded research request from plain data.

        Missing artifact collections use the maintained required and optional
        defaults. Nested Data requirements are parsed through their own contract,
        and constructor validation rejects blank identity or unsupported types.

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
        domain_owner: Bounded context authoritative for the artifact.
        producer_tool: Deterministic tool or service operation that produced it.
        requested_by: Operator request or workflow reference requiring the operation.
        actor: Operator or agent identity that routed the operation.
        artifact_type: Stable artifact type.
        artifact_uri: Optional canonical Postgres artifact URI.
        payload: Optional structured artifact summary.
        source_request: Source request or parameters that produced the artifact.
        provenance_refs: Provenance references back to results, graph state, or runs.
        warnings: Structured non-fatal warnings.
        blockers: Structured blockers.
    """

    handoff_id: str
    domain_owner: str
    producer_tool: str
    requested_by: str
    actor: str
    artifact_type: str
    artifact_uri: str | None = None
    payload: Mapping[str, Any] = field(default_factory=dict)
    source_request: Mapping[str, Any] = field(default_factory=dict)
    provenance_refs: Mapping[str, Any] = field(default_factory=dict)
    warnings: tuple[ResearchIssue, ...] = field(default_factory=tuple)
    blockers: tuple[ResearchIssue, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        """Validate artifact authority, provenance, and payload shape."""
        if not self.handoff_id.strip():
            raise ValueError("handoff_id is required")
        if not self.domain_owner.strip():
            raise ValueError("domain_owner is required")
        if not self.producer_tool.strip():
            raise ValueError("producer_tool is required")
        if not self.requested_by.strip():
            raise ValueError("requested_by is required")
        if not self.actor.strip():
            raise ValueError("actor is required")
        if self.artifact_type not in SUPPORTED_ARTIFACT_TYPES:
            raise ValueError(f"unsupported artifact type: {self.artifact_type}")
        expected_owner = DOMAIN_OWNER_BY_ARTIFACT_TYPE.get(self.artifact_type)
        if expected_owner is not None and self.domain_owner != expected_owner:
            raise ValueError(
                f"{self.artifact_type} must be owned by the {expected_owner} domain"
            )
        if self.artifact_uri is None and not self.payload:
            raise ValueError("artifact_uri or payload is required")
        if self.artifact_uri is not None:
            try:
                uri_type, _ = parse_research_artifact_uri(self.artifact_uri)
            except ResearchArtifactStoreError as exc:
                raise ValueError(str(exc)) from exc
            if uri_type != self.artifact_type:
                raise ValueError(
                    f"artifact_uri type {uri_type} does not match {self.artifact_type}"
                )

    def to_dict(self) -> dict[str, Any]:
        """Serialize a handoff to bounded agent-visible plain data.

        Payload, source request, and provenance values are normalized recursively;
        warnings and blockers retain their structured issue shapes. The result
        contains no hidden reasoning or complete artifact loaded from its URI.
        """
        payload = {
            "handoff_id": self.handoff_id,
            "domain_owner": self.domain_owner,
            "producer_tool": self.producer_tool,
            "requested_by": self.requested_by,
            "actor": self.actor,
            "artifact_type": self.artifact_type,
            "artifact_uri": self.artifact_uri,
            "payload": _jsonable(self.payload),
            "source_request": _jsonable(self.source_request),
            "provenance_refs": _jsonable(self.provenance_refs),
            "warnings": [warning.to_dict() for warning in self.warnings],
            "blockers": [blocker.to_dict() for blocker in self.blockers],
        }
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SpecialistHandoff":
        """Build and validate a specialist handoff from plain data.

        Nested issues and mappings are normalized before constructor validation
        checks domain ownership, required provenance, supported artifact type, and
        URI/type agreement.

        Args:
            payload: Mapping containing handoff fields.

        Returns:
            Parsed specialist handoff.
        """
        return cls(
            handoff_id=str(payload.get("handoff_id") or ""),
            domain_owner=str(payload.get("domain_owner") or ""),
            producer_tool=str(payload.get("producer_tool") or ""),
            requested_by=str(payload.get("requested_by") or ""),
            actor=str(payload.get("actor") or ""),
            artifact_type=str(payload.get("artifact_type") or ""),
            artifact_uri=str(payload["artifact_uri"])
            if payload.get("artifact_uri") is not None
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
        domain_owner: Bounded context authoritative for the artifact.
        required: Whether absence is a blocker.
        status: Slot status such as missing, accepted, blocked, or optional_missing.
        handoff: Optional accepted specialist handoff.
        blockers: Structured blockers attached to the slot.
    """

    slot_key: str
    artifact_type: str
    domain_owner: str
    required: bool
    status: str = "missing"
    handoff: SpecialistHandoff | None = None
    blockers: tuple[ResearchIssue, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        """Serialize slot state, accepted handoff details, and blocker payloads for supervisors."""
        return {
            "slot_key": self.slot_key,
            "artifact_type": self.artifact_type,
            "domain_owner": self.domain_owner,
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

    Construction verifies that the artifact type is known, that domain authority
    matches the registry, and that a stable artifact ID exists.
    The reference is used when a supervisor needs to cite or require an artifact
    without loading the full report payload into the current message.
    """

    artifact_id: str
    artifact_type: str
    domain_owner: str
    uri: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate artifact type, domain authority, and non-empty identity."""
        if self.artifact_type not in SUPPORTED_ARTIFACT_TYPES:
            raise ValueError(f"unsupported artifact type: {self.artifact_type}")
        if DOMAIN_OWNER_BY_ARTIFACT_TYPE[self.artifact_type] != self.domain_owner:
            raise ValueError(
                f"{self.artifact_type} must be owned by the "
                f"{DOMAIN_OWNER_BY_ARTIFACT_TYPE[self.artifact_type]} domain"
            )
        if not self.artifact_id.strip():
            raise ValueError("artifact_id is required")
        try:
            uri_type, uri_id = parse_research_artifact_uri(self.uri)
        except ResearchArtifactStoreError as exc:
            raise ValueError(str(exc)) from exc
        if uri_type != self.artifact_type or uri_id != self.artifact_id:
            raise ValueError("artifact URI identity does not match artifact reference")

    def to_dict(self) -> dict[str, Any]:
        """Serialize artifact identity, authority, URI, and normalized metadata."""
        return {
            "artifact_id": self.artifact_id,
            "artifact_type": self.artifact_type,
            "domain_owner": self.domain_owner,
            "uri": self.uri,
            "metadata": _jsonable(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ArtifactReportRef":
        """Build an artifact reference from JSON-compatible data."""
        return cls(
            artifact_id=str(payload.get("artifact_id") or ""),
            artifact_type=str(payload.get("artifact_type") or ""),
            domain_owner=str(payload.get("domain_owner") or ""),
            uri=str(payload.get("uri") or ""),
            metadata=_mapping(payload.get("metadata")),
        )


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


def artifact_report_ref(artifact_type: str, artifact_id: str) -> ArtifactReportRef:
    """Build a generic typed artifact reference.

    Args:
        artifact_type: Stable artifact type.
        artifact_id: Stable artifact identifier.
    Returns:
        Typed artifact report reference.
    """
    return ArtifactReportRef(
        artifact_id=artifact_id,
        artifact_type=artifact_type,
        domain_owner=DOMAIN_OWNER_BY_ARTIFACT_TYPE[artifact_type],
        uri=research_artifact_uri(artifact_type, artifact_id),
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
