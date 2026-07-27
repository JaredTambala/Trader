"""Closed vocabularies for provider-neutral research orchestration."""

from __future__ import annotations

from enum import Enum

class ResearchObjectiveStatus(str, Enum):
    """Lifecycle states for an operator research objective."""

    DRAFT = "draft"
    APPROVED = "approved"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


class ExperimentProtocolStatus(str, Enum):
    """Lifecycle states for an experiment-design proposal."""

    PROPOSED = "proposed"
    APPROVED = "approved"
    BLOCKED = "blocked"
    SUPERSEDED = "superseded"


class ApprovalStatus(str, Enum):
    """Closed decision states for one material assumption."""

    REQUESTED = "requested"
    APPROVED = "approved"
    REJECTED = "rejected"


class DatasetRole(str, Enum):
    """Role a bounded dataset plays in an experiment protocol."""

    BASELINE = "baseline"
    SELECTION = "selection"
    HOLDOUT = "holdout"
    ROBUSTNESS = "robustness"


class OptimizationDirection(str, Enum):
    """Direction for a declared scalar optimisation objective."""

    MAXIMIZE = "maximize"
    MINIMIZE = "minimize"


class TunableValueType(str, Enum):
    """Supported provider-neutral search-dimension value types."""

    INTEGER = "integer"
    FLOAT = "float"
    CATEGORICAL = "categorical"


class CapabilitySideEffect(str, Enum):
    """Research-safe side-effect classes understood by workflow plans."""

    READ_ONLY = "read_only"
    LOCAL_MUTATING = "local_mutating"
    EXTERNAL_RESEARCH_MUTATING = "external_research_mutating"


class ArtifactCardinality(str, Enum):
    """Allowed cardinalities for a workflow artifact slot."""

    EXACTLY_ONE = "exactly_one"
    ZERO_OR_ONE = "zero_or_one"
    ONE_OR_MORE = "one_or_more"


class ArtifactSlotStatus(str, Enum):
    """Resolution states for an artifact slot."""

    EMPTY = "empty"
    RESOLVED = "resolved"
    BLOCKED = "blocked"


class PrerequisiteKind(str, Enum):
    """Kinds of prerequisite a workflow may declare."""

    ARTIFACT = "artifact"
    CAPABILITY = "capability"
    POLICY_GATE = "policy_gate"
    APPROVAL = "approval"


class PrerequisiteStatus(str, Enum):
    """Resolution states for a declared prerequisite."""

    UNRESOLVED = "unresolved"
    SATISFIED = "satisfied"
    BLOCKED = "blocked"


class WorkflowPlanStatus(str, Enum):
    """Pre-execution lifecycle states for a workflow plan."""

    DRAFT = "draft"
    AWAITING_APPROVAL = "awaiting_approval"
    READY = "ready"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


class WorkflowStepStatus(str, Enum):
    """Terminal public outcomes for one workflow-step attempt."""

    SUCCEEDED = "succeeded"
    BLOCKED = "blocked"
    FAILED = "failed"


class RetryDisposition(str, Enum):
    """Whether a failed or blocked step may be retried unchanged."""

    NOT_APPLICABLE = "not_applicable"
    RETRYABLE = "retryable"
    TERMINAL = "terminal"
