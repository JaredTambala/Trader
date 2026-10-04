"""Contracts for Console health application-service orchestration.

Subject: Translation of repository evidence into narrow liveness and readiness contracts.
Level: In-process service unit contract.
Collaborators: Real health service with a recording repository stub; no FastAPI or PostgreSQL.
Guarantees: Services orchestrate repository outcomes and preserve fail-closed startup semantics.
Non-goals: HTTP status codes, connection transactions, SQL correctness, and process lifespan.
"""

from __future__ import annotations

import asyncio

import pytest

from trader_console_api.repositories import (
    ConsoleDatabaseUnavailable,
    SchemaCompatibility,
)
from trader_console_api.services import HealthService, IncompatibleDatabaseSchema


class _CompatibilityRepository:
    def __init__(
        self,
        inspection: SchemaCompatibility | None = None,
        *,
        unavailable: bool = False,
    ) -> None:
        self.inspection = inspection
        self.unavailable = unavailable
        self.calls = 0

    async def inspect(self) -> SchemaCompatibility:
        self.calls += 1
        if self.unavailable:
            raise ConsoleDatabaseUnavailable("test outage")
        assert self.inspection is not None
        return self.inspection


def _service(repository: _CompatibilityRepository) -> HealthService:
    return HealthService(
        scope_id="paper-primary",
        compatibility_repository=repository,
    )


def test_liveness_does_not_invoke_the_compatibility_repository() -> None:
    """Keep the process claim independent from every database collaborator."""
    repository = _CompatibilityRepository(unavailable=True)

    response = _service(repository).liveness()

    assert response.status == "alive"
    assert repository.calls == 0


def test_readiness_maps_compatible_repository_evidence() -> None:
    """Return scope-bound readiness when repository evidence is fully compatible."""
    repository = _CompatibilityRepository(SchemaCompatibility(1, 1, ()))

    response = asyncio.run(_service(repository).readiness())

    assert response.status == "ready"
    assert response.scope_id == "paper-primary"
    assert response.contract_version == 1


def test_readiness_maps_database_failure_without_leaking_exception_text() -> None:
    """Expose one stable unavailable code instead of adapter-specific database details."""
    repository = _CompatibilityRepository(unavailable=True)

    response = asyncio.run(_service(repository).readiness())

    assert response.status == "unavailable"
    assert response.issues == ("database_unavailable",)


def test_startup_service_rejects_incompatible_repository_evidence() -> None:
    """Preserve the exact repository issue when startup admission must fail closed."""
    repository = _CompatibilityRepository(
        SchemaCompatibility(0, 0, ("database_schema_too_old",))
    )

    with pytest.raises(IncompatibleDatabaseSchema, match="database_schema_too_old"):
        asyncio.run(_service(repository).require_startup_readiness())
