"""Expose Postgres implementations of research persistence ports.

The package owns schema management, canonical artifact storage, and typed
projection writers. Importing it does not open a connection; concrete stores
receive or create database resources explicitly.
"""

from .artifact_store import (
    RESEARCH_ARTIFACT_SCHEMA_STATEMENTS,
    PostgresResearchArtifactStore,
)

__all__ = ["RESEARCH_ARTIFACT_SCHEMA_STATEMENTS", "PostgresResearchArtifactStore"]
