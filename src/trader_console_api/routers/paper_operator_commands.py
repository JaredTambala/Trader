"""Authorized, audited paper-runtime command routes."""

from __future__ import annotations

from typing import Annotated, Any, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response
from fastapi.responses import JSONResponse

from ..contracts import (
    ApiError,
    PaperOperatorCommandRecord,
    PaperOperatorCommandsResponse,
    PaperOperatorCommandRequest,
    TraderPrincipal,
)
from ..services.paper_operator_commands import (
    PaperAdmissionUnavailable,
    PaperOperatorAuthorityError,
    PaperOperatorCommandConflict,
    PaperOperatorCommandDatabaseUnavailable,
    PaperOperatorCommandNotFound,
    PaperOperatorCommandService,
    PaperOperatorCommandStorageUnavailable,
    PaperOperatorScopeError,
)

router = APIRouter(prefix="/api/paper", tags=["paper-operator"])
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0)]


def get_paper_operator_command_service(request: Request) -> PaperOperatorCommandService:
    """Resolve the application-composed operator-command service."""
    return cast(PaperOperatorCommandService, request.app.state.paper_operator_command_service)


async def require_operator_principal(request: Request) -> TraderPrincipal:
    """Authenticate each mutation and require an explicit human operator identity."""
    provider = cast(Any, getattr(request.app.state, "authentication_provider", None))
    if provider is None:
        raise HTTPException(status_code=401, detail="Operator authentication is required")
    try:
        principal = await provider.authenticate(request)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Operator authentication failed") from exc
    if not principal.principal_id:
        raise HTTPException(status_code=401, detail="Operator authentication returned no principal")
    return principal


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    """Return a stable no-store command error envelope."""
    return JSONResponse(
        status_code=status_code,
        content=ApiError(code=code, message=message).model_dump(mode="json"),
        headers={"Cache-Control": "no-store"},
    )


def _failure(exc: Exception) -> JSONResponse:
    """Map command failures to explicit transport outcomes."""
    if isinstance(exc, PaperOperatorAuthorityError):
        return _error(403, "operator_authority_required", str(exc))
    if isinstance(exc, PaperOperatorScopeError):
        return _error(409, "paper_scope_required", str(exc))
    if isinstance(exc, PaperAdmissionUnavailable):
        return _error(409, "paper_admission_unavailable", str(exc))
    if isinstance(exc, PaperOperatorCommandConflict):
        return _error(409, "paper_command_conflict", str(exc))
    if isinstance(exc, PaperOperatorCommandNotFound):
        return _error(404, "paper_command_not_found", str(exc))
    if isinstance(exc, PaperOperatorCommandStorageUnavailable):
        return _error(503, "paper_command_storage_unavailable", str(exc))
    if isinstance(exc, PaperOperatorCommandDatabaseUnavailable):
        return _error(503, "database_unavailable", "Console database is unavailable")
    raise exc


@router.post(
    "/commands",
    response_model=PaperOperatorCommandRecord,
    status_code=202,
    responses={401: {"model": ApiError}, 403: {"model": ApiError}, 409: {"model": ApiError}, 503: {"model": ApiError}},
)
async def submit_paper_operator_command(
    request_body: PaperOperatorCommandRequest,
    response: Response,
    principal: Annotated[TraderPrincipal, Depends(require_operator_principal)],
    service: Annotated[PaperOperatorCommandService, Depends(get_paper_operator_command_service)],
) -> PaperOperatorCommandRecord | JSONResponse:
    """Validate and queue one human-authorized paper-runtime command."""
    try:
        result = await service.submit(request_body, principal)
    except Exception as exc:
        return _failure(exc)
    response.headers["Cache-Control"] = "no-store"
    return result


@router.get(
    "/commands",
    response_model=PaperOperatorCommandsResponse,
    responses={401: {"model": ApiError}, 403: {"model": ApiError}, 503: {"model": ApiError}},
)
async def list_paper_operator_commands(
    response: Response,
    principal: Annotated[TraderPrincipal, Depends(require_operator_principal)],
    service: Annotated[PaperOperatorCommandService, Depends(get_paper_operator_command_service)],
    limit: Limit = 20,
    offset: Offset = 0,
) -> PaperOperatorCommandsResponse | JSONResponse:
    """Return bounded command audit history for the authorized operator."""
    try:
        result = await service.list(limit=limit, offset=offset, principal=principal)
    except Exception as exc:
        return _failure(exc)
    response.headers["Cache-Control"] = "no-store"
    return result


@router.get(
    "/commands/{command_id}",
    response_model=PaperOperatorCommandRecord,
    responses={401: {"model": ApiError}, 403: {"model": ApiError}, 404: {"model": ApiError}, 503: {"model": ApiError}},
)
async def get_paper_operator_command(
    command_id: Annotated[UUID, Path()],
    response: Response,
    principal: Annotated[TraderPrincipal, Depends(require_operator_principal)],
    service: Annotated[PaperOperatorCommandService, Depends(get_paper_operator_command_service)],
) -> PaperOperatorCommandRecord | JSONResponse:
    """Return one durable command receipt for operator polling."""
    try:
        result = await service.get(command_id, principal)
    except Exception as exc:
        return _failure(exc)
    response.headers["Cache-Control"] = "no-store"
    return result


__all__ = ["get_paper_operator_command_service", "require_operator_principal", "router"]
