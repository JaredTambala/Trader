"""Public research-ownership and cross-agent handoff contracts."""

from .artifacts import (
    DATA_AGENT_OWNER,
    DATA_QUALITY_REPORT,
    DATASET_MANIFEST,
    DRIFT_REPORT,
    FEATURE_MANIFEST,
    MODEL_CARD,
    OWNER_BY_ARTIFACT_TYPE,
    PREDICTION_ARTIFACT,
    SUPPORTED_ARTIFACT_TYPES,
)
from .handoffs import (
    BoundedResearchRequest,
    DataRequirement,
    ResearchIssue,
    SpecialistArtifactSlot,
    SpecialistHandoff,
)
from .ownership import AgentDefinition, agent_owner_for_tool, get_agent_definition

__all__ = [
    "AgentDefinition",
    "BoundedResearchRequest",
    "DATASET_MANIFEST",
    "DATA_AGENT_OWNER",
    "DATA_QUALITY_REPORT",
    "DRIFT_REPORT",
    "DataRequirement",
    "FEATURE_MANIFEST",
    "MODEL_CARD",
    "OWNER_BY_ARTIFACT_TYPE",
    "PREDICTION_ARTIFACT",
    "ResearchIssue",
    "SpecialistArtifactSlot",
    "SpecialistHandoff",
    "SUPPORTED_ARTIFACT_TYPES",
    "agent_owner_for_tool",
    "get_agent_definition",
]
