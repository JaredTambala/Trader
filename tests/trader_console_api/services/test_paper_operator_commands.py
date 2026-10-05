"""Application contracts for authorized paper operator commands.

Subject: Admission validation, human authority, idempotent request handoff, and outcome visibility.
Level: In-process application service.
Collaborators: Repository session double; no database, broker, or HTTP server.
Guarantees: Only approved matching human requests reach persistence and every command is queued as an audit receipt.
Non-goals: PostgreSQL schema installation, runtime command consumption, and browser rendering.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from trader_console_api.contracts import (
    BrokerAccountBinding,
    ConsoleEnvironment,
    ConsoleScope,
    PaperOperatorCommandRecord,
    PaperOperatorCommandRequest,
    TraderPrincipal,
)
from trader_console_api.services.paper_operator_commands import (
    PaperAdmissionUnavailable,
    PaperOperatorAuthorityError,
    PaperOperatorCommandService,
)


def _scope() -> ConsoleScope:
    return ConsoleScope(
        scope_id="paper-primary",
        display_name="Paper",
        environment=ConsoleEnvironment.PAPER,
        broker_account_display_label="paper-account-1",
        broker_account_binding=BrokerAccountBinding.CONFIGURED,
    )


def _request(**overrides: object) -> PaperOperatorCommandRequest:
    values: dict[str, object] = {
        "command": "pause",
        "admission_id": "admission-1",
        "idempotency_key": "request-1",
        "reason": "test pause",
    }
    values.update(overrides)
    return PaperOperatorCommandRequest.model_validate(values)


def _record() -> PaperOperatorCommandRecord:
    return PaperOperatorCommandRecord(
        command_id=str(uuid4()),
        scope_id="paper-primary",
        command="pause",
        admission_id="admission-1",
        idempotency_key="request-1",
        requested_by="human:test@example.test",
        status="requested",
        reason="test pause",
        requested_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


class _Session:
    def __init__(self, admission: dict[str, object] | None) -> None:
        self.admission_value = admission
        self.submitted: tuple[PaperOperatorCommandRequest, str] | None = None

    async def require_storage(self) -> None:
        """Storage is available in the service fixture."""

    async def admission(self, _admission_id: str) -> dict[str, object] | None:
        """Return the configured admission projection."""
        return self.admission_value

    async def submit(self, request: PaperOperatorCommandRequest, *, requested_by: str, request_digest: str) -> PaperOperatorCommandRecord:
        """Capture the normalized handoff and return a queued receipt."""
        self.submitted = (request, requested_by)
        assert len(request_digest) == 64
        return _record()


class _Repository:
    def __init__(self, admission: dict[str, object] | None) -> None:
        self.session_value = _Session(admission)

    @asynccontextmanager
    async def session(self, *, write: bool = False):
        """Yield the service session fixture."""
        assert write
        yield self.session_value


def _admission(**broker_scope: object) -> dict[str, object]:
    return {
        "decision": "approved",
        "status": "approved",
        "expires_at": datetime.now(timezone.utc) + timedelta(days=1),
        "revoked_at": None,
        "payload": {
            "broker_scope": {
                "environment": "paper",
                "scope_id": "paper-primary",
                "account": "paper-account-1",
                **broker_scope,
            }
        },
    }


def test_submit_requires_human_operator_and_matching_admission() -> None:
    """Reject an agent identity before any command can reach persistence."""
    repository = _Repository(_admission())
    service = PaperOperatorCommandService(repository, _scope())
    with pytest.raises(PaperOperatorAuthorityError):
        asyncio.run(service.submit(_request(), TraderPrincipal(principal_id="agent:research")))
    assert repository.session_value.submitted is None


def test_submit_persists_only_after_approved_scope_validation() -> None:
    """Pass the complete admission and server scope into one idempotent handoff."""
    repository = _Repository(_admission())
    service = PaperOperatorCommandService(repository, _scope())
    result = asyncio.run(service.submit(_request(), TraderPrincipal(principal_id="human:test@example.test")))
    assert result.status == "requested"
    assert repository.session_value.submitted is not None
    assert repository.session_value.submitted[1] == "human:test@example.test"


def test_submit_rejects_expired_or_mismatched_admission() -> None:
    """Keep stale evidence and broker scope drift fail-closed at the command boundary."""
    expired = _admission()
    expired["expires_at"] = datetime.now(timezone.utc) - timedelta(seconds=1)
    with pytest.raises(PaperAdmissionUnavailable, match="admission_expired"):
        asyncio.run(PaperOperatorCommandService(_Repository(expired), _scope()).submit(_request(), TraderPrincipal(principal_id="human:test")))

    mismatched = _admission(account="other-account")
    with pytest.raises(PaperAdmissionUnavailable, match="broker_account_mismatch"):
        asyncio.run(PaperOperatorCommandService(_Repository(mismatched), _scope()).submit(_request(), TraderPrincipal(principal_id="human:test")))
