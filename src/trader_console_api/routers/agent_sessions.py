"""Human-authorized reads and command intents for agent research sessions."""

from __future__ import annotations

from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, Request, Response
from fastapi.responses import JSONResponse

from ..contracts import (
    AgentSessionCommandRecord,
    AgentSessionCommandRequest,
    AgentSessionCommandsResponse,
    AgentSessionProjection,
    ApiError,
    TraderPrincipal,
)
from ..services.agent_sessions import (
    AgentSessionCommandConflict,
    AgentSessionNotFound,
    AgentSessionAuthorityError,
    AgentSessionDatabaseUnavailable,
    AgentSessionService,
    AgentSessionStorageUnavailable,
)
from .paper_operator_commands import require_operator_principal


router = APIRouter(prefix="/api/agent-sessions", tags=["agent-sessions"])
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0)]


def get_agent_session_service(request: Request) -> AgentSessionService:
    """Resolve the application-composed agent-session service."""
    return cast(AgentSessionService, request.app.state.agent_session_service)


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    """Return a stable no-store agent-session error envelope."""
    return JSONResponse(
        status_code=status_code,
        content=ApiError(code=code, message=message).model_dump(mode="json"),
        headers={"Cache-Control": "no-store"},
    )


def _failure(exc: Exception) -> JSONResponse:
    """Map agent-session failures to explicit transport outcomes."""
    if isinstance(exc, AgentSessionAuthorityError):
        return _error(403, "agent_session_human_authority_required", str(exc))
    if isinstance(exc, AgentSessionNotFound):
        return _error(404, "agent_session_not_found", str(exc))
    if isinstance(exc, AgentSessionCommandConflict):
        return _error(409, "agent_session_command_conflict", str(exc))
    if isinstance(exc, AgentSessionStorageUnavailable):
        return _error(503, "agent_session_storage_unavailable", str(exc))
    if isinstance(exc, AgentSessionDatabaseUnavailable):
        return _error(503, "database_unavailable", "Console database is unavailable")
    raise exc


@router.get(
    "/{session_id}",
    response_model=AgentSessionProjection,
    responses={401: {"model": ApiError}, 403: {"model": ApiError}, 404: {"model": ApiError}, 503: {"model": ApiError}},
)
async def get_agent_session(
    session_id: Annotated[str, Path(min_length=1, max_length=200)],
    response: Response,
    principal: Annotated[TraderPrincipal, Depends(require_operator_principal)],
    service: Annotated[AgentSessionService, Depends(get_agent_session_service)],
) -> AgentSessionProjection | JSONResponse:
    """Return one redacted session workspace to its human owner."""
    try:
        result = await service.get(session_id, principal)
    except Exception as exc:
        return _failure(exc)
    response.headers["Cache-Control"] = "no-store"
    return result


@router.post(
    "/{session_id}/commands",
    response_model=AgentSessionCommandRecord,
    status_code=202,
    responses={401: {"model": ApiError}, 403: {"model": ApiError}, 404: {"model": ApiError}, 409: {"model": ApiError}, 503: {"model": ApiError}},
)
async def command_agent_session(
    session_id: Annotated[str, Path(min_length=1, max_length=200)],
    request_body: AgentSessionCommandRequest,
    response: Response,
    principal: Annotated[TraderPrincipal, Depends(require_operator_principal)],
    service: Annotated[AgentSessionService, Depends(get_agent_session_service)],
) -> AgentSessionCommandRecord | JSONResponse:
    """Persist one human interrupt, resume, cancel, or inspect intent."""
    try:
        result = await service.command(session_id, request_body, principal)
    except Exception as exc:
        return _failure(exc)
    response.headers["Cache-Control"] = "no-store"
    return result


@router.get(
    "/{session_id}/commands",
    response_model=AgentSessionCommandsResponse,
    responses={401: {"model": ApiError}, 403: {"model": ApiError}, 404: {"model": ApiError}, 503: {"model": ApiError}},
)
async def list_agent_session_commands(
    session_id: Annotated[str, Path(min_length=1, max_length=200)],
    response: Response,
    principal: Annotated[TraderPrincipal, Depends(require_operator_principal)],
    service: Annotated[AgentSessionService, Depends(get_agent_session_service)],
    limit: Limit = 20,
    offset: Offset = 0,
) -> AgentSessionCommandsResponse | JSONResponse:
    """Return bounded command history for one authorized session."""
    try:
        result = await service.list_commands(
            session_id,
            limit=limit,
            offset=offset,
            principal=principal,
        )
    except Exception as exc:
        return _failure(exc)
    response.headers["Cache-Control"] = "no-store"
    return result


@router.get(
    "/{session_id}/commands/{command_id}",
    response_model=AgentSessionCommandRecord,
    responses={401: {"model": ApiError}, 403: {"model": ApiError}, 404: {"model": ApiError}, 503: {"model": ApiError}},
)
async def get_agent_session_command(
    session_id: Annotated[str, Path(min_length=1, max_length=200)],
    command_id: Annotated[UUID, Path()],
    response: Response,
    principal: Annotated[TraderPrincipal, Depends(require_operator_principal)],
    service: Annotated[AgentSessionService, Depends(get_agent_session_service)],
) -> AgentSessionCommandRecord | JSONResponse:
    """Return one exact command receipt after rechecking session ownership."""
    try:
        result = await service.get_command(session_id, command_id, principal)
    except Exception as exc:
        return _failure(exc)
    response.headers["Cache-Control"] = "no-store"
    return result


__all__ = ["get_agent_session_service", "router"]
