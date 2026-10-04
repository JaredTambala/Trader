"""HTTP resources for durable backtest execution commands."""

from __future__ import annotations

from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, Request, Response
from fastapi.responses import JSONResponse

from ..contracts import (
    ApiError,
    BacktestExecutionRecord,
    BacktestExecutionsResponse,
    BacktestExecutionSubmit,
)
from ..services.backtest_executions import (
    BacktestExecutionNotFound,
    BacktestExecutionService,
    BacktestExecutionStorageUnavailable,
    ExecutionDatabaseUnavailable,
)


router = APIRouter(prefix="/api/backtests", tags=["backtests"])
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0)]


def get_execution_service(request: Request) -> BacktestExecutionService:
    """Resolve the scope-bound execution service composed by the application."""
    return cast(BacktestExecutionService, request.app.state.backtest_execution_service)


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    """Return a stable no-store command error envelope."""
    return JSONResponse(
        status_code=status_code,
        content=ApiError(code=code, message=message).model_dump(mode="json"),
        headers={"Cache-Control": "no-store"},
    )


def _failure(exc: Exception) -> JSONResponse:
    """Map durable command failures to HTTP status and error code."""
    if isinstance(exc, BacktestExecutionNotFound):
        return _error(404, "backtest_execution_not_found", str(exc))
    if isinstance(exc, BacktestExecutionStorageUnavailable):
        return _error(503, "execution_storage_unavailable", str(exc))
    if isinstance(exc, ExecutionDatabaseUnavailable):
        return _error(503, "database_unavailable", "Console database is unavailable")
    raise exc


@router.get(
    "/executions",
    response_model=BacktestExecutionsResponse,
    responses={503: {"model": ApiError}},
)
async def list_backtest_executions(
    response: Response,
    service: Annotated[BacktestExecutionService, Depends(get_execution_service)],
    limit: Limit = 20,
    offset: Offset = 0,
) -> BacktestExecutionsResponse | JSONResponse:
    """List durable commands in the configured scope."""
    try:
        result = await service.list(limit=limit, offset=offset)
    except Exception as exc:
        return _failure(exc)
    response.headers["Cache-Control"] = "no-store"
    return result


@router.post(
    "/executions",
    response_model=BacktestExecutionRecord,
    status_code=202,
    responses={404: {"model": ApiError}, 503: {"model": ApiError}},
)
async def submit_backtest_execution(
    request: BacktestExecutionSubmit,
    response: Response,
    service: Annotated[BacktestExecutionService, Depends(get_execution_service)],
) -> BacktestExecutionRecord | JSONResponse:
    """Submit one idempotent queued command for an immutable definition."""
    try:
        result = await service.submit(request)
    except Exception as exc:
        return _failure(exc)
    response.headers["Cache-Control"] = "no-store"
    return result


@router.get(
    "/executions/{execution_id}",
    response_model=BacktestExecutionRecord,
    responses={404: {"model": ApiError}, 503: {"model": ApiError}},
)
async def get_backtest_execution(
    execution_id: Annotated[UUID, Path()],
    response: Response,
    service: Annotated[BacktestExecutionService, Depends(get_execution_service)],
) -> BacktestExecutionRecord | JSONResponse:
    """Return durable status for one execution command."""
    try:
        result = await service.get(execution_id)
    except Exception as exc:
        return _failure(exc)
    response.headers["Cache-Control"] = "no-store"
    return result


__all__ = ["router"]
