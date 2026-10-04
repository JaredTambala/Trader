"""HTTP resources for saved experiment comparison definitions."""

from __future__ import annotations

from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, Request, Response
from fastapi.responses import JSONResponse

from ..comparison_contracts import (
    ComparisonEvaluation,
    ComparisonViewDefinition,
    ComparisonViewDetail,
    ComparisonViewUpdate,
    ComparisonViewsResponse,
)
from ..contracts import ApiError
from ..services.comparison_views import (
    ComparisonDatabaseUnavailable,
    ComparisonNotFound,
    ComparisonRevisionConflict,
    ComparisonStorageUnavailable,
    ComparisonViewService,
    InvalidComparisonSelection,
)

router = APIRouter(prefix="/api", tags=["comparison-views"])
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0)]


def get_comparison_view_service(request: Request) -> ComparisonViewService:
    """Resolve the scope-bound comparison service composed by the app."""
    return cast(ComparisonViewService, request.app.state.comparison_view_service)


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    """Return the stable API error envelope with evidence disabled for caching."""
    return JSONResponse(
        status_code=status_code,
        content=ApiError(code=code, message=message).model_dump(mode="json"),
        headers={"Cache-Control": "no-store"},
    )


def _failure(exc: Exception) -> JSONResponse:
    """Map service failures to their transport contract."""
    if isinstance(exc, ComparisonNotFound):
        return _error(404, "comparison_view_not_found", str(exc))
    if isinstance(exc, InvalidComparisonSelection):
        return _error(422, "invalid_comparison_selection", str(exc))
    if isinstance(exc, ComparisonRevisionConflict):
        return _error(409, "comparison_view_revision_conflict", str(exc))
    if isinstance(exc, ComparisonStorageUnavailable):
        return _error(503, "comparison_storage_unavailable", str(exc))
    if isinstance(exc, ComparisonDatabaseUnavailable):
        return _error(503, "database_unavailable", "Console database is unavailable")
    raise exc


@router.post(
    "/experiments/{experiment_id}/comparison-views/preview",
    response_model=ComparisonEvaluation,
    responses={404: {"model": ApiError}, 503: {"model": ApiError}},
)
async def preview_comparison_view(
    experiment_id: Annotated[str, Path(min_length=1, max_length=256)],
    definition: ComparisonViewDefinition,
    response: Response,
    service: Annotated[ComparisonViewService, Depends(get_comparison_view_service)],
) -> ComparisonEvaluation | JSONResponse:
    """Evaluate a draft against current evidence without saving it."""
    try:
        result = await service.preview(experiment_id, definition)
    except Exception as exc:  # mapped below; unexpected failures remain visible
        return _failure(exc)
    response.headers["Cache-Control"] = "no-store"
    return result


@router.get(
    "/experiments/{experiment_id}/comparison-views",
    response_model=ComparisonViewsResponse,
    responses={503: {"model": ApiError}},
)
async def list_comparison_views(
    experiment_id: Annotated[str, Path(min_length=1, max_length=256)],
    response: Response,
    service: Annotated[ComparisonViewService, Depends(get_comparison_view_service)],
    limit: Limit = 20,
    offset: Offset = 0,
) -> ComparisonViewsResponse | JSONResponse:
    """List saved definitions for one experiment and configured scope."""
    try:
        result = await service.list(experiment_id, limit=limit, offset=offset)
    except Exception as exc:
        return _failure(exc)
    response.headers["Cache-Control"] = "no-store"
    return result


@router.post(
    "/experiments/{experiment_id}/comparison-views",
    response_model=ComparisonViewDetail,
    status_code=201,
    responses={404: {"model": ApiError}, 422: {"model": ApiError}, 503: {"model": ApiError}},
)
async def create_comparison_view(
    experiment_id: Annotated[str, Path(min_length=1, max_length=256)],
    definition: ComparisonViewDefinition,
    response: Response,
    service: Annotated[ComparisonViewService, Depends(get_comparison_view_service)],
) -> ComparisonViewDetail | JSONResponse:
    """Persist a new user-authored comparison definition."""
    try:
        result = await service.save(experiment_id, definition)
    except Exception as exc:
        return _failure(exc)
    response.headers["Cache-Control"] = "no-store"
    return result


@router.get(
    "/experiments/{experiment_id}/comparison-views/{view_id}",
    response_model=ComparisonViewDetail,
    responses={404: {"model": ApiError}, 503: {"model": ApiError}},
)
async def get_comparison_view(
    experiment_id: Annotated[str, Path(min_length=1, max_length=256)],
    view_id: UUID,
    response: Response,
    service: Annotated[ComparisonViewService, Depends(get_comparison_view_service)],
) -> ComparisonViewDetail | JSONResponse:
    """Load one definition and reevaluate its selected evidence now."""
    try:
        result = await service.get(experiment_id, view_id)
    except Exception as exc:
        return _failure(exc)
    response.headers["Cache-Control"] = "no-store"
    return result


@router.put(
    "/experiments/{experiment_id}/comparison-views/{view_id}",
    response_model=ComparisonViewDetail,
    responses={404: {"model": ApiError}, 409: {"model": ApiError}, 422: {"model": ApiError}, 503: {"model": ApiError}},
)
async def replace_comparison_view(
    experiment_id: Annotated[str, Path(min_length=1, max_length=256)],
    view_id: UUID,
    update: ComparisonViewUpdate,
    response: Response,
    service: Annotated[ComparisonViewService, Depends(get_comparison_view_service)],
) -> ComparisonViewDetail | JSONResponse:
    """Replace a definition only when its revision is still current."""
    try:
        result = await service.replace(experiment_id, view_id, update)
    except Exception as exc:
        return _failure(exc)
    response.headers["Cache-Control"] = "no-store"
    return result


__all__ = ["router"]
