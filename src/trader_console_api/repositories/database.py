"""Pooled PostgreSQL access for Console repositories."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any, Protocol

import psycopg
from psycopg_pool import AsyncConnectionPool, PoolTimeout

from ..configuration import ConsoleApiSettings


class ConsoleConnectionPool(Protocol):
    """Minimal pool behavior required by the API lifespan and repositories."""

    async def open(self, wait: bool = False, timeout: float = 30.0) -> None:
        """Open the bounded pool and optionally wait for its minimum size."""
        ...

    async def close(self, timeout: float = 5.0) -> None:
        """Close the pool and its connections."""
        ...

    def connection(self, timeout: float | None = None) -> Any:
        """Return an asynchronous connection context manager."""
        ...


PoolFactory = Callable[[ConsoleApiSettings], ConsoleConnectionPool]


class ConsoleDatabaseUnavailable(RuntimeError):
    """Raised when a repository cannot complete database work."""


def create_connection_pool(settings: ConsoleApiSettings) -> AsyncConnectionPool:
    """Create the unopened default Psycopg pool for one Console process.

    Args:
        settings: Normalized server-owned process settings.

    Returns:
        An unopened asynchronous pool. The application lifespan owns opening
        and closing it.
    """
    return AsyncConnectionPool(
        conninfo=settings.database_url.get_secret_value(),
        min_size=settings.pool_min_size,
        max_size=settings.pool_max_size,
        open=False,
        timeout=settings.pool_timeout_seconds,
        name="trader-console-api",
        kwargs={"application_name": "trader-console-api"},
    )


class ConsoleDatabase:
    """Provide transaction-scoped database access to repositories."""

    def __init__(
        self,
        pool: ConsoleConnectionPool,
        settings: ConsoleApiSettings,
    ) -> None:
        """Bind the process pool to its transaction and timeout policy."""
        self._pool = pool
        self._settings = settings

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[Any]:
        """Yield one connection inside the current bounded transaction policy.

        Query repositories use PostgreSQL ``READ ONLY`` enforcement. Command
        repositories use :meth:`command_transaction` with their explicit write
        and isolation policy.

        Raises:
            ConsoleDatabaseUnavailable: If Psycopg cannot acquire or use a
                database connection.
        """
        async with self._transaction(command=False) as connection:
            yield connection

    @asynccontextmanager
    async def command_transaction(self) -> AsyncIterator[Any]:
        """Commit one bounded application command, rolling back on any failure.

        Comparison definitions are the only current command owner. Repeatable
        reads keep membership validation and its write on the same evidence view.
        """
        async with self._transaction(command=True) as connection:
            yield connection

    @asynccontextmanager
    async def _transaction(self, *, command: bool) -> AsyncIterator[Any]:
        try:
            async with self._pool.connection(
                timeout=self._settings.pool_timeout_seconds
            ) as connection:
                async with connection.transaction():
                    await connection.execute(
                        "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ WRITE"
                        if command else "SET TRANSACTION READ ONLY"
                    )
                    await connection.execute(
                        "SELECT set_config('statement_timeout', %s, true)",
                        [str(self._settings.statement_timeout_ms)],
                    )
                    yield connection
        except (psycopg.Error, PoolTimeout) as exc:
            raise ConsoleDatabaseUnavailable(
                "Console database transaction is unavailable"
            ) from exc
