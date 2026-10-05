"""Adapter from Console authoring lineage to research-owned admission evidence."""

from __future__ import annotations

from typing import Literal

from trader_research.experiments.implementations import load_passed_implementation
from trader_research.foundation.artifacts import ResearchArtifactStore

from ..contracts import ImplementationLineage, ImplementationValidationReport


class ResearchArtifactLineageResolver:
    """Resolve exact passed implementation evidence without importing user code."""

    def __init__(self, store: ResearchArtifactStore) -> None:
        """Bind the already-composed research artifact store."""
        self._store = store

    def resolve(
        self,
        lineage: ImplementationLineage,
        *,
        profile_id: str,
        expected_kind: Literal["strategy", "risk_manager"],
    ) -> ImplementationLineage:
        """Re-read and compare version, kind, source digest, and report identity."""
        implementation, report = load_passed_implementation(
            self._store,
            lineage.implementation_validation_id,
            expected_kind=expected_kind,
        )
        if implementation.implementation_version_id != lineage.implementation_version_id:
            raise ValueError("implementation version ID drifted from research admission")
        if implementation.implementation_kind != lineage.implementation_kind:
            raise ValueError("implementation kind drifted from research admission")
        if implementation.source_hash != lineage.source_hash:
            raise ValueError("implementation source hash drifted from research admission")
        if implementation.name != lineage.implementation_name:
            raise ValueError("implementation name drifted from research admission")
        if implementation.version != lineage.implementation_version:
            raise ValueError("implementation version drifted from research admission")
        metadata_profile = str(implementation.metadata.get("profile_id") or "")
        if metadata_profile and metadata_profile != profile_id:
            raise ValueError("implementation profile drifted from selected catalogue profile")
        canonical_report = ImplementationValidationReport.model_validate(
            {
                "validation_id": report["validation_id"],
                "implementation_version_id": report["implementation_version_id"],
                "implementation_kind": report["implementation_kind"],
                "source_hash": report["source_hash"],
                "status": report["status"],
                "valid": report["valid"],
                "blockers": tuple(str(item) for item in report.get("blockers") or ()),
                "warnings": tuple(str(item) for item in report.get("warnings") or ()),
            }
        )
        return lineage.model_copy(update={"validation_report": canonical_report})


__all__ = ["ResearchArtifactLineageResolver"]
