"""Define canonical research artifact values and persistence boundaries.

Artifacts carry immutable identity, bounded-context ownership, producer
provenance, normalized payloads, and optional workflow attribution. Concrete
storage adapters implement the ports without changing those domain contracts.
"""

from .domain import (
    DATA_DOMAIN_OWNER,
    EXPERIMENTS_DOMAIN_OWNER,
    KNOWLEDGE_METHODOLOGY_DOMAIN_OWNER,
    ML_DOMAIN_OWNER,
    ORCHESTRATION_DOMAIN_OWNER,
    REVIEW_DOMAIN_OWNER,
    SUPPORTED_DOMAIN_OWNERS,
    ArtifactReference,
    SCHEMA_VERSION,
)
from .store import (
    ContextualResearchArtifactStore,
    InMemoryResearchArtifactStore,
    ResearchArtifactNotFound,
    ResearchArtifactRecord,
    ResearchArtifactStore,
    ResearchArtifactStoreError,
    UnavailableResearchArtifactStore,
    build_artifact_record,
    load_artifact_ref,
    parse_research_artifact_uri,
    research_artifact_uri,
)

__all__ = [
    "ArtifactReference",
    "ContextualResearchArtifactStore",
    "DATA_DOMAIN_OWNER",
    "EXPERIMENTS_DOMAIN_OWNER",
    "InMemoryResearchArtifactStore",
    "KNOWLEDGE_METHODOLOGY_DOMAIN_OWNER",
    "ML_DOMAIN_OWNER",
    "ORCHESTRATION_DOMAIN_OWNER",
    "REVIEW_DOMAIN_OWNER",
    "ResearchArtifactNotFound",
    "ResearchArtifactRecord",
    "ResearchArtifactStore",
    "ResearchArtifactStoreError",
    "UnavailableResearchArtifactStore",
    "SCHEMA_VERSION",
    "SUPPORTED_DOMAIN_OWNERS",
    "build_artifact_record",
    "load_artifact_ref",
    "parse_research_artifact_uri",
    "research_artifact_uri",
]
