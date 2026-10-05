"""Application boundary for authorized paper-runtime commands."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Any
from uuid import UUID

from trader.runtime.operator_control import is_human_operator_principal

from ..contracts import (
    ConsoleEnvironment,
    ConsoleScope,
    PageInfo,
    PaperOperatorCommandRecord,
    PaperOperatorCommandsResponse,
    PaperOperatorCommandRequest,
    TraderPrincipal,
)
from ..repositories.database import ConsoleDatabaseUnavailable
from ..repositories.paper_operator_commands import (
    PaperOperatorCommandConflict,
    PaperOperatorCommandNotFound,
    PaperOperatorCommandRepository,
)
from ..repositories.paper_operator_commands_schema import PaperOperatorCommandStorageUnavailable


class PaperOperatorAuthorityError(RuntimeError):
    """The authenticated principal cannot operate paper runtime."""


class PaperOperatorScopeError(RuntimeError):
    """The configured scope cannot accept paper-runtime commands."""


class PaperAdmissionUnavailable(RuntimeError):
    """The immutable human admission cannot be resolved or qualified."""


PaperOperatorCommandDatabaseUnavailable = ConsoleDatabaseUnavailable


def _request_digest(request: PaperOperatorCommandRequest, requested_by: str) -> str:
    """Hash the complete command identity used for idempotent replay."""
    payload = {
        "command": request.command,
        "admission_id": request.admission_id,
        "reason": request.reason or "",
        "requested_by": requested_by,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _timestamp(value: Any) -> datetime | None:
    """Normalize a projection timestamp without accepting malformed evidence."""
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _admission_blockers(
    admission: dict[str, Any] | None,
    *,
    scope: ConsoleScope,
    now: datetime,
) -> tuple[str, ...]:
    """Return fail-closed blockers for one exact candidate admission."""
    if admission is None:
        return ("admission_not_found",)
    blockers: list[str] = []
    if str(admission.get("decision") or "") != "approved":
        blockers.append("admission_not_approved")
    if str(admission.get("status") or "") != "approved":
        blockers.append("admission_status_not_approved")
    expires_at = _timestamp(admission.get("expires_at"))
    if expires_at is not None and expires_at <= now:
        blockers.append("admission_expired")
    if admission.get("revoked_at") is not None:
        blockers.append("admission_revoked")
    payload = admission.get("payload")
    if not isinstance(payload, dict):
        blockers.append("admission_payload_unavailable")
        return tuple(blockers)
    broker_scope = payload.get("broker_scope")
    if not isinstance(broker_scope, dict):
        blockers.append("broker_scope_unavailable")
        return tuple(blockers)
    if str(broker_scope.get("environment") or "") != scope.environment.value:
        blockers.append("broker_environment_mismatch")
    configured_scope_id = broker_scope.get("scope_id")
    if configured_scope_id is not None and str(configured_scope_id) != scope.scope_id:
        blockers.append("broker_scope_mismatch")
    configured_account = broker_scope.get("account")
    if configured_account is not None and scope.broker_account_display_label is not None:
        if str(configured_account) != scope.broker_account_display_label:
            blockers.append("broker_account_mismatch")
    return tuple(blockers)


class PaperOperatorCommandService:
    """Validate, persist, and expose operator command audit receipts."""

    def __init__(self, repository: PaperOperatorCommandRepository, scope: ConsoleScope) -> None:
        """Bind the command service to one server-owned Console scope."""
        self._repository = repository
        self._scope = scope

    async def submit(
        self,
        request: PaperOperatorCommandRequest,
        principal: TraderPrincipal,
    ) -> PaperOperatorCommandRecord:
        """Validate human authority and admission before writing a command receipt."""
        self._require_operator(principal)
        self._require_paper_scope()
        now = datetime.now(timezone.utc)
        async with self._repository.session(write=True) as session:
            await session.require_storage()
            admission = await session.admission(request.admission_id)
            blockers = _admission_blockers(admission, scope=self._scope, now=now)
            if blockers:
                raise PaperAdmissionUnavailable(
                    "Paper candidate admission is not eligible: " + ", ".join(blockers)
                )
            return await session.submit(
                request,
                requested_by=principal.principal_id,
                request_digest=_request_digest(request, principal.principal_id),
            )

    async def get(self, command_id: UUID, principal: TraderPrincipal) -> PaperOperatorCommandRecord:
        """Return one audited command to an authorized operator."""
        self._require_operator(principal)
        self._require_paper_scope()
        async with self._repository.session() as session:
            await session.require_storage()
            result = await session.get(command_id)
        if result is None:
            raise PaperOperatorCommandNotFound("Paper operator command not found")
        return result

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        principal: TraderPrincipal,
    ) -> PaperOperatorCommandsResponse:
        """Return bounded audited command history to an authorized operator."""
        self._require_operator(principal)
        self._require_paper_scope()
        async with self._repository.session() as session:
            await session.require_storage()
            rows, total = await session.list(limit, offset)
        return PaperOperatorCommandsResponse(
            items=tuple(rows),
            page=PageInfo(limit=limit, offset=offset, total=total, has_more=offset + limit < total),
        )

    def _require_operator(self, principal: TraderPrincipal) -> None:
        if not is_human_operator_principal(principal.principal_id):
            raise PaperOperatorAuthorityError("Paper runtime commands require a human operator principal")

    def _require_paper_scope(self) -> None:
        if self._scope.environment is not ConsoleEnvironment.PAPER:
            raise PaperOperatorScopeError("Paper runtime commands require a paper Console scope")


__all__ = [
    "PaperAdmissionUnavailable",
    "PaperOperatorAuthorityError",
    "PaperOperatorCommandConflict",
    "PaperOperatorCommandDatabaseUnavailable",
    "PaperOperatorCommandNotFound",
    "PaperOperatorCommandService",
    "PaperOperatorCommandStorageUnavailable",
    "PaperOperatorScopeError",
]
