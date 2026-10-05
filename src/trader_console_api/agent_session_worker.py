"""Apply durable human agent-session intents through the agent runtime boundary."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass
from typing import Any, Protocol

from trader_agents.application.session_commands import apply_session_command
from .contracts import AgentSessionCommandRecord
from .repositories.agent_session_worker import AgentSessionWorkerRepository


class RuntimeFactory(Protocol):
    """Build one isolated runtime context for one claimed command."""

    def __call__(self) -> Any:
        """Return an async context manager yielding a runtime."""


@dataclass(frozen=True)
class AgentSessionCommandWorker:
    """Claim, apply, and durably finish one human agent command."""

    repository: AgentSessionWorkerRepository
    runtime_factory: RuntimeFactory
    worker_id: str
    lease_seconds: int = 60
    max_attempts: int = 3

    async def run_once(self) -> bool:
        """Process one command, returning whether work was claimed.

        A command whose runtime outcome is unknown is marked ``ambiguous``;
        workers never replay an accepted side effect after a lost response.
        """
        async with self.repository.session() as session:
            command = await session.claim_next(
                worker_id=self.worker_id,
                lease_seconds=self.lease_seconds,
                max_attempts=self.max_attempts,
            )
            if command is None:
                return False
        try:
            async with self.repository.session() as session:
                research_session = await session.load_session(command.session_id)
            if research_session is None:
                await self._finish(
                    command,
                    status="rejected",
                    code="session_not_found",
                    message="Agent session was not found.",
                )
                return True
            if research_session.operator_id != command.requested_by:
                await self._finish(
                    command,
                    status="rejected",
                    code="session_owner_mismatch",
                    message="Command owner does not match the session.",
                )
                return True
            lease_lost = False

            async def renew_lease() -> None:
                """Keep a long-running runtime command owned by this worker."""
                nonlocal lease_lost
                interval = max(1.0, self.lease_seconds / 3)
                while True:
                    await asyncio.sleep(interval)
                    try:
                        async with self.repository.session() as heartbeat_session:
                            if not await heartbeat_session.heartbeat(
                                _command_uuid(command),
                                worker_id=self.worker_id,
                                lease_seconds=self.lease_seconds,
                            ):
                                lease_lost = True
                                return
                    except asyncio.CancelledError:
                        raise
                    except Exception:
                        lease_lost = True
                        return

            heartbeat_task = asyncio.create_task(renew_lease())
            try:
                async with self.runtime_factory() as runtime:
                    state = await apply_session_command(
                        runtime,
                        research_session,
                        command=command.command,
                        operator_id=command.requested_by,
                        reason=command.reason,
                        operator_answer=command.operator_answer,
                        approved=command.approved,
                    )
            finally:
                heartbeat_task.cancel()
                with suppress(asyncio.CancelledError):
                    await heartbeat_task
            if lease_lost:
                raise RuntimeError("agent command lease was lost during runtime execution")
            checkpoint_sequence = _checkpoint_sequence(state)
            async with self.repository.session() as session:
                await session.upsert_public_state(
                    research_session,
                    state,
                    checkpoint_sequence=checkpoint_sequence,
                )
                finished = await session.finish(
                    _command_uuid(command),
                    worker_id=self.worker_id,
                    status="completed",
                    outcome_code="runtime_applied",
                    outcome_message="The runtime applied the human command.",
                )
            if not finished:
                raise RuntimeError("agent command lease was lost before completion")
        except (ValueError, TypeError):
            await self._finish(
                command,
                status="rejected",
                code="command_rejected",
                message="The command failed its runtime authority or lifecycle checks.",
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            await self._finish(
                command,
                status="ambiguous",
                code="runtime_outcome_unknown",
                message="The runtime outcome was not observed; inspect the session before further action.",
            )
        return True

    async def _finish(
        self,
        command: AgentSessionCommandRecord,
        *,
        status: str,
        code: str,
        message: str,
    ) -> None:
        """Finish a claimed command only while retaining worker ownership."""
        async with self.repository.session() as session:
            await session.finish(
                _command_uuid(command),
                worker_id=self.worker_id,
                status=status,
                outcome_code=code,
                outcome_message=message,
            )


def _command_uuid(command: AgentSessionCommandRecord) -> Any:
    """Normalize the transport command identity for repository updates."""
    from uuid import UUID

    return UUID(command.command_id)


def _checkpoint_sequence(state: Mapping[str, Any]) -> int | None:
    """Map the runtime's next sequence to the last saved checkpoint."""
    value = state.get("next_sequence")
    if isinstance(value, int) and not isinstance(value, bool) and value > 1:
        return value - 1
    return None


__all__ = ["AgentSessionCommandWorker", "RuntimeFactory"]
