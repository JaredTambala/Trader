"""HTTP transport for Console liveness and readiness."""

from __future__ import annotations

from typing import Annotated, cast

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse

from ..contracts import LivenessResponse, ReadinessResponse
from ..services import HealthService


router = APIRouter(prefix="/health", tags=["health"])


def get_health_service(request: Request) -> HealthService:
    """Resolve the lifespan-created health service for a request."""
    return cast(HealthService, request.app.state.health_service)


HealthServiceDependency = Annotated[HealthService, Depends(get_health_service)]


@router.get("/live", response_model=LivenessResponse)
async def liveness(
    response: Response,
    service: HealthServiceDependency,
) -> LivenessResponse:
    """Translate the service's process-liveness contract to HTTP."""
    response.headers["Cache-Control"] = "no-store"
    return service.liveness()


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    responses={503: {"model": ReadinessResponse}},
)
async def readiness(
    response: Response,
    service: HealthServiceDependency,
) -> ReadinessResponse | JSONResponse:
    """Translate the service's database readiness to HTTP."""
    payload = await service.readiness()
    if payload.status == "unavailable":
        return JSONResponse(
            status_code=503,
            content=payload.model_dump(mode="json"),
            headers={"Cache-Control": "no-store"},
        )
    response.headers["Cache-Control"] = "no-store"
    return payload
