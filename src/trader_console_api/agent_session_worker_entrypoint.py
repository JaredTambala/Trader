"""Poll and apply human agent-session commands in a dedicated process."""

from __future__ import annotations

import argparse
import asyncio
from contextlib import asynccontextmanager
import os

from trader_agents.application.runtime import runtime_from_environment

from .agent_session_worker import AgentSessionCommandWorker
from .configuration import ConsoleApiSettings
from .repositories.agent_session_worker import AgentSessionWorkerRepository
from .repositories.database import ConsoleDatabase, create_connection_pool


def _positive_env(name: str, default: int, maximum: int) -> int:
    """Read one bounded positive integer from the environment."""
    raw = os.environ.get(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value < 1 or value > maximum:
        raise ValueError(f"{name} must be between 1 and {maximum}")
    return value


@asynccontextmanager
async def _runtime_factory():
    """Open one agent runtime with its configured MCP/checkpoint resources."""
    async with runtime_from_environment(os.environ) as runtime:
        yield runtime


async def _run(*, once: bool, worker_id: str, lease_seconds: int, poll_seconds: int) -> None:
    """Poll Console command storage until drained or interrupted."""
    settings = ConsoleApiSettings.from_environment()
    pool = create_connection_pool(settings)
    database = ConsoleDatabase(pool, settings)
    repository = AgentSessionWorkerRepository(database, settings.scope.scope_id)
    worker = AgentSessionCommandWorker(
        repository=repository,
        runtime_factory=_runtime_factory,
        worker_id=worker_id,
        lease_seconds=lease_seconds,
        max_attempts=_positive_env("TRADER_AGENT_SESSION_MAX_ATTEMPTS", 3, 20),
    )
    await pool.open(wait=True, timeout=settings.pool_open_timeout_seconds)
    try:
        while True:
            claimed = await worker.run_once()
            if once:
                return
            await asyncio.sleep(poll_seconds if not claimed else 0)
    finally:
        await pool.close(timeout=settings.pool_close_timeout_seconds)


def main(arguments: list[str] | None = None) -> None:
    """Run one or continuously poll the agent command queue."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="claim at most one command")
    options = parser.parse_args(arguments)
    worker_id = os.environ.get("TRADER_AGENT_SESSION_WORKER_ID", "agent-session-worker").strip()
    if not worker_id:
        parser.error("TRADER_AGENT_SESSION_WORKER_ID must not be blank")
    try:
        asyncio.run(
            _run(
                once=options.once,
                worker_id=worker_id,
                lease_seconds=_positive_env("TRADER_AGENT_SESSION_LEASE_SECONDS", 60, 86_400),
                poll_seconds=_positive_env("TRADER_AGENT_SESSION_POLL_SECONDS", 2, 300),
            )
        )
    except (OSError, ValueError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
