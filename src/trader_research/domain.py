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
METHOD_PACKAGE_MANIFEST = "method_package_manifest"
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
STRATEGY_IMPLEMENTATION = "strategy_implementation"
STRATEGY_CANDIDATE_VALIDATION_REPORT = "strategy_candidate_validation_report"
RISK_MANAGER_CANDIDATE = "risk_manager_candidate"
RISK_MANAGER_IMPLEMENTATION = "risk_manager_implementation"
RISK_MANAGER_CANDIDATE_VALIDATION_REPORT = "risk_manager_candidate_validation_report"
STRATEGY_RISK_STACK = "strategy_risk_stack"
STRATEGY_RISK_STACK_VALIDATION_REPORT = "strategy_risk_stack_validation_report"
BACKTEST_RUN_REF = "backtest_run_ref"
PORTFOLIO_BACKTEST_RUN_REF = "portfolio_backtest_run_ref"
COMPARISON_REPORT = "comparison_report"
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
        METHOD_PACKAGE_MANIFEST,
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
        STRATEGY_IMPLEMENTATION,
        STRATEGY_CANDIDATE_VALIDATION_REPORT,
        RISK_MANAGER_CANDIDATE,
        RISK_MANAGER_IMPLEMENTATION,
        RISK_MANAGER_CANDIDATE_VALIDATION_REPORT,
        STRATEGY_RISK_STACK,
        STRATEGY_RISK_STACK_VALIDATION_REPORT,
        BACKTEST_RUN_REF,
        PORTFOLIO_BACKTEST_RUN_REF,
        COMPARISON_REPORT,
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
    METHOD_PACKAGE_MANIFEST: QUANTITATIVE_METHODS_OWNER,
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
    STRATEGY_IMPLEMENTATION: QUANT_RESEARCH_SUPERVISOR_OWNER,
    STRATEGY_CANDIDATE_VALIDATION_REPORT: QUANT_RESEARCH_SUPERVISOR_OWNER,
    RISK_MANAGER_CANDIDATE: QUANT_RESEARCH_SUPERVISOR_OWNER,
    RISK_MANAGER_IMPLEMENTATION: QUANT_RESEARCH_SUPERVISOR_OWNER,
    RISK_MANAGER_CANDIDATE_VALIDATION_REPORT: QUANT_RESEARCH_SUPERVISOR_OWNER,
    STRATEGY_RISK_STACK: QUANT_RESEARCH_SUPERVISOR_OWNER,
    STRATEGY_RISK_STACK_VALIDATION_REPORT: QUANT_RESEARCH_SUPERVISOR_OWNER,
    BACKTEST_RUN_REF: QUANT_RESEARCH_SUPERVISOR_OWNER,
    PORTFOLIO_BACKTEST_RUN_REF: QUANT_RESEARCH_SUPERVISOR_OWNER,
    COMPARISON_REPORT: QUANT_RESEARCH_SUPERVISOR_OWNER,
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
class StrategyCandidateArtifactLink:
    """Declarative artifact reference embedded in a strategy candidate manifest.

    The reference is intentionally lighter than `ArtifactReportRef` because task
    25 must be able to describe future `method_package_manifest.json` inputs
    before task 23N adds validated package artifacts to the typed report registry.

    Attributes:
        artifact_id: Stable artifact identifier.
        artifact_type: Artifact kind, such as `method_package_manifest`.
        role: Template role fulfilled by this artifact.
        path: Optional local artifact path.
        uri: Optional URI-addressable artifact location.
        agent_owner: Optional owning agent recorded by the producer.
        status: Optional producer status, such as `validated`.
        metadata: Optional JSON-compatible provenance.
    """

    artifact_id: str
    artifact_type: str
    role: str
    path: str | None = None
    uri: str | None = None
    agent_owner: str | None = None
    status: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate required artifact identity fields."""
        if not self.artifact_id.strip():
            raise ValueError("strategy candidate artifact_id is required")
        if not self.artifact_type.strip():
            raise ValueError("strategy candidate artifact_type is required")
        if not self.role.strip():
            raise ValueError("strategy candidate artifact role is required")

    def to_dict(self) -> dict[str, Any]:
        """Serialize the artifact link into a JSON-safe manifest reference."""
        payload: dict[str, Any] = {
            "artifact_id": self.artifact_id,
            "artifact_type": self.artifact_type,
            "role": self.role,
            "metadata": _jsonable(self.metadata),
        }
        if self.path is not None:
            payload["path"] = self.path
        if self.uri is not None:
            payload["uri"] = self.uri
        if self.agent_owner is not None:
            payload["agent_owner"] = self.agent_owner
        if self.status is not None:
            payload["status"] = self.status
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "StrategyCandidateArtifactLink":
        """Build an artifact link from JSON-compatible manifest data.

        Args:
            payload: Mapping with artifact identity and optional provenance fields.

        Returns:
            Parsed strategy-candidate artifact link.
        """
        return cls(
            artifact_id=str(payload.get("artifact_id") or ""),
            artifact_type=str(payload.get("artifact_type") or ""),
            role=str(payload.get("role") or ""),
            path=str(payload["path"]) if payload.get("path") is not None else None,
            uri=str(payload["uri"]) if payload.get("uri") is not None else None,
            agent_owner=str(payload["agent_owner"]) if payload.get("agent_owner") is not None else None,
            status=str(payload["status"]) if payload.get("status") is not None else None,
            metadata=_mapping(payload.get("metadata")),
        )


@dataclass(frozen=True)
class StrategyCandidateSizing:
    """Sizing assumption declared by a strategy candidate manifest.

    Attributes:
        model: Sizing model identifier; task 25 catalog templates use fixed quantity.
        target_qty_when_long: Quantity requested when the long/flat template opens long exposure.
        max_position_qty: Optional maximum position quantity assumption.
        metadata: Optional JSON-compatible sizing notes.
    """

    model: str = "fixed_quantity"
    target_qty_when_long: float = 1.0
    max_position_qty: float | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate the sizing model and non-negative quantity assumptions."""
        if not self.model.strip():
            raise ValueError("strategy candidate sizing model is required")
        if self.target_qty_when_long < 0.0:
            raise ValueError("strategy candidate target_qty_when_long must be non-negative")
        if self.max_position_qty is not None and self.max_position_qty < 0.0:
            raise ValueError("strategy candidate max_position_qty must be non-negative")

    def to_dict(self) -> dict[str, Any]:
        """Serialize sizing assumptions for the strategy candidate manifest."""
        payload: dict[str, Any] = {
            "model": self.model,
            "target_qty_when_long": float(self.target_qty_when_long),
            "metadata": _jsonable(self.metadata),
        }
        if self.max_position_qty is not None:
            payload["max_position_qty"] = float(self.max_position_qty)
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "StrategyCandidateSizing":
        """Build sizing assumptions from JSON-compatible manifest data.

        Args:
            payload: Mapping with sizing model and quantity fields.

        Returns:
            Parsed sizing assumptions.
        """
        target_qty = payload.get("target_qty_when_long")
        max_position_qty = payload.get("max_position_qty")
        return cls(
            model=str(payload.get("model") or "fixed_quantity"),
            target_qty_when_long=float(target_qty) if target_qty is not None else 1.0,
            max_position_qty=float(max_position_qty) if max_position_qty is not None else None,
            metadata=_mapping(payload.get("metadata")),
        )


@dataclass(frozen=True)
class StrategyCandidateRiskAssumption:
    """Named risk or execution assumption recorded on a strategy candidate.

    Attributes:
        name: Stable assumption name.
        value: JSON-compatible assumption value.
        description: Optional human-readable context.
    """

    name: str
    value: Any
    description: str | None = None

    def __post_init__(self) -> None:
        """Validate that the assumption has a stable name."""
        if not self.name.strip():
            raise ValueError("strategy candidate risk assumption name is required")

    def to_dict(self) -> dict[str, Any]:
        """Serialize a risk assumption into the candidate manifest."""
        payload = {"name": self.name, "value": _jsonable(self.value)}
        if self.description is not None:
            payload["description"] = self.description
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "StrategyCandidateRiskAssumption":
        """Build a risk assumption from JSON-compatible manifest data.

        Args:
            payload: Mapping with assumption name, value, and optional description.

        Returns:
            Parsed risk assumption.
        """
        return cls(
            name=str(payload.get("name") or ""),
            value=_jsonable(payload.get("value")),
            description=str(payload["description"]) if payload.get("description") is not None else None,
        )


@dataclass(frozen=True)
class StrategyCandidateSourceRef:
    """Source-backed Python strategy implementation attached to a candidate.

    Attributes:
        artifact_id: Stable implementation identifier, usually the candidate ID.
        path: Local Python source path.
        source_hash: SHA-256 of the source file.
        class_name: Concrete class expected to implement `trader.strategies.Strategy`.
        factory_name: Module-level factory used to instantiate the strategy.
        runtime_contract: Runtime interface the implementation must satisfy.
        artifact_type: Strategy implementation artifact kind.
        metadata: Optional JSON-compatible provenance.
    """

    artifact_id: str
    path: str
    source_hash: str
    class_name: str
    factory_name: str = "build_strategy"
    runtime_contract: str = "trader.strategies.Strategy"
    artifact_type: str = STRATEGY_IMPLEMENTATION
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate required source implementation identity fields."""
        if not self.artifact_id.strip():
            raise ValueError("strategy source artifact_id is required")
        if self.artifact_type != STRATEGY_IMPLEMENTATION:
            raise ValueError(f"strategy source artifact_type must be {STRATEGY_IMPLEMENTATION}")
        if not self.path.strip():
            raise ValueError("strategy source path is required")
        if not self.source_hash.strip():
            raise ValueError("strategy source_hash is required")
        if not self.class_name.strip():
            raise ValueError("strategy source class_name is required")
        if not self.factory_name.strip():
            raise ValueError("strategy source factory_name is required")
        if self.runtime_contract != "trader.strategies.Strategy":
            raise ValueError("strategy source runtime_contract must be trader.strategies.Strategy")

    def to_dict(self) -> dict[str, Any]:
        """Serialize the strategy implementation reference for candidate manifests."""
        return {
            "artifact_id": self.artifact_id,
            "artifact_type": self.artifact_type,
            "path": self.path,
            "source_hash": self.source_hash,
            "class_name": self.class_name,
            "factory_name": self.factory_name,
            "runtime_contract": self.runtime_contract,
            "metadata": _jsonable(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "StrategyCandidateSourceRef":
        """Build a strategy implementation reference from manifest data.

        Args:
            payload: Mapping with source path, hash, factory, and class metadata.

        Returns:
            Parsed strategy source reference.
        """
        return cls(
            artifact_id=str(payload.get("artifact_id") or ""),
            artifact_type=str(payload.get("artifact_type") or STRATEGY_IMPLEMENTATION),
            path=str(payload.get("path") or ""),
            source_hash=str(payload.get("source_hash") or ""),
            class_name=str(payload.get("class_name") or ""),
            factory_name=str(payload.get("factory_name") or "build_strategy"),
            runtime_contract=str(payload.get("runtime_contract") or "trader.strategies.Strategy"),
            metadata=_mapping(payload.get("metadata")),
        )


@dataclass(frozen=True)
class StrategyCandidateManifest:
    """Rich strategy-candidate artifact prepared for validation and backtesting.

    This manifest is declarative. It records template selection, method and
    signal artifact links, an importable strategy source file, parameterization,
    semantics, sizing, and risk assumptions, but it does not bind the strategy
    to a market-data universe.

    Attributes:
        candidate_id: Stable strategy candidate identifier.
        template_family: Maintained strategy template family.
        method_package_refs: Declarative method package references.
        signal_refs: Declarative signal implementation or validation references.
        strategy_source: Importable Python strategy implementation source.
        parameters: JSON-compatible template parameter values.
        entry_semantics: Declarative entry policy payload.
        exit_semantics: Declarative exit policy payload.
        sizing: Sizing assumptions for the maintained strategy template.
        risk_assumptions: Named risk and execution assumptions.
        execution_assumptions: JSON-compatible execution boundary assumptions.
        warnings: Structured non-fatal manifest issues.
        blockers: Structured blocking manifest issues.
    """

    candidate_id: str
    template_family: str
    method_package_refs: tuple[StrategyCandidateArtifactLink, ...] = field(default_factory=tuple)
    signal_refs: tuple[StrategyCandidateArtifactLink, ...] = field(default_factory=tuple)
    strategy_source: StrategyCandidateSourceRef | None = None
    parameters: Mapping[str, Any] = field(default_factory=dict)
    entry_semantics: Mapping[str, Any] = field(default_factory=dict)
    exit_semantics: Mapping[str, Any] = field(default_factory=dict)
    sizing: StrategyCandidateSizing = field(default_factory=StrategyCandidateSizing)
    risk_assumptions: tuple[StrategyCandidateRiskAssumption, ...] = field(default_factory=tuple)
    execution_assumptions: Mapping[str, Any] = field(default_factory=dict)
    warnings: tuple[ResearchIssue, ...] = field(default_factory=tuple)
    blockers: tuple[ResearchIssue, ...] = field(default_factory=tuple)
    artifact_type: str = STRATEGY_CANDIDATE

    def __post_init__(self) -> None:
        """Validate candidate identity, artifact type, and template family."""
        if not self.candidate_id.strip():
            raise ValueError("strategy candidate manifest candidate_id is required")
        if not self.template_family.strip():
            raise ValueError("strategy candidate manifest template_family is required")
        if self.artifact_type != STRATEGY_CANDIDATE:
            raise ValueError(f"strategy candidate manifest artifact_type must be {STRATEGY_CANDIDATE}")

    def to_dict(self) -> dict[str, Any]:
        """Serialize the strategy candidate manifest into the stable artifact payload."""
        return {
            "candidate_id": self.candidate_id,
            "artifact_type": self.artifact_type,
            "template_family": self.template_family,
            "method_package_refs": [item.to_dict() for item in self.method_package_refs],
            "signal_refs": [item.to_dict() for item in self.signal_refs],
            "strategy_source": self.strategy_source.to_dict() if self.strategy_source is not None else None,
            "parameters": _jsonable(self.parameters),
            "entry_semantics": _jsonable(self.entry_semantics),
            "exit_semantics": _jsonable(self.exit_semantics),
            "sizing": self.sizing.to_dict(),
            "risk_assumptions": [item.to_dict() for item in self.risk_assumptions],
            "execution_assumptions": _jsonable(self.execution_assumptions),
            "warnings": [warning.to_dict() for warning in self.warnings],
            "blockers": [blocker.to_dict() for blocker in self.blockers],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "StrategyCandidateManifest":
        """Build a strategy candidate manifest from JSON-compatible data.

        Args:
            payload: Mapping with candidate identity, template family, artifact
                references, semantics, sizing, risk assumptions, and issues.

        Returns:
            Parsed strategy candidate manifest.
        """
        return cls(
            candidate_id=str(payload.get("candidate_id") or ""),
            artifact_type=str(payload.get("artifact_type") or STRATEGY_CANDIDATE),
            template_family=str(payload.get("template_family") or ""),
            method_package_refs=tuple(
                StrategyCandidateArtifactLink.from_dict(item)
                for item in _mapping_sequence(payload.get("method_package_refs"))
            ),
            signal_refs=tuple(
                StrategyCandidateArtifactLink.from_dict(item) for item in _mapping_sequence(payload.get("signal_refs"))
            ),
            strategy_source=(
                StrategyCandidateSourceRef.from_dict(_mapping(payload.get("strategy_source")))
                if payload.get("strategy_source") is not None
                else None
            ),
            parameters=_mapping(payload.get("parameters")),
            entry_semantics=_mapping(payload.get("entry_semantics")),
            exit_semantics=_mapping(payload.get("exit_semantics")),
            sizing=StrategyCandidateSizing.from_dict(_mapping(payload.get("sizing"))),
            risk_assumptions=tuple(
                StrategyCandidateRiskAssumption.from_dict(item)
                for item in _mapping_sequence(payload.get("risk_assumptions"))
            ),
            execution_assumptions=_mapping(payload.get("execution_assumptions")),
            warnings=tuple(ResearchIssue.from_dict(item) for item in _mapping_sequence(payload.get("warnings"))),
            blockers=tuple(ResearchIssue.from_dict(item) for item in _mapping_sequence(payload.get("blockers"))),
        )


@dataclass(frozen=True)
class RiskManagerCandidateSourceRef:
    """Source-backed Python risk-manager implementation attached to a candidate.

    Attributes:
        artifact_id: Stable implementation identifier, usually the candidate ID.
        path: Local Python source path.
        source_hash: SHA-256 of the source file.
        class_name: Concrete class expected to implement `trader.risk.RiskManager`.
        factory_name: Module-level factory used to instantiate the risk manager.
        runtime_contract: Runtime interface the implementation must satisfy.
        artifact_type: Risk-manager implementation artifact kind.
        metadata: Optional JSON-compatible provenance.
    """

    artifact_id: str
    path: str
    source_hash: str
    class_name: str
    factory_name: str = "build_risk_manager"
    runtime_contract: str = "trader.risk.RiskManager"
    artifact_type: str = RISK_MANAGER_IMPLEMENTATION
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate required source implementation identity fields."""
        if not self.artifact_id.strip():
            raise ValueError("risk manager source artifact_id is required")
        if self.artifact_type != RISK_MANAGER_IMPLEMENTATION:
            raise ValueError(f"risk manager source artifact_type must be {RISK_MANAGER_IMPLEMENTATION}")
        if not self.path.strip():
            raise ValueError("risk manager source path is required")
        if not self.source_hash.strip():
            raise ValueError("risk manager source_hash is required")
        if not self.class_name.strip():
            raise ValueError("risk manager source class_name is required")
        if not self.factory_name.strip():
            raise ValueError("risk manager source factory_name is required")
        if self.runtime_contract != "trader.risk.RiskManager":
            raise ValueError("risk manager source runtime_contract must be trader.risk.RiskManager")

    def to_dict(self) -> dict[str, Any]:
        """Serialize the risk-manager implementation reference."""
        return {
            "artifact_id": self.artifact_id,
            "artifact_type": self.artifact_type,
            "path": self.path,
            "source_hash": self.source_hash,
            "class_name": self.class_name,
            "factory_name": self.factory_name,
            "runtime_contract": self.runtime_contract,
            "metadata": _jsonable(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RiskManagerCandidateSourceRef":
        """Build a risk-manager implementation reference from manifest data."""
        return cls(
            artifact_id=str(payload.get("artifact_id") or ""),
            artifact_type=str(payload.get("artifact_type") or RISK_MANAGER_IMPLEMENTATION),
            path=str(payload.get("path") or ""),
            source_hash=str(payload.get("source_hash") or ""),
            class_name=str(payload.get("class_name") or ""),
            factory_name=str(payload.get("factory_name") or "build_risk_manager"),
            runtime_contract=str(payload.get("runtime_contract") or "trader.risk.RiskManager"),
            metadata=_mapping(payload.get("metadata")),
        )


@dataclass(frozen=True)
class RiskManagerCandidateManifest:
    """Declarative source-backed risk-manager candidate for portfolio research.

    Risk-manager candidates are data-free: symbols, timeframe, dates, and source
    filters are supplied later by Data Agent dataset manifests and portfolio
    backtest tooling.

    Attributes:
        candidate_id: Stable risk-manager candidate identifier.
        template_family: Maintained risk-manager template family.
        method_package_refs: Optional validated method packages for sourced risk measures.
        risk_manager_source: Importable Python risk-manager source reference.
        parameters: JSON-compatible risk parameter values.
        policy_intent: Declarative policy semantics for later validation/backtests.
        execution_assumptions: JSON-compatible execution boundary assumptions.
        validation_requirements: Deferred checks required before portfolio backtests.
        warnings: Structured non-fatal manifest issues.
        blockers: Structured blocking manifest issues.
        status: Candidate lifecycle state.
    """

    candidate_id: str
    template_family: str
    method_package_refs: tuple[StrategyCandidateArtifactLink, ...] = field(default_factory=tuple)
    risk_manager_source: RiskManagerCandidateSourceRef | None = None
    parameters: Mapping[str, Any] = field(default_factory=dict)
    policy_intent: Mapping[str, Any] = field(default_factory=dict)
    execution_assumptions: Mapping[str, Any] = field(default_factory=dict)
    validation_requirements: Mapping[str, Any] = field(default_factory=dict)
    warnings: tuple[ResearchIssue, ...] = field(default_factory=tuple)
    blockers: tuple[ResearchIssue, ...] = field(default_factory=tuple)
    status: str = "candidate"
    artifact_type: str = RISK_MANAGER_CANDIDATE
    schema_version: str = "1"

    def __post_init__(self) -> None:
        """Validate candidate identity, artifact type, and template family."""
        if not self.candidate_id.strip():
            raise ValueError("risk manager candidate manifest candidate_id is required")
        if not self.template_family.strip():
            raise ValueError("risk manager candidate manifest template_family is required")
        if self.artifact_type != RISK_MANAGER_CANDIDATE:
            raise ValueError(f"risk manager candidate manifest artifact_type must be {RISK_MANAGER_CANDIDATE}")
        if not self.status.strip():
            raise ValueError("risk manager candidate manifest status is required")

    def to_dict(self) -> dict[str, Any]:
        """Serialize the risk-manager candidate manifest."""
        return {
            "candidate_id": self.candidate_id,
            "artifact_type": self.artifact_type,
            "schema_version": self.schema_version,
            "template_family": self.template_family,
            "method_package_refs": [item.to_dict() for item in self.method_package_refs],
            "risk_manager_source": (
                self.risk_manager_source.to_dict() if self.risk_manager_source is not None else None
            ),
            "parameters": _jsonable(self.parameters),
            "policy_intent": _jsonable(self.policy_intent),
            "execution_assumptions": _jsonable(self.execution_assumptions),
            "validation_requirements": _jsonable(self.validation_requirements),
            "warnings": [warning.to_dict() for warning in self.warnings],
            "blockers": [blocker.to_dict() for blocker in self.blockers],
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RiskManagerCandidateManifest":
        """Build a risk-manager candidate manifest from JSON-compatible data."""
        return cls(
            candidate_id=str(payload.get("candidate_id") or ""),
            artifact_type=str(payload.get("artifact_type") or RISK_MANAGER_CANDIDATE),
            schema_version=str(payload.get("schema_version") or "1"),
            template_family=str(payload.get("template_family") or ""),
            method_package_refs=tuple(
                StrategyCandidateArtifactLink.from_dict(item)
                for item in _mapping_sequence(payload.get("method_package_refs"))
            ),
            risk_manager_source=(
                RiskManagerCandidateSourceRef.from_dict(_mapping(payload.get("risk_manager_source")))
                if payload.get("risk_manager_source") is not None
                else None
            ),
            parameters=_mapping(payload.get("parameters")),
            policy_intent=_mapping(payload.get("policy_intent")),
            execution_assumptions=_mapping(payload.get("execution_assumptions")),
            validation_requirements=_mapping(payload.get("validation_requirements")),
            warnings=tuple(ResearchIssue.from_dict(item) for item in _mapping_sequence(payload.get("warnings"))),
            blockers=tuple(ResearchIssue.from_dict(item) for item in _mapping_sequence(payload.get("blockers"))),
            status=str(payload.get("status") or "candidate"),
        )


@dataclass(frozen=True)
class StrategyRiskStackManifest:
    """Declarative composition of one strategy candidate and ordered risk managers.

    Attributes:
        stack_id: Stable strategy/risk stack identifier.
        strategy_candidate_ref: Reference to the source-backed strategy candidate.
        risk_manager_refs: Ordered references to risk-manager candidates.
        strategy_validation_report_ref: Optional passed strategy validation report ref.
        execution_assumptions: JSON-compatible no-live-trading assumptions.
        warnings: Structured non-fatal stack issues.
        blockers: Structured blocking stack issues.
        status: Stack lifecycle state.
        artifact_type: Stable artifact kind.
        schema_version: Serialized schema version.
    """

    stack_id: str
    strategy_candidate_ref: StrategyCandidateArtifactLink
    risk_manager_refs: tuple[StrategyCandidateArtifactLink, ...]
    strategy_validation_report_ref: StrategyCandidateArtifactLink | None = None
    execution_assumptions: Mapping[str, Any] = field(default_factory=dict)
    warnings: tuple[ResearchIssue, ...] = field(default_factory=tuple)
    blockers: tuple[ResearchIssue, ...] = field(default_factory=tuple)
    status: str = "candidate"
    artifact_type: str = STRATEGY_RISK_STACK
    schema_version: str = "1"

    def __post_init__(self) -> None:
        """Validate stack identity, artifact type, and risk-manager coverage."""
        if not self.stack_id.strip():
            raise ValueError("strategy risk stack stack_id is required")
        if self.artifact_type != STRATEGY_RISK_STACK:
            raise ValueError(f"strategy risk stack artifact_type must be {STRATEGY_RISK_STACK}")
        if not self.risk_manager_refs:
            raise ValueError("strategy risk stack requires at least one risk manager ref")

    def to_dict(self) -> dict[str, Any]:
        """Serialize a strategy/risk stack manifest."""
        return {
            "stack_id": self.stack_id,
            "artifact_type": self.artifact_type,
            "schema_version": self.schema_version,
            "strategy_candidate_ref": self.strategy_candidate_ref.to_dict(),
            "strategy_validation_report_ref": (
                self.strategy_validation_report_ref.to_dict()
                if self.strategy_validation_report_ref is not None
                else None
            ),
            "risk_manager_refs": [item.to_dict() for item in self.risk_manager_refs],
            "execution_assumptions": _jsonable(self.execution_assumptions),
            "warnings": [warning.to_dict() for warning in self.warnings],
            "blockers": [blocker.to_dict() for blocker in self.blockers],
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "StrategyRiskStackManifest":
        """Build a strategy/risk stack manifest from JSON-compatible data."""
        return cls(
            stack_id=str(payload.get("stack_id") or ""),
            artifact_type=str(payload.get("artifact_type") or STRATEGY_RISK_STACK),
            schema_version=str(payload.get("schema_version") or "1"),
            strategy_candidate_ref=StrategyCandidateArtifactLink.from_dict(
                _mapping(payload.get("strategy_candidate_ref"))
            ),
            strategy_validation_report_ref=(
                StrategyCandidateArtifactLink.from_dict(_mapping(payload.get("strategy_validation_report_ref")))
                if payload.get("strategy_validation_report_ref") is not None
                else None
            ),
            risk_manager_refs=tuple(
                StrategyCandidateArtifactLink.from_dict(item)
                for item in _mapping_sequence(payload.get("risk_manager_refs"))
            ),
            execution_assumptions=_mapping(payload.get("execution_assumptions")),
            warnings=tuple(ResearchIssue.from_dict(item) for item in _mapping_sequence(payload.get("warnings"))),
            blockers=tuple(ResearchIssue.from_dict(item) for item in _mapping_sequence(payload.get("blockers"))),
            status=str(payload.get("status") or "candidate"),
        )


@dataclass(frozen=True)
class StrategyRiskStackValidationReport:
    """Validation report contract for a strategy plus ordered risk managers.

    Attributes:
        validation_id: Stable strategy/risk stack validation identifier.
        stack_id: Strategy/risk stack validated by this report.
        status: Validation result state, such as `passed` or `blocked`.
        checks: JSON-compatible check results.
        fixture_summary: Deterministic smoke-fixture summary.
        strategy_validation_report_ref: Optional strategy validation report ref.
        risk_manager_validation_refs: Ordered risk-manager validation refs.
        warnings: Structured non-fatal validation issues.
        blockers: Structured blocking validation issues.
        artifact_type: Stable artifact kind.
        schema_version: Serialized schema version.
    """

    validation_id: str
    stack_id: str
    status: str
    checks: Mapping[str, Any] = field(default_factory=dict)
    fixture_summary: Mapping[str, Any] = field(default_factory=dict)
    strategy_validation_report_ref: StrategyCandidateArtifactLink | None = None
    risk_manager_validation_refs: tuple[StrategyCandidateArtifactLink, ...] = field(default_factory=tuple)
    warnings: tuple[ResearchIssue, ...] = field(default_factory=tuple)
    blockers: tuple[ResearchIssue, ...] = field(default_factory=tuple)
    artifact_type: str = STRATEGY_RISK_STACK_VALIDATION_REPORT
    schema_version: str = "1"

    def __post_init__(self) -> None:
        """Validate report identity and artifact type."""
        if not self.validation_id.strip():
            raise ValueError("strategy risk stack validation_id is required")
        if not self.stack_id.strip():
            raise ValueError("strategy risk stack validation stack_id is required")
        if self.artifact_type != STRATEGY_RISK_STACK_VALIDATION_REPORT:
            raise ValueError(
                f"strategy risk stack validation artifact_type must be {STRATEGY_RISK_STACK_VALIDATION_REPORT}"
            )

    def to_dict(self) -> dict[str, Any]:
        """Serialize a strategy/risk stack validation report."""
        return {
            "validation_id": self.validation_id,
            "artifact_type": self.artifact_type,
            "schema_version": self.schema_version,
            "stack_id": self.stack_id,
            "status": self.status,
            "checks": _jsonable(self.checks),
            "fixture_summary": _jsonable(self.fixture_summary),
            "strategy_validation_report_ref": (
                self.strategy_validation_report_ref.to_dict()
                if self.strategy_validation_report_ref is not None
                else None
            ),
            "risk_manager_validation_refs": [item.to_dict() for item in self.risk_manager_validation_refs],
            "warnings": [warning.to_dict() for warning in self.warnings],
            "blockers": [blocker.to_dict() for blocker in self.blockers],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "StrategyRiskStackValidationReport":
        """Build a strategy/risk stack validation report from JSON-compatible data."""
        return cls(
            validation_id=str(payload.get("validation_id") or ""),
            artifact_type=str(payload.get("artifact_type") or STRATEGY_RISK_STACK_VALIDATION_REPORT),
            schema_version=str(payload.get("schema_version") or "1"),
            stack_id=str(payload.get("stack_id") or ""),
            status=str(payload.get("status") or ""),
            checks=_mapping(payload.get("checks")),
            fixture_summary=_mapping(payload.get("fixture_summary")),
            strategy_validation_report_ref=(
                StrategyCandidateArtifactLink.from_dict(_mapping(payload.get("strategy_validation_report_ref")))
                if payload.get("strategy_validation_report_ref") is not None
                else None
            ),
            risk_manager_validation_refs=tuple(
                StrategyCandidateArtifactLink.from_dict(item)
                for item in _mapping_sequence(payload.get("risk_manager_validation_refs"))
            ),
            warnings=tuple(ResearchIssue.from_dict(item) for item in _mapping_sequence(payload.get("warnings"))),
            blockers=tuple(ResearchIssue.from_dict(item) for item in _mapping_sequence(payload.get("blockers"))),
        )


@dataclass(frozen=True)
class BacktestRunRef:
    """Pointer from research planning/evaluation artifacts to a persisted backtest run.

    The reference keeps experiment-level IDs, the concrete runtime `run_id`, and
    the artifact directory together with the Data Agent scope that bounded the
    run so downstream agents can locate metrics, trades, and provenance without
    embedding the full backtest payload in every handoff.
    """

    experiment_id: str
    experiment_run_id: str
    run_id: str
    artifact_dir: str | None = None
    artifact_type: str = BACKTEST_RUN_REF
    candidate_id: str | None = None
    validation_id: str | None = None
    strategy_risk_stack_id: str | None = None
    strategy_risk_stack_validation_id: str | None = None
    dataset_id: str | None = None
    data_scope: Mapping[str, Any] = field(default_factory=dict)
    status: str | None = None
    summary: Mapping[str, Any] = field(default_factory=dict)
    symbol_metrics: Mapping[str, Any] = field(default_factory=dict)
    exposure_summary: Mapping[str, Any] = field(default_factory=dict)
    risk_measure_summary: Mapping[str, Any] = field(default_factory=dict)
    artifact_paths: Mapping[str, Any] = field(default_factory=dict)
    warnings: tuple[ResearchIssue, ...] = ()
    blockers: tuple[ResearchIssue, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """Serialize experiment and run identifiers used to locate persisted backtest artifacts later."""
        return {
            "artifact_type": self.artifact_type,
            "experiment_id": self.experiment_id,
            "experiment_run_id": self.experiment_run_id,
            "run_id": self.run_id,
            "artifact_dir": self.artifact_dir,
            "candidate_id": self.candidate_id,
            "validation_id": self.validation_id,
            "strategy_risk_stack_id": self.strategy_risk_stack_id,
            "strategy_risk_stack_validation_id": self.strategy_risk_stack_validation_id,
            "dataset_id": self.dataset_id,
            "data_scope": dict(self.data_scope),
            "status": self.status,
            "summary": dict(self.summary),
            "symbol_metrics": dict(self.symbol_metrics),
            "exposure_summary": dict(self.exposure_summary),
            "risk_measure_summary": dict(self.risk_measure_summary),
            "artifact_paths": dict(self.artifact_paths),
            "warnings": [issue.to_dict() for issue in self.warnings],
            "blockers": [issue.to_dict() for issue in self.blockers],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "BacktestRunRef":
        """Parse a persisted backtest run reference."""
        return cls(
            experiment_id=str(payload.get("experiment_id") or ""),
            experiment_run_id=str(payload.get("experiment_run_id") or ""),
            run_id=str(payload.get("run_id") or ""),
            artifact_dir=str(payload["artifact_dir"]) if payload.get("artifact_dir") is not None else None,
            artifact_type=str(payload.get("artifact_type") or BACKTEST_RUN_REF),
            candidate_id=str(payload["candidate_id"]) if payload.get("candidate_id") is not None else None,
            validation_id=str(payload["validation_id"]) if payload.get("validation_id") is not None else None,
            strategy_risk_stack_id=(
                str(payload["strategy_risk_stack_id"]) if payload.get("strategy_risk_stack_id") is not None else None
            ),
            strategy_risk_stack_validation_id=(
                str(payload["strategy_risk_stack_validation_id"])
                if payload.get("strategy_risk_stack_validation_id") is not None
                else None
            ),
            dataset_id=str(payload["dataset_id"]) if payload.get("dataset_id") is not None else None,
            data_scope=_mapping(payload.get("data_scope")),
            status=str(payload["status"]) if payload.get("status") is not None else None,
            summary=_mapping(payload.get("summary")),
            symbol_metrics=_mapping(payload.get("symbol_metrics")),
            exposure_summary=_mapping(payload.get("exposure_summary")),
            risk_measure_summary=_mapping(payload.get("risk_measure_summary")),
            artifact_paths=_mapping(payload.get("artifact_paths")),
            warnings=tuple(ResearchIssue.from_dict(item) for item in _mapping_sequence(payload.get("warnings"))),
            blockers=tuple(ResearchIssue.from_dict(item) for item in _mapping_sequence(payload.get("blockers"))),
        )


@dataclass(frozen=True)
class PortfolioBacktestRunRef:
    """Pointer to a future risk-scoped portfolio backtest bundle.

    This schema is intentionally separate from the current baseline `BacktestRunRef`
    so portfolio backtests can require a validated strategy/risk stack while
    retaining the same Data Agent data-scope discipline.

    Attributes:
        run_id: Stable portfolio backtest run identifier.
        strategy_risk_stack_id: Validated strategy/risk stack used by the run.
        strategy_risk_stack_validation_id: Passed stack validation report identifier.
        dataset_id: Data Agent dataset manifest identifier.
        data_scope: Normalized multi-symbol data scope supplied by the manifest.
        artifact_dir: Optional local bundle directory.
        status: Run status.
        summary: Portfolio-level summary metrics.
        symbol_metrics: Per-symbol metrics.
        exposure_summary: Gross/net exposure and concentration summaries.
        risk_measure_summary: VaR/CVaR or supplied risk-measure summaries.
        artifact_paths: Bundle artifact paths.
        warnings: Structured non-fatal run issues.
        blockers: Structured blocking run issues.
        artifact_type: Stable artifact kind.
        schema_version: Serialized schema version.
    """

    run_id: str
    strategy_risk_stack_id: str
    strategy_risk_stack_validation_id: str
    dataset_id: str
    data_scope: Mapping[str, Any]
    artifact_dir: str | None = None
    status: str | None = None
    summary: Mapping[str, Any] = field(default_factory=dict)
    symbol_metrics: Mapping[str, Any] = field(default_factory=dict)
    exposure_summary: Mapping[str, Any] = field(default_factory=dict)
    risk_measure_summary: Mapping[str, Any] = field(default_factory=dict)
    artifact_paths: Mapping[str, Any] = field(default_factory=dict)
    warnings: tuple[ResearchIssue, ...] = ()
    blockers: tuple[ResearchIssue, ...] = ()
    artifact_type: str = PORTFOLIO_BACKTEST_RUN_REF
    schema_version: str = "1"

    def __post_init__(self) -> None:
        """Validate required portfolio run identity and stack references."""
        if not self.run_id.strip():
            raise ValueError("portfolio backtest run_id is required")
        if not self.strategy_risk_stack_id.strip():
            raise ValueError("portfolio backtest strategy_risk_stack_id is required")
        if not self.strategy_risk_stack_validation_id.strip():
            raise ValueError("portfolio backtest strategy_risk_stack_validation_id is required")
        if not self.dataset_id.strip():
            raise ValueError("portfolio backtest dataset_id is required")
        if self.artifact_type != PORTFOLIO_BACKTEST_RUN_REF:
            raise ValueError(f"portfolio backtest artifact_type must be {PORTFOLIO_BACKTEST_RUN_REF}")

    def to_dict(self) -> dict[str, Any]:
        """Serialize a portfolio backtest run reference."""
        return {
            "artifact_type": self.artifact_type,
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "artifact_dir": self.artifact_dir,
            "strategy_risk_stack_id": self.strategy_risk_stack_id,
            "strategy_risk_stack_validation_id": self.strategy_risk_stack_validation_id,
            "dataset_id": self.dataset_id,
            "data_scope": _jsonable(self.data_scope),
            "status": self.status,
            "summary": _jsonable(self.summary),
            "symbol_metrics": _jsonable(self.symbol_metrics),
            "exposure_summary": _jsonable(self.exposure_summary),
            "risk_measure_summary": _jsonable(self.risk_measure_summary),
            "artifact_paths": _jsonable(self.artifact_paths),
            "warnings": [issue.to_dict() for issue in self.warnings],
            "blockers": [issue.to_dict() for issue in self.blockers],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "PortfolioBacktestRunRef":
        """Build a portfolio backtest run reference from JSON-compatible data."""
        return cls(
            run_id=str(payload.get("run_id") or ""),
            artifact_type=str(payload.get("artifact_type") or PORTFOLIO_BACKTEST_RUN_REF),
            schema_version=str(payload.get("schema_version") or "1"),
            artifact_dir=str(payload["artifact_dir"]) if payload.get("artifact_dir") is not None else None,
            strategy_risk_stack_id=str(payload.get("strategy_risk_stack_id") or ""),
            strategy_risk_stack_validation_id=str(payload.get("strategy_risk_stack_validation_id") or ""),
            dataset_id=str(payload.get("dataset_id") or ""),
            data_scope=_mapping(payload.get("data_scope")),
            status=str(payload["status"]) if payload.get("status") is not None else None,
            summary=_mapping(payload.get("summary")),
            symbol_metrics=_mapping(payload.get("symbol_metrics")),
            exposure_summary=_mapping(payload.get("exposure_summary")),
            risk_measure_summary=_mapping(payload.get("risk_measure_summary")),
            artifact_paths=_mapping(payload.get("artifact_paths")),
            warnings=tuple(ResearchIssue.from_dict(item) for item in _mapping_sequence(payload.get("warnings"))),
            blockers=tuple(ResearchIssue.from_dict(item) for item in _mapping_sequence(payload.get("blockers"))),
        )


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
