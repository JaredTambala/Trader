"""Read-only paper-runtime operations route."""

from __future__ import annotations

from typing import Annotated, cast

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse

from ..contracts import ApiError, PaperRuntimeOperations
from ..services.paper_runtime import PaperRuntimeDatabaseUnavailable, PaperRuntimeService

router = APIRouter(prefix="/api/paper", tags=["paper-runtime"])


def get_paper_runtime_service(request: Request) -> PaperRuntimeService:
    """Resolve the application-owned paper-runtime service."""
    return cast(PaperRuntimeService, request.app.state.paper_runtime_service)


@router.get(
    "/runtime",
    response_model=PaperRuntimeOperations,
    responses={503: {"model": ApiError}},
)
async def paper_runtime(
    response: Response,
    service: Annotated[PaperRuntimeService, Depends(get_paper_runtime_service)],
) -> PaperRuntimeOperations | JSONResponse:
    """Return read-only paper operational evidence with explicit qualifiers."""
    try:
        result = await service.operations()
    except PaperRuntimeDatabaseUnavailable:
        return JSONResponse(
            status_code=503,
            content=ApiError(code="database_unavailable", message="Console database is unavailable").model_dump(mode="json"),
            headers={"Cache-Control": "no-store"},
        )
    response.headers["Cache-Control"] = "no-store"
    return result
