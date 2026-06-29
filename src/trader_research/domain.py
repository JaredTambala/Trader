"""Typed research-domain schemas for supervisor handoffs."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from .contracts import SideEffect


DATA_AGENT_OWNER = "Data Agent"
QUANT_RESEARCH_SUPERVISOR_OWNER = "Quant Research Supervisor Agent"
QUANTITATIVE_METHODS_OWNER = "Quantitative Methods Agent"
MATH_CODER_OWNER = QUANTITATIVE_METHODS_OWNER
ML_AGENT_OWNER = "ML Agent"
HYPOTHESIS_AGENT_OWNER = "Hypothesis Agent"
EVALUATION_AGENT_OWNER = "Evaluation Agent"
ADVERSARIAL_AGENT_OWNER = "Adversarial Agent"

DATASET_MANIFEST = "dataset_manifest"
DATA_QUALITY_REPORT = "data_quality_report"
HYPOTHESIS_CARD = "hypothesis_card"
KNOWLEDGE_SOURCE_MANIFEST = "knowledge_source_manifest"
KNOWLEDGE_INGESTION_REPORT = "knowledge_ingestion_report"
KNOWLEDGE_CHUNK_MANIFEST = "knowledge_chunk_manifest"
KNOWLEDGE_EMBEDDING_MANIFEST = "knowledge_embedding_manifest"
METHOD_CARD_DRAFT = "method_card_draft"
METHOD_CARD = "method_card"
METHOD_IMPLEMENTATION_MANIFEST = "method_implementation_manifest"
INDICATOR_VALIDATION_REPORT = "indicator_validation_report"
SIGNAL_IMPLEMENTATION_VALIDATION_REPORT = "signal_implementation_validation_report"
SIGNAL_DIAGNOSTIC_REPORT = "signal_diagnostic_report"
MULTIPLE_TESTING_REPORT = "multiple_testing_report"
CXX_KERNEL_MANIFEST = "cxx_kernel_manifest"
EVIDENCE_RETRIEVAL_REPORT = "evidence_retrieval_report"
CITATION_VALIDATION_REPORT = "citation_validation_report"
INDICATOR_METADATA = "indicator_metadata"
STATISTICAL_TEST_REPORT = "statistical_test_report"
FEATURE_MANIFEST = "feature_dataset_manifest"
MODEL_CARD = "model_card"
PREDICTION_ARTIFACT = "prediction_artifact"
DRIFT_REPORT = "drift_report"
EXPERIMENT_PLAN = "experiment_plan"
STRATEGY_CANDIDATE = "strategy_candidate"
BACKTEST_RUN_REF = "backtest_run_ref"
EVALUATION_REPORT = "evaluation_report"
ROBUSTNESS_REPORT = "robustness_report"
RECOMMENDATION_REPORT = "recommendation_report"
RESEARCH_VERDICT = "research_verdict"

SUPPORTED_ARTIFACT_TYPES = frozenset(
    {
        DATASET_MANIFEST,
        DATA_QUALITY_REPORT,
        HYPOTHESIS_CARD,
        KNOWLEDGE_SOURCE_MANIFEST,
        KNOWLEDGE_INGESTION_REPORT,
        KNOWLEDGE_CHUNK_MANIFEST,
        KNOWLEDGE_EMBEDDING_MANIFEST,
        METHOD_CARD_DRAFT,
        METHOD_CARD,
        METHOD_IMPLEMENTATION_MANIFEST,
        INDICATOR_VALIDATION_REPORT,
        SIGNAL_IMPLEMENTATION_VALIDATION_REPORT,
        SIGNAL_DIAGNOSTIC_REPORT,
        MULTIPLE_TESTING_REPORT,
        CXX_KERNEL_MANIFEST,
        EVIDENCE_RETRIEVAL_REPORT,
        CITATION_VALIDATION_REPORT,
        INDICATOR_METADATA,
        STATISTICAL_TEST_REPORT,
        FEATURE_MANIFEST,
        MODEL_CARD,
        PREDICTION_ARTIFACT,
        DRIFT_REPORT,
        EXPERIMENT_PLAN,
        STRATEGY_CANDIDATE,
        BACKTEST_RUN_REF,
        EVALUATION_REPORT,
        ROBUSTNESS_REPORT,
        RECOMMENDATION_REPORT,
        RESEARCH_VERDICT,
    }
)

OWNER_BY_ARTIFACT_TYPE = {
    DATASET_MANIFEST: DATA_AGENT_OWNER,
    DATA_QUALITY_REPORT: DATA_AGENT_OWNER,
    HYPOTHESIS_CARD: HYPOTHESIS_AGENT_OWNER,
    KNOWLEDGE_SOURCE_MANIFEST: QUANTITATIVE_METHODS_OWNER,
    KNOWLEDGE_INGESTION_REPORT: QUANTITATIVE_METHODS_OWNER,
    KNOWLEDGE_CHUNK_MANIFEST: QUANTITATIVE_METHODS_OWNER,
    KNOWLEDGE_EMBEDDING_MANIFEST: QUANTITATIVE_METHODS_OWNER,
    METHOD_CARD_DRAFT: QUANTITATIVE_METHODS_OWNER,
    METHOD_CARD: QUANTITATIVE_METHODS_OWNER,
    METHOD_IMPLEMENTATION_MANIFEST: QUANTITATIVE_METHODS_OWNER,
    INDICATOR_VALIDATION_REPORT: QUANTITATIVE_METHODS_OWNER,
    SIGNAL_IMPLEMENTATION_VALIDATION_REPORT: QUANTITATIVE_METHODS_OWNER,
    SIGNAL_DIAGNOSTIC_REPORT: QUANTITATIVE_METHODS_OWNER,
    MULTIPLE_TESTING_REPORT: QUANTITATIVE_METHODS_OWNER,
    CXX_KERNEL_MANIFEST: QUANTITATIVE_METHODS_OWNER,
    EVIDENCE_RETRIEVAL_REPORT: QUANTITATIVE_METHODS_OWNER,
    CITATION_VALIDATION_REPORT: QUANTITATIVE_METHODS_OWNER,
    INDICATOR_METADATA: MATH_CODER_OWNER,
    STATISTICAL_TEST_REPORT: MATH_CODER_OWNER,
    FEATURE_MANIFEST: ML_AGENT_OWNER,
    MODEL_CARD: ML_AGENT_OWNER,
    PREDICTION_ARTIFACT: ML_AGENT_OWNER,
    DRIFT_REPORT: ML_AGENT_OWNER,
    EXPERIMENT_PLAN: QUANT_RESEARCH_SUPERVISOR_OWNER,
    STRATEGY_CANDIDATE: QUANT_RESEARCH_SUPERVISOR_OWNER,
    BACKTEST_RUN_REF: QUANT_RESEARCH_SUPERVISOR_OWNER,
    EVALUATION_REPORT: EVALUATION_AGENT_OWNER,
    ROBUSTNESS_REPORT: ADVERSARIAL_AGENT_OWNER,
    RECOMMENDATION_REPORT: QUANT_RESEARCH_SUPERVISOR_OWNER,
    RESEARCH_VERDICT: QUANT_RESEARCH_SUPERVISOR_OWNER,
}


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
            source=str(payload["source"]) if payload.get("source") is not None else None,
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
    optional_artifacts: tuple[str, ...] = (FEATURE_MANIFEST, MODEL_CARD, PREDICTION_ARTIFACT, DRIFT_REPORT)

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
            data_requirement=DataRequirement.from_dict(_mapping(payload.get("data_requirement"))),
            required_artifacts=tuple(str(item) for item in _sequence(payload.get("required_artifacts")))
            or BoundedResearchRequest.required_artifacts,
            optional_artifacts=tuple(str(item) for item in _sequence(payload.get("optional_artifacts")))
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
        provenance_refs: Provenance references back to envelopes, graph state, or runs.
        warnings: Structured non-fatal warnings.
        blockers: Structured blockers.
        side_effect: Optional side-effect class from the producing tool envelope.
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
    side_effect: SideEffect | None = None

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
            "side_effect": self.side_effect.value if self.side_effect is not None else None,
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
        side_effect = payload.get("side_effect")
        return cls(
            handoff_id=str(payload.get("handoff_id") or ""),
            agent_owner=str(payload.get("agent_owner") or ""),
            artifact_type=str(payload.get("artifact_type") or ""),
            artifact_path=str(payload["artifact_path"]) if payload.get("artifact_path") is not None else None,
            payload=_mapping(payload.get("payload")),
            source_request=_mapping(payload.get("source_request")),
            provenance_refs=_mapping(payload.get("provenance_refs")),
            warnings=tuple(ResearchIssue.from_dict(item) for item in _mapping_sequence(payload.get("warnings"))),
            blockers=tuple(ResearchIssue.from_dict(item) for item in _mapping_sequence(payload.get("blockers"))),
            side_effect=SideEffect(str(side_effect)) if side_effect is not None else None,
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
    """Supervisor-owned plan that names data requirements and candidate strategy IDs.

    The plan is intentionally lightweight: it references normalized data
    requirements and candidate identifiers rather than embedding run outputs. This
    keeps upstream planning artifacts serializable and lets later evaluation steps
    attach concrete backtest references as separate handoffs.
    """

    plan_id: str
    request_id: str
    data_requirements: tuple[DataRequirement, ...]
    strategy_candidates: tuple[str, ...] = ()
    status: str = "draft"

    def to_dict(self) -> dict[str, Any]:
        """Serialize the experiment plan into data requirements and candidate references for handoff."""
        return {
            "plan_id": self.plan_id,
            "request_id": self.request_id,
            "data_requirements": [item.to_dict() for item in self.data_requirements],
            "strategy_candidates": list(self.strategy_candidates),
            "status": self.status,
        }


@dataclass(frozen=True)
class StrategyCandidate:
    """Serializable reference to a strategy idea selected for experimentation.

    A candidate records the strategy family, JSON-compatible parameter payload,
    and optional hypothesis linkage used to trace why it entered a suite. It is a
    planning artifact only; executable strategy construction and validation happen
    later through standard strategy builders and backtest runs.
    """

    candidate_id: str
    family: str
    parameters: Mapping[str, Any] = field(default_factory=dict)
    source_hypothesis_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize candidate identity, family, parameters, and optional hypothesis linkage for planning."""
        return {
            "candidate_id": self.candidate_id,
            "family": self.family,
            "parameters": _jsonable(self.parameters),
            "source_hypothesis_id": self.source_hypothesis_id,
        }


@dataclass(frozen=True)
class BacktestRunRef:
    """Pointer from research planning/evaluation artifacts to a persisted backtest run.

    The reference keeps experiment-level IDs, the concrete runtime `run_id`, and
    the optional artifact directory together so downstream agents can locate
    metrics, trades, and provenance without embedding the full backtest payload in
    every handoff.
    """

    experiment_id: str
    experiment_run_id: str
    run_id: str
    artifact_dir: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize experiment and run identifiers used to locate persisted backtest artifacts later."""
        return {
            "experiment_id": self.experiment_id,
            "experiment_run_id": self.experiment_run_id,
            "run_id": self.run_id,
            "artifact_dir": self.artifact_dir,
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
            raise ValueError(f"{self.artifact_type} must be owned by {OWNER_BY_ARTIFACT_TYPE[self.artifact_type]}")
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


def stable_research_id(prefix: str, payload: Mapping[str, Any]) -> str:
    """Build a deterministic research-domain identifier.

    Args:
        prefix: Stable ID prefix.
        payload: JSON-compatible payload to hash.

    Returns:
        Deterministic identifier with a short SHA-256 digest.
    """
    serialized = json.dumps(_jsonable(payload), sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def artifact_report_ref(artifact_type: str, artifact_id: str, *, path: str | Path | None = None) -> ArtifactReportRef:
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
