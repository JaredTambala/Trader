"""HTTP resources for immutable Console backtest definitions."""

from __future__ import annotations

from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, Request, Response
from fastapi.responses import JSONResponse

from ..contracts import (
    ApiError,
    BacktestDefinitionRevision,
    BacktestDefinitionsResponse,
    BacktestPreflightRequest,
    BacktestPreflightResponse,
)
from ..services.backtest_definitions import (
    BacktestDefinitionConflict,
    BacktestDefinitionNotFound,
    BacktestDefinitionService,
    BacktestDefinitionStorageUnavailable,
    DefinitionDatabaseUnavailable,
    InvalidBacktestDefinition,
)


router = APIRouter(prefix="/api/backtests", tags=["backtests"])
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0)]


def get_definition_service(request: Request) -> BacktestDefinitionService:
    """Resolve the scope-bound definition service composed by the application."""
    return cast(BacktestDefinitionService, request.app.state.backtest_definition_service)


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    """Return the stable error envelope with evidence disabled for caching."""
    return JSONResponse(
        status_code=status_code,
        content=ApiError(code=code, message=message).model_dump(mode="json"),
        headers={"Cache-Control": "no-store"},
    )


def _failure(exc: Exception) -> JSONResponse:
    """Map definition service failures to the HTTP contract."""
    if isinstance(exc, InvalidBacktestDefinition):
        return JSONResponse(
            status_code=422,
            content=exc.result.model_dump(mode="json"),
            headers={"Cache-Control": "no-store"},
        )
    if isinstance(exc, BacktestDefinitionNotFound):
        return _error(404, "backtest_definition_not_found", str(exc))
    if isinstance(exc, BacktestDefinitionConflict):
        return _error(409, "backtest_definition_conflict", str(exc))
    if isinstance(exc, BacktestDefinitionStorageUnavailable):
        return _error(503, "definition_storage_unavailable", str(exc))
    if isinstance(exc, DefinitionDatabaseUnavailable):
        return _error(503, "database_unavailable", "Console database is unavailable")
    raise exc


@router.get(
    "/definitions",
    response_model=BacktestDefinitionsResponse,
    responses={503: {"model": ApiError}},
)
async def list_backtest_definitions(
    response: Response,
    service: Annotated[BacktestDefinitionService, Depends(get_definition_service)],
    limit: Limit = 20,
    offset: Offset = 0,
) -> BacktestDefinitionsResponse | JSONResponse:
    """List latest immutable revisions in the configured scope."""
    try:
        result = await service.list(limit=limit, offset=offset)
    except Exception as exc:
        return _failure(exc)
    response.headers["Cache-Control"] = "no-store"
    return result


@router.post(
    "/definitions",
    response_model=BacktestDefinitionRevision,
    status_code=201,
    responses={
        409: {"model": ApiError},
        422: {"model": BacktestPreflightResponse},
        503: {"model": ApiError},
    },
)
async def create_backtest_definition(
    draft: BacktestPreflightRequest,
    response: Response,
    service: Annotated[BacktestDefinitionService, Depends(get_definition_service)],
) -> BacktestDefinitionRevision | JSONResponse:
    """Preflight and persist the first immutable revision for a definition."""
    try:
        result = await service.create(draft)
    except Exception as exc:
        return _failure(exc)
    response.headers["Cache-Control"] = "no-store"
    return result


@router.get(
    "/definitions/{definition_id}",
    response_model=BacktestDefinitionRevision,
    responses={404: {"model": ApiError}, 503: {"model": ApiError}},
)
async def get_backtest_definition(
    definition_id: Annotated[UUID, Path()],
    response: Response,
    service: Annotated[BacktestDefinitionService, Depends(get_definition_service)],
) -> BacktestDefinitionRevision | JSONResponse:
    """Return the latest immutable revision for one definition identity."""
    try:
        result = await service.get(definition_id)
    except Exception as exc:
        return _failure(exc)
    response.headers["Cache-Control"] = "no-store"
    return result


@router.post(
    "/definitions/{definition_id}/revisions",
    response_model=BacktestDefinitionRevision,
    status_code=201,
    responses={
        404: {"model": ApiError},
        409: {"model": ApiError},
        422: {"model": BacktestPreflightResponse},
        503: {"model": ApiError},
    },
)
async def create_backtest_definition_revision(
    definition_id: Annotated[UUID, Path()],
    draft: BacktestPreflightRequest,
    response: Response,
    service: Annotated[BacktestDefinitionService, Depends(get_definition_service)],
) -> BacktestDefinitionRevision | JSONResponse:
    """Preflight and append one immutable revision to an existing definition."""
    try:
        result = await service.create_revision(definition_id, draft)
    except Exception as exc:
        return _failure(exc)
    response.headers["Cache-Control"] = "no-store"
    return result


__all__ = ["router"]
