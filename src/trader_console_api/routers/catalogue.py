"""HTTP resources for allowlisted backtest profiles and preflight."""

from __future__ import annotations

from typing import Annotated, cast

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse

from ..contracts import (
    ApiError,
    BacktestCatalogueResponse,
    BacktestPreflightRequest,
    BacktestPreflightResponse,
)
from ..services.catalogue import CatalogueDatabaseUnavailable, CatalogueService, PreflightService


router = APIRouter(prefix="/api/backtests", tags=["backtests"])


def get_catalogue_service(request: Request) -> CatalogueService:
    """Resolve the immutable catalogue service composed by the application."""
    return cast(CatalogueService, request.app.state.catalogue_service)


def get_preflight_service(request: Request) -> PreflightService:
    """Resolve the scope-bound preflight service composed by the application."""
    return cast(PreflightService, request.app.state.preflight_service)


def _unavailable() -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content=ApiError(
            code="database_unavailable",
            message="Console database is unavailable",
        ).model_dump(mode="json"),
        headers={"Cache-Control": "no-store"},
    )


@router.get("/catalogue", response_model=BacktestCatalogueResponse)
async def backtest_catalogue(
    response: Response,
    service: Annotated[CatalogueService, Depends(get_catalogue_service)],
) -> BacktestCatalogueResponse:
    """Return the allowlisted strategy and risk profiles."""
    response.headers["Cache-Control"] = "no-store"
    return service.describe()


@router.post(
    "/preflight",
    response_model=BacktestPreflightResponse,
    responses={503: {"model": ApiError}},
)
async def backtest_preflight(
    draft: BacktestPreflightRequest,
    response: Response,
    service: Annotated[PreflightService, Depends(get_preflight_service)],
) -> BacktestPreflightResponse | JSONResponse:
    """Normalize and validate a draft without persisting or queueing it."""
    try:
        result = await service.preflight(draft)
    except CatalogueDatabaseUnavailable:
        return _unavailable()
    response.headers["Cache-Control"] = "no-store"
    return result


__all__ = ["router"]
