"""HTTP resources for market data and backtest evidence."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse

from ..contracts import (
    ApiError,
    BarsResponse,
    ExperimentRunsResponse,
    ExperimentsResponse,
    MAX_MARKET_DATA_BARS_PER_PAGE,
    MarketDatasetsResponse,
    RiskDecisionsResponse,
    RunDetail,
)
from ..services import ResourceDatabaseUnavailable, ResourceService

router = APIRouter(prefix="/api", tags=["resources"])
Limit = Annotated[int, Query(ge=1, le=5000)]
BarsLimit = Annotated[int, Query(ge=1, le=MAX_MARKET_DATA_BARS_PER_PAGE)]
Offset = Annotated[int, Query(ge=0)]


def get_resource_service(request: Request) -> ResourceService:
    """Resolve the application-owned resource service."""
    return cast(ResourceService, request.app.state.resource_service)


def _unavailable() -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content=ApiError(
            code="database_unavailable",
            message="Console database is unavailable",
        ).model_dump(mode="json"),
        headers={"Cache-Control": "no-store"},
    )


@router.get(
    "/market-data/datasets",
    response_model=MarketDatasetsResponse,
    responses={503: {"model": ApiError}},
)
async def market_datasets(
    response: Response,
    service: Annotated[ResourceService, Depends(get_resource_service)],
    limit: Limit = 100,
    offset: Offset = 0,
) -> MarketDatasetsResponse | JSONResponse:
    """List available symbol/timeframe/source market-data slices."""
    try:
        result = await service.market_datasets(limit=limit, offset=offset)
    except ResourceDatabaseUnavailable:
        return _unavailable()
    response.headers["Cache-Control"] = "no-store"
    return result


@router.get(
    "/market-data/bars",
    response_model=BarsResponse,
    responses={503: {"model": ApiError}},
)
async def market_data_bars(
    response: Response,
    service: Annotated[ResourceService, Depends(get_resource_service)],
    symbol: Annotated[str, Query(min_length=1, max_length=32)],
    asset_class: Literal["stock", "crypto"] = "stock",
    timeframe: Annotated[str, Query(min_length=1, max_length=32)] = "1Min",
    source: Annotated[str | None, Query(max_length=100)] = None,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: BarsLimit = 1000,
    offset: Offset = 0,
) -> BarsResponse | JSONResponse:
    """Return bounded OHLCV observations ordered from earliest to latest."""
    if start is not None and end is not None and end < start:
        raise HTTPException(status_code=422, detail="end must not precede start")
    try:
        result = await service.bars(
            asset_class=asset_class,
            symbol=symbol,
            timeframe=timeframe,
            source=source,
            start=start,
            end=end,
            limit=limit,
            offset=offset,
        )
    except ResourceDatabaseUnavailable:
        return _unavailable()
    response.headers["Cache-Control"] = "no-store"
    return result


@router.get(
    "/experiments",
    response_model=ExperimentsResponse,
    responses={503: {"model": ApiError}},
)
async def experiments(
    response: Response,
    service: Annotated[ResourceService, Depends(get_resource_service)],
    limit: Limit = 100,
    offset: Offset = 0,
) -> ExperimentsResponse | JSONResponse:
    """Discover experiment groups from published backtest runs."""
    try:
        result = await service.experiments(limit=limit, offset=offset)
    except ResourceDatabaseUnavailable:
        return _unavailable()
    response.headers["Cache-Control"] = "no-store"
    return result


@router.get(
    "/experiments/{experiment_id}/runs",
    response_model=ExperimentRunsResponse,
    responses={503: {"model": ApiError}},
)
async def experiment_runs(
    experiment_id: str,
    response: Response,
    service: Annotated[ResourceService, Depends(get_resource_service)],
    compatible_with_run_id: Annotated[str | None, Query(min_length=1)] = None,
    limit: Limit = 100,
    offset: Offset = 0,
) -> ExperimentRunsResponse | JSONResponse:
    """List runs and comparison eligibility within one experiment."""
    try:
        result = await service.experiment_runs(
            experiment_id=experiment_id,
            compatible_with_run_id=compatible_with_run_id,
            limit=limit,
            offset=offset,
        )
    except ResourceDatabaseUnavailable:
        return _unavailable()
    response.headers["Cache-Control"] = "no-store"
    return result


@router.get(
    "/runs/{run_id}/risk-decisions",
    response_model=RiskDecisionsResponse,
    responses={404: {"model": ApiError}, 503: {"model": ApiError}},
)
async def risk_decisions(
    run_id: str,
    response: Response,
    service: Annotated[ResourceService, Depends(get_resource_service)],
    manager_id: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
    outcome: Literal["approved", "transformed", "rejected"] | None = None,
    cycle_id: Annotated[str | None, Query(min_length=1, max_length=200)] = None,
    client_order_id: Annotated[str | None, Query(min_length=1, max_length=200)] = None,
    limit: Limit = 100,
    offset: Offset = 0,
) -> RiskDecisionsResponse | JSONResponse:
    """Return a bounded, filterable manager decision trace for one run."""
    try:
        result = await service.risk_decisions(
            run_id=run_id,
            manager_id=manager_id,
            outcome=outcome,
            cycle_id=cycle_id,
            client_order_id=client_order_id,
            limit=limit,
            offset=offset,
        )
    except ResourceDatabaseUnavailable:
        return _unavailable()
    if result is None:
        return JSONResponse(
            status_code=404,
            content=ApiError(
                code="run_not_found",
                message=f"No published run was found for {run_id}",
            ).model_dump(mode="json"),
            headers={"Cache-Control": "no-store"},
        )
    response.headers["Cache-Control"] = "no-store"
    return result


@router.get(
    "/runs/{run_id}",
    response_model=RunDetail,
    responses={404: {"model": ApiError}, 503: {"model": ApiError}},
)
async def run_detail(
    run_id: str,
    response: Response,
    service: Annotated[ResourceService, Depends(get_resource_service)],
    section_limit: Annotated[int, Query(ge=1, le=5000)] = 1000,
) -> RunDetail | JSONResponse:
    """Return a backtest run and its published evidence sections."""
    try:
        result = await service.run_detail(run_id=run_id, section_limit=section_limit)
    except ResourceDatabaseUnavailable:
        return _unavailable()
    if result is None:
        return JSONResponse(
            status_code=404,
            content=ApiError(
                code="run_not_found",
                message=f"No published run was found for {run_id}",
            ).model_dump(mode="json"),
            headers={"Cache-Control": "no-store"},
        )
    response.headers["Cache-Control"] = "no-store"
    return result
