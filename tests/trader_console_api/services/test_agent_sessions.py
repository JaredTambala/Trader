"""Application contracts for the Console agent-session workspace.

Subject: Typed redacted session projection and human command authority.
Level: In-process application service.
Collaborators: Repository and transaction doubles; no SQL, runtime, MCP, or browser.
Guarantees: Public evidence is bounded, private payloads are absent, session ownership
is enforced, and command intents retain explicit operator identity.
Non-goals: Applying commands in the agent runtime, model qualification, and UI layout.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import datetime, timezone
from typing import cast
from uuid import UUID

import pytest

from trader_console_api.contracts import (
    AgentSessionCommandRecord,
    AgentSessionCommandRequest,
    TraderPrincipal,
)
from trader_console_api.repositories.agent_sessions import (
    AgentSessionRepository,
    AgentSessionSource,
)
from trader_console_api.repositories.agent_sessions import AgentSessionCommandConflict
from trader_console_api.repositories.agent_sessions_schema import (
    AgentSessionStorageUnavailable,
)
from trader_console_api.services.agent_sessions import (
    AgentSessionAuthorityError,
    AgentSessionService,
    _build_projection,
)


@pytest.mark.parametrize(
    "payload",
    [
        {
            "command": "resume",
            "idempotency_key": "resume-missing-approval",
            "operator_answer": "continue",
        },
        {
            "command": "resume",
            "idempotency_key": "resume-missing-answer",
            "approved": True,
        },
        {
            "command": "resume",
            "idempotency_key": "resume-blank-answer",
            "approved": False,
            "operator_answer": "  ",
        },
        {
            "command": "interrupt",
            "idempotency_key": "interrupt-approval",
            "approved": True,
        },
    ],
)
def test_resume_contract_requires_an_explicit_answer_and_decision(
    payload: dict[str, object],
) -> None:
    """Resume requests require a bounded human answer and explicit approval decision."""
    with pytest.raises(ValueError):
        AgentSessionCommandRequest.model_validate(payload)


def test_resume_contract_accepts_an_explicit_decline() -> None:
    """A human may explicitly decline a resume while still supplying the answer envelope."""
    request = AgentSessionCommandRequest.model_validate(
        {
            "command": "resume",
            "idempotency_key": "resume-decline",
            "operator_answer": "Stop and review the evidence.",
            "approved": False,
        }
    )
    assert request.approved is False


def _source() -> AgentSessionSource:
    """Build one public session source containing deliberately unsafe fields."""
    return AgentSessionSource(
        session={
            "session_id": "session-1",
            "operator_id": "human:jared",
            "status": "active",
            "payload": {
                "session_id": "session-1",
                "session_digest": "a" * 64,
                "operator_id": "human:jared",
                "objective": "Investigate a bounded market question.",
                "success_definition": "Return inspectable evidence.",
                "model_profile_id": "model-v1",
                "agent_program_ids": ["coordinator-v1", "data-v1"],
                "tool_catalog_id": "catalogue-v1",
                "scope_envelope": {
                    "data_scope": {
                        "scope_id": "scope-1",
                        "asset_class": "stock",
                        "symbols": ["AAPL"],
                        "timeframe": "1d",
                        "start": "2024-01-01T00:00:00Z",
                        "end": "2024-02-01T00:00:00Z",
                        "prompt": "must never be projected",
                    },
                    "credentials": "must never be projected",
                },
                "budget": {
                    "max_model_calls": 4,
                    "max_tool_calls": 8,
                    "max_tokens": 1000,
                    "max_duration_seconds": 60,
                    "max_mutations": 1,
                    "max_revisions": 1,
                    "concurrency_limit": 2,
                },
                "metadata": {
                    "agenda_summary": "Inspect data before proposing a strategy.",
                    "prompt": "private prompt",
                    "completion": "private completion",
                    "raw_payload": {"secret": "private"},
                },
            },
        },
        receipts=(
            {
                "payload": {
                    "receipt_id": "receipt-1",
                    "session_id": "session-1",
                    "branch_id": "branch-1",
                    "sequence": 1,
                    "actor": "Research Coordinator",
                    "program_id": "coordinator-v1",
                    "model_profile_id": "model-v1",
                    "action": "ask_operator",
                    "status": "awaiting_operator",
                    "summary": "Operator clarification is required.",
                    "evidence_refs": [
                        {
                            "artifact_type": "dataset_manifest",
                            "artifact_id": "manifest-1",
                            "domain_owner": "Data",
                            "uri": "research://postgres/dataset_manifest/manifest-1",
                            "metadata": {"source_hash": "b" * 64, "secret": "drop"},
                        }
                    ],
                    "budget_used": {
                        "model_calls": 1,
                        "tool_calls": 1,
                        "tokens": 42,
                        "duration_ms": 100,
                        "mutations": 0,
                        "revisions": 0,
                    },
                    "blockers": [
                        {
                            "code": "operator_input",
                            "message": "Choose the evaluation window.",
                            "details": {"prompt": "drop"},
                        }
                    ],
                    "next_actions": ["resume"],
                    "metadata": {"role": "research_coordinator", "completion": "drop"},
                }
            },
        ),
        commands=(),
    )


def test_projection_is_typed_and_redacted() -> None:
    """The workspace retains scope and evidence identity while excluding private payloads."""
    projection = _build_projection(_source())
    rendered = str(projection.model_dump(mode="json"))
    assert projection.session_id == "session-1"
    assert projection.scope_summary["symbols"] == ["AAPL"]
    assert projection.pending_interrupt is not None
    assert projection.events[0].event_type == "ask_operator"
    assert projection.evidence_refs[0].source_hash == "b" * 64
    assert "private prompt" not in rendered
    assert "private completion" not in rendered
    assert "credentials" not in rendered
    assert "raw_payload" not in rendered
    assert "secret" not in rendered


def test_projection_retains_specialist_outcomes_handoffs_and_exact_revisions() -> None:
    """Specialist branches expose bounded outcome states and pinned artifact identity."""
    statuses = ("complete", "partial", "failed", "blocked", "stale", "unavailable")
    receipts = []
    for sequence, specialist_status in enumerate(statuses, start=1):
        artifact_status = {
            "complete": "available",
            "partial": "stale",
            "failed": "unavailable",
            "blocked": "incompatible",
            "stale": "stale",
            "unavailable": "unavailable",
        }[specialist_status]
        receipts.append(
            {
                "payload": {
                    "receipt_id": f"receipt-{sequence}",
                    "session_id": "session-1",
                    "branch_id": f"branch-{sequence}",
                    "sequence": sequence,
                    "actor": "Data Specialist",
                    "program_id": "data-v1",
                    "model_profile_id": "model-v1",
                    "action": "handoff",
                    "status": "completed" if specialist_status == "complete" else "running",
                    "specialist_status": specialist_status,
                    "summary": f"Specialist branch {specialist_status}.",
                    "delegation_id": f"delegation-{sequence}",
                    "attempt_id": f"attempt-{sequence}",
                    "evidence_refs": [
                        {
                            "artifact_type": "dataset_manifest",
                            "artifact_id": f"manifest-{sequence}",
                            "domain_owner": "Data",
                            "uri": f"research://postgres/dataset_manifest/manifest-{sequence}",
                            "metadata": {
                                "source_hash": "b" * 64,
                                "revision": sequence,
                                "status": artifact_status,
                            },
                        }
                    ],
                    "blockers": (
                        [{"code": "evidence", "message": "Evidence needs review."}]
                        if specialist_status in {"partial", "failed", "blocked"}
                        else []
                    ),
                    "next_actions": ["review"],
                    "metadata": {
                        "role": "data_research",
                        "owner": "Data Specialist",
                        "handoff_digest": "c" * 64,
                    },
                }
            }
        )

    projection = _build_projection(replace(_source(), receipts=tuple(receipts)))

    assert [item.specialist_status for item in projection.delegations] == list(statuses)
    assert projection.delegations[0].handoff is not None
    assert projection.delegations[0].handoff.digest == "c" * 64
    assert projection.delegations[0].handoff.artifact_refs[0].revision == 1
    assert projection.delegations[4].handoff.artifact_refs[0].status == "stale"
    assert projection.delegations[5].status == "blocked"


def test_runtime_public_state_drives_workspace_progress() -> None:
    """Use a fresh runtime inspection snapshot for agenda, budget, and interrupt state."""
    source = replace(
        _source(),
        public_state={
            "session_id": "session-1",
            "session_digest": "a" * 64,
            "operator_id": "human:jared",
            "public_state": {
                "status": "awaiting_operator",
                "next_sequence": 4,
                "agenda": {"objective_summary": "Compare the qualified data slice."},
                "budget_usage": {
                    "model_calls": 2,
                    "tool_calls": 3,
                    "input_tokens": 10,
                    "output_tokens": 32,
                    "duration_ms": 120,
                    "mutations": 0,
                    "revisions": 0,
                },
                "pending_interrupt": {
                    "kind": "operator_clarification_required",
                    "question": "Choose the evaluation window.",
                    "requested_action": "answer_or_decline",
                    "resume_schema": {"type": "object"},
                },
                "delegations": [
                    {
                        "delegation_id": "delegation-1",
                        "attempt_id": "attempt-1",
                        "branch_id": "branch-data",
                        "task": {
                            "role": "data_research",
                            "question": "Qualify the exact data window.",
                        },
                    }
                ],
            },
        },
    )
    projection = _build_projection(source)
    assert projection.status == "awaiting_operator"
    assert projection.agenda_summary == "Compare the qualified data slice."
    assert projection.checkpoint_sequence == 3
    assert projection.budget_used.tokens == 42
    assert projection.delegations[0].role == "data_research"
    assert projection.pending_interrupt is not None


def test_terminal_receipt_overrides_an_earlier_operator_interrupt() -> None:
    """A later terminal transition closes a previously pending operator request."""
    source = _source()
    source = replace(
        source,
        receipts=source.receipts
        + (
            {
                "payload": {
                    "receipt_id": "receipt-2",
                    "session_id": "session-1",
                    "branch_id": "branch-1",
                    "sequence": 2,
                    "actor": "Research Coordinator",
                    "program_id": "coordinator-v1",
                    "model_profile_id": "model-v1",
                    "action": "conclude",
                    "status": "terminal",
                    "summary": "Evidence is complete.",
                    "evidence_refs": [],
                    "budget_used": {
                        "model_calls": 2,
                        "tool_calls": 2,
                        "tokens": 84,
                        "duration_ms": 200,
                        "mutations": 0,
                        "revisions": 0,
                    },
                    "blockers": [],
                    "next_actions": [],
                    "metadata": {"role": "research_coordinator"},
                }
            },
        ),
    )
    projection = _build_projection(source)
    assert projection.status == "terminal"
    assert projection.pending_interrupt is None


def test_specialist_completion_does_not_close_the_human_session() -> None:
    """A terminal specialist branch remains progress until the coordinator concludes."""
    source = _inspected_source("running")
    specialist_receipt = dict(source.receipts[0])
    specialist_receipt["payload"] = {
        **specialist_receipt["payload"],
        "receipt_id": "specialist-complete",
        "branch_id": "branch-data",
        "actor": "data_research",
        "status": "completed",
        "metadata": {"role": "data_research"},
    }
    projection = _build_projection(replace(source, receipts=(specialist_receipt,)))
    assert projection.terminal_decision is None
    assert projection.status == "running"
    assert projection.available_commands == ("inspect", "interrupt", "cancel")


def test_public_state_identity_and_counters_fail_closed() -> None:
    """A stale or malformed runtime snapshot cannot alter the human projection."""
    source = replace(
        _source(),
        public_state={
            "session_id": "another-session",
            "session_digest": "a" * 64,
            "operator_id": "human:jared",
            "public_state": {"budget_usage": {"model_calls": "not-a-counter"}},
        },
    )
    with pytest.raises(AgentSessionStorageUnavailable):
        _build_projection(source)


def _inspected_source(status: str, *, pending: bool = False) -> AgentSessionSource:
    """Attach an exact public runtime inspection to the source fixture."""
    return replace(
        _source(),
        public_state={
            "session_id": "session-1",
            "session_digest": "a" * 64,
            "operator_id": "human:jared",
            "public_state": {
                "status": status,
                "next_sequence": 2,
                "pending_interrupt": (
                    {
                        "kind": "operator_input",
                        "question": "Choose a window.",
                        "requested_action": "answer",
                    }
                    if pending
                    else None
                ),
            },
        },
    )


@pytest.mark.parametrize(
    ("status", "pending", "expected"),
    [
        ("running", False, ("inspect", "interrupt", "cancel")),
        ("awaiting_operator", True, ("inspect", "resume", "cancel")),
        ("completed", False, ("inspect",)),
        ("blocked", False, ("inspect",)),
    ],
)
def test_public_state_sets_exact_human_command_authority(
    status: str, pending: bool, expected: tuple[str, ...]
) -> None:
    """The Console exposes only commands justified by the inspected checkpoint."""
    projection = _build_projection(_inspected_source(status, pending=pending))
    assert projection.available_commands == expected


def test_uninspected_or_incompatible_identity_fails_closed() -> None:
    """A missing inspection limits authority and mismatched canonical identities cannot render."""
    source = _source()
    assert _build_projection(source).available_commands == ("inspect",)
    with pytest.raises(AgentSessionStorageUnavailable, match="row identity"):
        _build_projection(
            replace(source, session={**source.session, "session_id": "other"})
        )
    receipt = dict(source.receipts[0])
    receipt["payload"] = {**receipt["payload"], "model_profile_id": "different-model"}
    with pytest.raises(AgentSessionStorageUnavailable, match="receipt identity"):
        _build_projection(replace(source, receipts=(receipt,)))
    with pytest.raises(AgentSessionStorageUnavailable, match="status"):
        _build_projection(_inspected_source("unknown-state"))
    source = replace(
        source,
        public_state={
            "session_id": "session-1",
            "session_digest": "a" * 64,
            "operator_id": "human:jared",
            "public_state": {"budget_usage": {"model_calls": "not-a-counter"}},
        },
    )
    with pytest.raises(AgentSessionStorageUnavailable):
        _build_projection(source)


class _Session:
    def __init__(self, source: AgentSessionSource | None = None) -> None:
        self.source = source or _source()

    async def require_storage(self) -> None:
        """Storage is available in the service fixture."""

    async def get(self, _session_id: str) -> AgentSessionSource:
        """Return the exact synthetic source."""
        return self.source

    async def create_command(self, session_id, request, *, requested_by):
        """Return one durable command receipt with the bound operator."""
        return AgentSessionCommandRecord(
            command_id="00000000-0000-0000-0000-000000000001",
            session_id=session_id,
            command=request.command,
            idempotency_key=request.idempotency_key,
            requested_by=requested_by,
            status="requested",
            reason=request.reason,
            operator_answer=request.operator_answer,
            requested_at=datetime.now(timezone.utc),
        )


class _Repository:
    def __init__(self, source: AgentSessionSource | None = None) -> None:
        self.source = source or _source()

    @asynccontextmanager
    async def session(self, *, write: bool = False):
        """Yield a source or command transaction double."""
        yield _Session(self.source)


def test_non_human_and_non_owner_cannot_read_or_command() -> None:
    """Agent identities and other humans fail closed before any mutation."""
    service = AgentSessionService(cast(AgentSessionRepository, _Repository()))
    with pytest.raises(AgentSessionAuthorityError):
        import asyncio

        asyncio.run(
            service.get("session-1", TraderPrincipal(principal_id="agent:coordinator"))
        )
    with pytest.raises(AgentSessionAuthorityError):
        import asyncio

        asyncio.run(
            service.get("session-1", TraderPrincipal(principal_id="human:other"))
        )


def test_human_owner_can_submit_an_interrupt_intent() -> None:
    """An owner command preserves the exact idempotency and authority fields."""
    service = AgentSessionService(
        cast(AgentSessionRepository, _Repository(_inspected_source("running")))
    )
    request = AgentSessionCommandRequest(
        command="interrupt",
        idempotency_key="intent-1",
        reason="Review the evidence before continuing.",
    )
    import asyncio

    result = asyncio.run(
        service.command(
            "session-1", request, TraderPrincipal(principal_id="human:jared")
        )
    )
    assert result.command == "interrupt"
    assert result.requested_by == "human:jared"
    UUID(result.command_id)


@pytest.mark.parametrize(
    ("status", "pending", "command"),
    [
        ("running", False, "inspect"),
        ("running", False, "interrupt"),
        ("running", False, "cancel"),
        ("awaiting_operator", True, "resume"),
        ("awaiting_operator", True, "cancel"),
        ("completed", False, "inspect"),
    ],
)
def test_owner_lifecycle_commands_follow_inspected_authority(
    status: str, pending: bool, command: str
) -> None:
    """Each admitted command persists a receipt bound to the owning human."""
    import asyncio

    service = AgentSessionService(
        cast(
            AgentSessionRepository,
            _Repository(_inspected_source(status, pending=pending)),
        )
    )
    request = AgentSessionCommandRequest.model_validate(
        {
            "command": command,
            "idempotency_key": f"intent-{status}-{command}",
            **(
                {"approved": False, "operator_answer": "Stop and review."}
                if command == "resume"
                else {}
            ),
        }
    )
    result = asyncio.run(
        service.command(
            "session-1", request, TraderPrincipal(principal_id="human:jared")
        )
    )
    assert result.command == command
    assert result.requested_by == "human:jared"


def test_invalid_state_and_uninspected_commands_are_rejected_before_persistence() -> (
    None
):
    """Resume, pause, and cancellation intents fail closed outside their runtime states."""
    import asyncio

    principal = TraderPrincipal(principal_id="human:jared")
    for source, command in (
        (_source(), "interrupt"),
        (_inspected_source("running"), "resume"),
        (_inspected_source("awaiting_operator", pending=True), "interrupt"),
        (_inspected_source("completed"), "cancel"),
    ):
        service = AgentSessionService(cast(AgentSessionRepository, _Repository(source)))
        request = AgentSessionCommandRequest(
            command=command,
            idempotency_key=f"invalid-{command}",
            operator_answer="reviewed" if command == "resume" else None,
            approved=True if command == "resume" else None,
        )
        with pytest.raises(AgentSessionCommandConflict):
            asyncio.run(service.command("session-1", request, principal))
