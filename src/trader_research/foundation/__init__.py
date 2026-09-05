"""Expose dependency-light primitives shared by all research contexts.

Foundation owns stable identities, result envelopes, artifact references,
persistence ports, and cross-context errors. It must remain independent of Data,
Experiments, Knowledge, ML, Review, transport, and provider implementations.
"""

from .artifacts import (
    DATA_DOMAIN_OWNER,
    EXPERIMENTS_DOMAIN_OWNER,
    KNOWLEDGE_METHODOLOGY_DOMAIN_OWNER,
    ML_DOMAIN_OWNER,
    ORCHESTRATION_DOMAIN_OWNER,
    REVIEW_DOMAIN_OWNER,
    SUPPORTED_DOMAIN_OWNERS,
    ArtifactReference,
    ContextualResearchArtifactStore,
    InMemoryResearchArtifactStore,
    ResearchArtifactNotFound,
    ResearchArtifactRecord,
    ResearchArtifactStore,
    ResearchArtifactStoreError,
    SCHEMA_VERSION,
    UnavailableResearchArtifactStore,
    build_artifact_record,
    load_artifact_ref,
    parse_research_artifact_uri,
    research_artifact_uri,
)
from .errors import ResearchApplicationError, ResearchFailure
from .identity import json_payload_hash, jsonable, source_hash, stable_research_id
from .results import ApplicationResult, error_result, success_result
from .predictions import PredictionDeploymentReader, PredictionMapperCatalog

__all__ = [
    "ApplicationResult",
    "DATA_DOMAIN_OWNER",
    "EXPERIMENTS_DOMAIN_OWNER",
    "KNOWLEDGE_METHODOLOGY_DOMAIN_OWNER",
    "ML_DOMAIN_OWNER",
    "ORCHESTRATION_DOMAIN_OWNER",
    "PredictionDeploymentReader",
    "PredictionMapperCatalog",
    "ArtifactReference",
    "ContextualResearchArtifactStore",
    "InMemoryResearchArtifactStore",
    "ResearchArtifactNotFound",
    "ResearchArtifactRecord",
    "ResearchArtifactStore",
    "ResearchArtifactStoreError",
    "ResearchApplicationError",
    "ResearchFailure",
    "REVIEW_DOMAIN_OWNER",
    "SCHEMA_VERSION",
    "SUPPORTED_DOMAIN_OWNERS",
    "UnavailableResearchArtifactStore",
    "build_artifact_record",
    "error_result",
    "json_payload_hash",
    "jsonable",
    "load_artifact_ref",
    "parse_research_artifact_uri",
    "research_artifact_uri",
    "source_hash",
    "stable_research_id",
    "success_result",
]
