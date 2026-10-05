"""Human command and read routes for reviewed-run next decisions."""

from __future__ import annotations

from typing import Annotated, cast

from fastapi import APIRouter, Depends, Path, Query, Request, Response
from fastapi.responses import JSONResponse

from ..contracts import (
    ApiError,
    NextResearchDecisionRecord,
    NextResearchDecisionsResponse,
    NextResearchDecisionRequest,
    TraderPrincipal,
)
from ..services.next_research_decisions import (
    NextDecisionAuthorityError,
    NextDecisionDatabaseUnavailable,
    NextDecisionRevisionConflict,
    NextResearchDecisionConflict,
    NextResearchDecisionEvidenceUnavailable,
    NextResearchDecisionNotFound,
    NextResearchDecisionService,
    NextResearchDecisionStorageUnavailable,
)
from .paper_operator_commands import require_operator_principal


router = APIRouter(prefix="/api/runs", tags=["research-decisions"])
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0)]


def get_next_research_decision_service(request: Request) -> NextResearchDecisionService:
    """Resolve the application-composed decision service."""
    return cast(NextResearchDecisionService, request.app.state.next_research_decision_service)


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    """Return a stable no-store decision error envelope."""
    return JSONResponse(
        status_code=status_code,
        content=ApiError(code=code, message=message).model_dump(mode="json"),
        headers={"Cache-Control": "no-store"},
    )


def _failure(exc: Exception) -> JSONResponse:
    """Map decision failures to explicit transport outcomes."""
    if isinstance(exc, NextDecisionAuthorityError):
        return _error(403, "next_decision_human_authority_required", str(exc))
    if isinstance(exc, (NextResearchDecisionEvidenceUnavailable,)):
        return _error(422, "next_decision_evidence_blocked", str(exc))
    if isinstance(exc, NextDecisionRevisionConflict):
        return _error(409, "next_decision_revision_conflict", str(exc))
    if isinstance(exc, NextResearchDecisionConflict):
        return _error(409, "next_decision_conflict", str(exc))
    if isinstance(exc, NextResearchDecisionNotFound):
        return _error(404, "next_decision_not_found", str(exc))
    if isinstance(exc, NextResearchDecisionStorageUnavailable):
        return _error(503, "next_decision_storage_unavailable", str(exc))
    if isinstance(exc, NextDecisionDatabaseUnavailable):
        return _error(503, "database_unavailable", "Console database is unavailable")
    raise exc


@router.post(
    "/{run_id}/next-decisions",
    response_model=NextResearchDecisionRecord,
    status_code=201,
    responses={401: {"model": ApiError}, 403: {"model": ApiError}, 409: {"model": ApiError}, 422: {"model": ApiError}, 503: {"model": ApiError}},
)
async def record_next_research_decision(
    run_id: Annotated[str, Path(min_length=1, max_length=200)],
    request_body: NextResearchDecisionRequest,
    response: Response,
    principal: Annotated[TraderPrincipal, Depends(require_operator_principal)],
    service: Annotated[NextResearchDecisionService, Depends(get_next_research_decision_service)],
) -> NextResearchDecisionRecord | JSONResponse:
    """Record one human-owned reject, refine, or continue decision."""
    try:
        result = await service.create(run_id, request_body, principal)
    except Exception as exc:
        return _failure(exc)
    response.headers["Cache-Control"] = "no-store"
    return result


@router.get(
    "/{run_id}/next-decisions",
    response_model=NextResearchDecisionsResponse,
    responses={401: {"model": ApiError}, 403: {"model": ApiError}, 503: {"model": ApiError}},
)
async def list_next_research_decisions(
    run_id: Annotated[str, Path(min_length=1, max_length=200)],
    response: Response,
    principal: Annotated[TraderPrincipal, Depends(require_operator_principal)],
    service: Annotated[NextResearchDecisionService, Depends(get_next_research_decision_service)],
    limit: Limit = 20,
    offset: Offset = 0,
) -> NextResearchDecisionsResponse | JSONResponse:
    """List the latest decision revision for each decision stream on a run."""
    try:
        result = await service.list(run_id, limit=limit, offset=offset, principal=principal)
    except Exception as exc:
        return _failure(exc)
    response.headers["Cache-Control"] = "no-store"
    return result


@router.get(
    "/{run_id}/next-decisions/{decision_id}",
    response_model=NextResearchDecisionRecord,
    responses={401: {"model": ApiError}, 403: {"model": ApiError}, 404: {"model": ApiError}, 503: {"model": ApiError}},
)
async def get_next_research_decision(
    run_id: Annotated[str, Path(min_length=1, max_length=200)],
    decision_id: Annotated[str, Path(min_length=1, max_length=200)],
    response: Response,
    principal: Annotated[TraderPrincipal, Depends(require_operator_principal)],
    service: Annotated[NextResearchDecisionService, Depends(get_next_research_decision_service)],
    revision: Annotated[int | None, Query(ge=1)] = None,
) -> NextResearchDecisionRecord | JSONResponse:
    """Read the latest or one exact immutable decision revision."""
    try:
        result = await service.get(run_id, decision_id, principal, revision)
    except Exception as exc:
        return _failure(exc)
    response.headers["Cache-Control"] = "no-store"
    return result


__all__ = ["get_next_research_decision_service", "router"]
