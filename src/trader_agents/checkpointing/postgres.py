"""Postgres adapter for LangGraph operational checkpoints."""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
import os

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver


CHECKPOINT_DSN_ENV = "TRADER_AGENTS_CHECKPOINT_DSN"


class CheckpointConfigurationError(ValueError):
    """Raised when the operational checkpointer is not configured safely."""


def checkpoint_dsn_from_env(
    environ: Mapping[str, str] | None = None,
) -> str:
    """Load the explicit checkpoint DSN without falling back to artifact storage."""
    values = os.environ if environ is None else environ
    dsn = str(values.get(CHECKPOINT_DSN_ENV) or "").strip()
    if not dsn:
        raise CheckpointConfigurationError(
            f"{CHECKPOINT_DSN_ENV} is required for Postgres agent checkpoints"
        )
    return dsn


@asynccontextmanager
async def open_postgres_checkpointer(
    *,
    dsn: str | None = None,
    environ: Mapping[str, str] | None = None,
    setup: bool = False,
) -> AsyncIterator[AsyncPostgresSaver]:
    """Open the maintained asynchronous LangGraph Postgres saver.

    Args:
        dsn: Explicit Postgres connection string. When omitted, the dedicated
            checkpoint environment variable is required.
        environ: Optional environment mapping used only when `dsn` is omitted.
        setup: Whether to run the checkpointer's idempotent schema migrations.

    Yields:
        Connected asynchronous Postgres checkpointer.
    """
    resolved_dsn = str(dsn or "").strip() or checkpoint_dsn_from_env(environ)
    async with AsyncPostgresSaver.from_conn_string(resolved_dsn) as saver:
        if setup:
            await saver.setup()
        yield saver


def checkpoint_runtime_summary(
    environ: Mapping[str, str] | None = None,
) -> dict[str, object]:
    """Return credential-free operational checkpointer configuration."""
    values = os.environ if environ is None else environ
    return {
        "backend": "postgres",
        "configured": bool(str(values.get(CHECKPOINT_DSN_ENV) or "").strip()),
        "persistent": True,
        "canonical_research_evidence": False,
    }
