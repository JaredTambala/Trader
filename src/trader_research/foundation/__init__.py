"""Dependency-light primitives shared by research contexts."""

from .artifacts import (
    ArtifactReference,
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

__all__ = [
    "ApplicationResult",
    "ArtifactReference",
    "InMemoryResearchArtifactStore",
    "ResearchArtifactNotFound",
    "ResearchArtifactRecord",
    "ResearchArtifactStore",
    "ResearchArtifactStoreError",
    "ResearchApplicationError",
    "ResearchFailure",
    "SCHEMA_VERSION",
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
