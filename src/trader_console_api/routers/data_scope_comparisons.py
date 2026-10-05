"""HTTP read route for comparing saved market-data alternatives."""

from __future__ import annotations

from typing import Annotated, cast

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse

from ..contracts import ApiError
from ..data_scope_comparison_contracts import (
    DataScopeComparisonRequest,
    DataScopeComparisonResponse,
)
from ..services.data_scope_comparisons import (
    DataScopeComparisonDatabaseUnavailable,
    DataScopeComparisonNotFound,
    DataScopeComparisonService,
    DataScopeComparisonStorageUnavailable,
)

router = APIRouter(prefix="/api", tags=["data-scope-comparisons"])


def get_data_scope_comparison_service(request: Request) -> DataScopeComparisonService:
    """Resolve the application-composed comparison service."""
    return cast(DataScopeComparisonService, request.app.state.data_scope_comparison_service)


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    """Return a stable no-store API error."""
    return JSONResponse(
        status_code=status_code,
        content=ApiError(code=code, message=message).model_dump(mode="json"),
        headers={"Cache-Control": "no-store"},
    )


def _failure(exc: Exception) -> JSONResponse:
    """Map comparison failures to explicit transport outcomes."""
    if isinstance(exc, DataScopeComparisonNotFound):
        return _error(404, "data_scope_comparison_scope_not_found", str(exc))
    if isinstance(exc, DataScopeComparisonStorageUnavailable):
        return _error(503, "data_scope_comparison_storage_unavailable", str(exc))
    if isinstance(exc, DataScopeComparisonDatabaseUnavailable):
        return _error(503, "database_unavailable", "Console database is unavailable")
    raise exc


@router.post(
    "/data-scope-comparisons",
    response_model=DataScopeComparisonResponse,
    responses={404: {"model": ApiError}, 503: {"model": ApiError}},
)
async def compare_data_scopes(
    request: DataScopeComparisonRequest,
    response: Response,
    service: Annotated[DataScopeComparisonService, Depends(get_data_scope_comparison_service)],
) -> DataScopeComparisonResponse | JSONResponse:
    """Return pairwise evidence and exclusions for selected saved scopes."""
    try:
        result = await service.compare(request)
    except Exception as exc:
        return _failure(exc)
    response.headers["Cache-Control"] = "no-store"
    return result


__all__ = ["router"]
