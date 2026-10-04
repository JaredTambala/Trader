"""Application service for preflight-gated immutable backtest definitions."""

from __future__ import annotations

from uuid import UUID

from ..contracts import (
    BacktestDefinitionRevision,
    BacktestDefinitionsResponse,
    BacktestPreflightRequest,
    BacktestPreflightResponse,
    PageInfo,
)
from ..repositories.backtest_definitions import (
    BacktestDefinitionConflict,
    BacktestDefinitionNotFound,
    BacktestDefinitionRepository,
)
from ..repositories.backtest_definitions_schema import BacktestDefinitionStorageUnavailable
from ..repositories.database import ConsoleDatabaseUnavailable
from .catalogue import PreflightService


class InvalidBacktestDefinition(ValueError):
    """A draft failed preflight and therefore cannot be persisted."""

    def __init__(self, result: BacktestPreflightResponse) -> None:
        """Keep the typed preflight issues for the 422 response."""
        super().__init__("Backtest definition failed preflight")
        self.result = result


DefinitionDatabaseUnavailable = ConsoleDatabaseUnavailable


class BacktestDefinitionService:
    """Preflight, persist, and retrieve immutable definition revisions."""

    def __init__(
        self,
        repository: BacktestDefinitionRepository,
        preflight: PreflightService,
    ) -> None:
        """Bind the scope-owned repository and read-only preflight service."""
        self._repository = repository
        self._preflight = preflight

    async def create(self, draft: BacktestPreflightRequest) -> BacktestDefinitionRevision:
        """Preflight a draft, then persist its normalized first revision."""
        result = await self._validated(draft)
        assert result.normalized_definition is not None
        async with self._repository.session(write=True) as session:
            await session.require_storage()
            return await session.create(
                result.normalized_definition,
                fingerprint=result.definition_fingerprint or "",
            )

    async def create_revision(
        self,
        definition_id: UUID,
        draft: BacktestPreflightRequest,
    ) -> BacktestDefinitionRevision:
        """Preflight a draft and append a new immutable revision."""
        result = await self._validated(draft)
        assert result.normalized_definition is not None
        async with self._repository.session(write=True) as session:
            await session.require_storage()
            return await session.create_revision(
                definition_id,
                result.normalized_definition,
                fingerprint=result.definition_fingerprint or "",
            )

    async def get(self, definition_id: UUID) -> BacktestDefinitionRevision:
        """Return the latest revision for one definition identity."""
        async with self._repository.session() as session:
            await session.require_storage()
            result = await session.get(definition_id)
        if result is None:
            raise BacktestDefinitionNotFound("Backtest definition not found")
        return result

    async def list(self, *, limit: int, offset: int) -> BacktestDefinitionsResponse:
        """Return a bounded page of latest definition revisions."""
        async with self._repository.session() as session:
            await session.require_storage()
            rows, total = await session.list(limit, offset)
        return BacktestDefinitionsResponse(
            items=tuple(rows),
            page=PageInfo(limit=limit, offset=offset, total=total, has_more=offset + limit < total),
        )

    async def _validated(self, draft: BacktestPreflightRequest) -> BacktestPreflightResponse:
        """Run side-effect-free preflight and reject every error before writes."""
        result = await self._preflight.preflight(draft)
        if not result.valid or result.normalized_definition is None:
            raise InvalidBacktestDefinition(result)
        return result


__all__ = [
    "BacktestDefinitionConflict",
    "BacktestDefinitionNotFound",
    "BacktestDefinitionService",
    "BacktestDefinitionStorageUnavailable",
    "DefinitionDatabaseUnavailable",
    "InvalidBacktestDefinition",
]
