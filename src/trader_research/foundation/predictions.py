"""Define neutral ports for prediction deployments and mapper evidence.

Specification and runtime services depend on these protocols to resolve passed
ML artifacts and immutable mapper configurations without importing model
providers or the ML persistence implementation.
"""

from __future__ import annotations

from typing import Any, Mapping, Protocol, Sequence

class PredictionDeploymentReader(Protocol):
    """Resolve one passed immutable raw-inference deployment."""

    def resolve_passed(self, validation_ref: str) -> Mapping[str, Any]:
        """Return normalized deployment evidence after lineage revalidation."""


class PredictionMapperCatalog(Protocol):
    """Validate maintained strategy-owned prediction interpretation."""

    def resolve_configuration(
        self,
        *,
        mapper_id: str,
        consumer_kind: str,
        output_contract: Sequence[Mapping[str, Any]],
        parameters: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        """Return immutable mapper identity/configuration evidence or fail."""

    def build_mapper(self, snapshot: Mapping[str, Any]) -> Any:
        """Revalidate one snapshot and construct its runtime mapper."""
