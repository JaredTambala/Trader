"""Agent-owned lifecycle command boundary for the human Console worker."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from trader_research.governance import ResearchSession

from trader_agents.contracts.domain import (
    OperatorCancellation,
    OperatorInterruption,
    OperatorResponse,
)


class SessionCommandRuntime(Protocol):
    """Runtime methods admitted at the Console command boundary."""

    async def inspect(self, session: ResearchSession) -> dict[str, Any]:
        """Return the redacted checkpoint projection."""

    async def interrupt(
        self,
        session: ResearchSession,
        interruption: OperatorInterruption,
    ) -> Any:
        """Pause at a checkpointed operator boundary."""

    async def resume(self, session: ResearchSession, response: OperatorResponse) -> Any:
        """Resume from a pending operator boundary."""

    async def cancel(self, session: ResearchSession, cancellation: OperatorCancellation) -> Any:
        """Cancel one owned checkpointed session."""


async def apply_session_command(
    runtime: SessionCommandRuntime,
    session: ResearchSession,
    *,
    command: str,
    operator_id: str,
    reason: str | None,
    operator_answer: str | None,
    approved: bool | None,
) -> dict[str, Any]:
    """Apply one validated human command and return a fresh public state.

    The worker owns persistence and retries; this boundary owns only the
    runtime lifecycle operation. It never receives prompts, raw model output,
    credentials, or a database connection.
    """
    if operator_id != session.operator_id:
        raise ValueError("session command operator does not own the session")
    if command == "inspect":
        return await runtime.inspect(session)
    if command == "interrupt":
        await runtime.interrupt(
            session,
            OperatorInterruption(
                operator_id=operator_id,
                reason=(reason or "Operator requested a review pause."),
            ),
        )
    elif command == "resume":
        if approved is None:
            raise ValueError("resume requires an explicit approved value")
        if not operator_answer or not operator_answer.strip():
            raise ValueError("resume requires an operator answer")
        await runtime.resume(
            session,
            OperatorResponse(
                approved=approved,
                answer=operator_answer,
                operator_id=operator_id,
            ),
        )
    elif command == "cancel":
        await runtime.cancel(
            session,
            OperatorCancellation(
                operator_id=operator_id,
                reason=(reason or "Operator requested cancellation."),
            ),
        )
    else:
        raise ValueError(f"unsupported agent session command: {command}")
    state = await runtime.inspect(session)
    if not isinstance(state, Mapping):
        raise RuntimeError("agent runtime returned an invalid public state")
    return dict(state)


__all__ = ["SessionCommandRuntime", "apply_session_command"]
