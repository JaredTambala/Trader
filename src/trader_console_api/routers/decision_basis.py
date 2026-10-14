"""Authenticated read route for the exact evidence behind a human decision."""

from typing import Annotated, cast

from fastapi import APIRouter, Depends, Path, Request, Response
from fastapi.responses import JSONResponse

from ..contracts import ApiError, TraderPrincipal
from ..decision_basis_contracts import DecisionBasisResponse
from ..services.decision_basis import DecisionBasisService
from .next_research_decisions import _failure
from .paper_operator_commands import require_operator_principal

router = APIRouter(prefix="/api/runs", tags=["research-decisions"])


def get_decision_basis_service(request: Request) -> DecisionBasisService:
    """Resolve the application's read-only decision evidence service."""
    return cast(DecisionBasisService, request.app.state.decision_basis_service)


@router.get(
    "/{run_id}/decision-basis", response_model=DecisionBasisResponse,
    responses={401: {"model": ApiError}, 403: {"model": ApiError}, 503: {"model": ApiError}},
)
async def get_decision_basis(
    run_id: Annotated[str, Path(min_length=1, max_length=200)],
    response: Response,
    principal: Annotated[TraderPrincipal, Depends(require_operator_principal)],
    service: Annotated[DecisionBasisService, Depends(get_decision_basis_service)],
) -> DecisionBasisResponse | JSONResponse:
    """Return verified references without writing a decision or launching execution."""
    try:
        result = await service.get(run_id, principal)
    except Exception as exc:
        return _failure(exc)
    response.headers["Cache-Control"] = "no-store"
    return result
