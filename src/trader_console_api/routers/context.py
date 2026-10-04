"""HTTP transport for the Console's configured application context."""

from typing import Annotated, cast

from fastapi import APIRouter, Depends, Request, Response

from ..contracts import ConsoleScope
from ..services import ContextService


router = APIRouter(prefix="/api", tags=["context"])


def get_context_service(request: Request) -> ContextService:
    """Resolve the context service wired by the application composition root."""
    return cast(ContextService, request.app.state.context_service)


@router.get("/context", response_model=ConsoleScope, operation_id="get_context")
async def context(
    response: Response,
    service: Annotated[ContextService, Depends(get_context_service)],
) -> ConsoleScope:
    """Return configured scope, not verified broker identity or trading health."""
    response.headers["Cache-Control"] = "no-store"
    return service.context()
