"""Canonical artifact-reference values shared across research contexts.

References expose only stable type, identifier, URI, and bounded metadata needed
for handoffs. They deliberately exclude complete artifact payloads and
transport-specific response envelopes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from ..identity import jsonable


SCHEMA_VERSION = "1"

DATA_DOMAIN_OWNER = "Data"
KNOWLEDGE_METHODOLOGY_DOMAIN_OWNER = "Knowledge/Methodology"
EXPERIMENTS_DOMAIN_OWNER = "Experiments"
ML_DOMAIN_OWNER = "ML"
REVIEW_DOMAIN_OWNER = "Review"
ORCHESTRATION_DOMAIN_OWNER = "Orchestration"

SUPPORTED_DOMAIN_OWNERS = frozenset(
    {
        DATA_DOMAIN_OWNER,
        KNOWLEDGE_METHODOLOGY_DOMAIN_OWNER,
        EXPERIMENTS_DOMAIN_OWNER,
        ML_DOMAIN_OWNER,
        REVIEW_DOMAIN_OWNER,
        ORCHESTRATION_DOMAIN_OWNER,
    }
)


@dataclass(frozen=True)
class ArtifactReference:
    """JSON-safe pointer to a canonical or bounded export artifact."""

    artifact_type: str
    path: str | Path | None = None
    uri: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize this reference without transport-specific metadata."""
        return {
            "artifact_type": self.artifact_type,
            "path": str(self.path) if self.path is not None else None,
            "uri": self.uri,
            "metadata": jsonable(self.metadata),
        }
