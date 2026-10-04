"""HTTP routes for immutable saved data scopes."""

from __future__ import annotations

from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, Request, Response
from fastapi.responses import JSONResponse

from ..data_scope_contracts import (
    SavedDataScope,
    SavedDataScopeCreate,
    SavedDataScopesResponse,
)
from ..contracts import ApiError
from ..services.saved_data_scopes import (
    SavedDataScopeConflict,
    SavedDataScopeDatabaseUnavailable,
    SavedDataScopeNotFound,
    SavedDataScopeService,
    SavedDataScopeStorageUnavailable,
)


router = APIRouter(prefix="/api/data-scopes", tags=["data-scopes"])
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0)]


def get_saved_scope_service(request: Request) -> SavedDataScopeService:
    """Resolve the application-composed saved-scope service."""
    return cast(SavedDataScopeService, request.app.state.saved_data_scope_service)


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    """Return a no-store typed error response."""
    return JSONResponse(
        status_code=status_code,
        content=ApiError(code=code, message=message).model_dump(mode="json"),
        headers={"Cache-Control": "no-store"},
    )


def _failure(exc: Exception) -> JSONResponse:
    """Map saved-scope failures to stable transport outcomes."""
    if isinstance(exc, SavedDataScopeNotFound):
        return _error(404, "saved_data_scope_not_found", str(exc))
    if isinstance(exc, SavedDataScopeConflict):
        return _error(409, "saved_data_scope_conflict", str(exc))
    if isinstance(exc, SavedDataScopeStorageUnavailable):
        return _error(503, "saved_data_scope_storage_unavailable", str(exc))
    if isinstance(exc, SavedDataScopeDatabaseUnavailable):
        return _error(503, "database_unavailable", "Console database is unavailable")
    raise exc


@router.post(
    "",
    response_model=SavedDataScope,
    status_code=201,
    responses={409: {"model": ApiError}, 503: {"model": ApiError}},
)
async def create_saved_data_scope(
    request: SavedDataScopeCreate,
    response: Response,
    service: Annotated[SavedDataScopeService, Depends(get_saved_scope_service)],
) -> SavedDataScope | JSONResponse:
    """Persist one exact scope and matching manifest/quality references."""
    try:
        result = await service.create(request)
    except Exception as exc:
        return _failure(exc)
    response.headers["Cache-Control"] = "no-store"
    return result


@router.get(
    "",
    response_model=SavedDataScopesResponse,
    responses={503: {"model": ApiError}},
)
async def list_saved_data_scopes(
    response: Response,
    service: Annotated[SavedDataScopeService, Depends(get_saved_scope_service)],
    limit: Limit = 20,
    offset: Offset = 0,
) -> SavedDataScopesResponse | JSONResponse:
    """List saved scopes without changing their evidence state."""
    try:
        result = await service.list(limit=limit, offset=offset)
    except Exception as exc:
        return _failure(exc)
    response.headers["Cache-Control"] = "no-store"
    return result


@router.get(
    "/{saved_scope_id}",
    response_model=SavedDataScope,
    responses={404: {"model": ApiError}, 503: {"model": ApiError}},
)
async def get_saved_data_scope(
    saved_scope_id: Annotated[UUID, Path()],
    response: Response,
    service: Annotated[SavedDataScopeService, Depends(get_saved_scope_service)],
) -> SavedDataScope | JSONResponse:
    """Reopen one saved scope with its persisted evidence qualification."""
    try:
        result = await service.get(saved_scope_id)
    except Exception as exc:
        return _failure(exc)
    response.headers["Cache-Control"] = "no-store"
    return result


@router.post(
    "/{saved_scope_id}/revalidate",
    response_model=SavedDataScope,
    responses={404: {"model": ApiError}, 503: {"model": ApiError}},
)
async def revalidate_saved_data_scope(
    saved_scope_id: Annotated[UUID, Path()],
    response: Response,
    service: Annotated[SavedDataScopeService, Depends(get_saved_scope_service)],
) -> SavedDataScope | JSONResponse:
    """Re-read exact producer evidence and persist active/stale/unavailable state."""
    try:
        result = await service.revalidate(saved_scope_id)
    except Exception as exc:
        return _failure(exc)
    response.headers["Cache-Control"] = "no-store"
    return result


__all__ = ["router"]
