"""Application service for idempotent durable backtest execution commands."""

from __future__ import annotations

from uuid import UUID

from ..contracts import (
    BacktestExecutionRecord,
    BacktestExecutionsResponse,
    BacktestExecutionSubmit,
    PageInfo,
)
from ..repositories.backtest_executions import (
    BacktestExecutionDefinitionNotFound,
    BacktestExecutionNotFound,
    BacktestExecutionRepository,
)
from ..repositories.backtest_executions_schema import BacktestExecutionStorageUnavailable
from ..repositories.database import ConsoleDatabaseUnavailable


ExecutionDatabaseUnavailable = ConsoleDatabaseUnavailable


class BacktestExecutionService:
    """Submit and observe durable execution commands without running a worker."""

    def __init__(self, repository: BacktestExecutionRepository) -> None:
        """Bind the scope-owned execution repository."""
        self._repository = repository

    async def submit(self, request: BacktestExecutionSubmit) -> BacktestExecutionRecord:
        """Create one queued command or return the idempotent existing command."""
        async with self._repository.session(write=True) as session:
            await session.require_storage()
            try:
                return await session.submit(
                    request.definition_id,
                    idempotency_key=request.idempotency_key,
                )
            except BacktestExecutionDefinitionNotFound as exc:
                raise BacktestExecutionNotFound(str(exc)) from exc

    async def get(self, execution_id: UUID) -> BacktestExecutionRecord:
        """Return durable command status for one execution ID."""
        async with self._repository.session() as session:
            await session.require_storage()
            result = await session.get(execution_id)
        if result is None:
            raise BacktestExecutionNotFound("Backtest execution not found")
        return result

    async def list(self, *, limit: int, offset: int) -> BacktestExecutionsResponse:
        """Return bounded command history for the configured scope."""
        async with self._repository.session() as session:
            await session.require_storage()
            rows, total = await session.list(limit, offset)
        return BacktestExecutionsResponse(
            items=tuple(rows),
            page=PageInfo(limit=limit, offset=offset, total=total, has_more=offset + limit < total),
        )


__all__ = [
    "BacktestExecutionNotFound",
    "BacktestExecutionService",
    "BacktestExecutionStorageUnavailable",
    "ExecutionDatabaseUnavailable",
]
