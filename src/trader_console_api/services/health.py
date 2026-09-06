"""Application service for Console process and database health."""

from __future__ import annotations

from typing import Protocol

from ..contracts import LivenessResponse, ReadinessResponse
from ..repositories import (
    ConsoleDatabaseUnavailable,
    SchemaCompatibility,
)


class CompatibilityRepository(Protocol):
    """Repository port required by health orchestration."""

    async def inspect(self) -> SchemaCompatibility:
        """Return current database-schema compatibility evidence."""
        ...


class IncompatibleDatabaseSchema(RuntimeError):
    """Raised when API startup observes an incompatible database schema."""

    def __init__(self, inspection: SchemaCompatibility) -> None:
        """Build an actionable startup error from stable issue codes."""
        self.inspection = inspection
        issues = ", ".join(inspection.issues) or "unknown_schema_compatibility_issue"
        super().__init__(f"Console database schema is incompatible: {issues}")


class HealthService:
    """Orchestrate narrow process and database readiness claims."""

    def __init__(
        self,
        *,
        scope_id: str,
        compatibility_repository: CompatibilityRepository,
    ) -> None:
        """Bind health orchestration to one scope and compatibility repository."""
        self._scope_id = scope_id
        self._compatibility_repository = compatibility_repository

    def liveness(self) -> LivenessResponse:
        """Return process liveness without touching an external collaborator."""
        return LivenessResponse()

    async def readiness(self) -> ReadinessResponse:
        """Return database readiness without leaking adapter errors."""
        try:
            inspection = await self._compatibility_repository.inspect()
        except ConsoleDatabaseUnavailable:
            return ReadinessResponse(
                status="unavailable",
                scope_id=self._scope_id,
                issues=("database_unavailable",),
            )
        if not inspection.ready:
            return ReadinessResponse(
                status="unavailable",
                scope_id=self._scope_id,
                contract_version=inspection.installed_version,
                issues=inspection.issues,
            )
        return ReadinessResponse(
            status="ready",
            scope_id=self._scope_id,
            contract_version=inspection.installed_version,
        )

    async def require_startup_readiness(self) -> SchemaCompatibility:
        """Return startup evidence or raise when the database is incompatible."""
        inspection = await self._compatibility_repository.inspect()
        if not inspection.ready:
            raise IncompatibleDatabaseSchema(inspection)
        return inspection
