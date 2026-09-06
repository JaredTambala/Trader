"""FastAPI composition root for the Trader Console API."""

from __future__ import annotations

from argparse import ArgumentParser
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Protocol

from fastapi import FastAPI, Request
import psycopg
from psycopg_pool import PoolTimeout

from .configuration import ConsoleApiSettings
from .contracts import TraderPrincipal
from .repositories import (
    ConsoleDatabase,
    ConsoleDatabaseUnavailable,
    PoolFactory,
    SchemaCompatibilityRepository,
    create_connection_pool,
)
from .routers import health_router
from .services import HealthService


class AuthenticationProvider(Protocol):
    """Extension point for a deployment-owned Trader principal provider."""

    async def authenticate(self, request: Request) -> TraderPrincipal:
        """Resolve the Trader principal represented by one request."""
        ...


class ConsoleStartupError(RuntimeError):
    """Raised when the API cannot establish its startup dependencies."""


def create_app(
    settings: ConsoleApiSettings | None = None,
    *,
    pool_factory: PoolFactory = create_connection_pool,
    authentication_provider: AuthenticationProvider | None = None,
) -> FastAPI:
    """Create the Trader Console API for one configured scope.

    Args:
        settings: Explicit settings, or ``None`` to load the local environment
            baseline.
        pool_factory: Injectable database connection/authentication composition.
            The default consumes the configured DSN; a deployment can provide a
            secret-manager, managed-identity, or proxy-backed factory later.
        authentication_provider: Optional request-principal extension point.
            This scaffold stores but does not invoke it because health routes do
            not make authorization claims and scoped data routes are later work.

    Returns:
        A FastAPI application whose lifespan owns exactly one bounded pool.
    """
    configured_settings = settings or ConsoleApiSettings.from_environment()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        pool = pool_factory(configured_settings)
        database = ConsoleDatabase(pool, configured_settings)
        compatibility_repository = SchemaCompatibilityRepository(database)
        health_service = HealthService(
            scope_id=configured_settings.scope.scope_id,
            compatibility_repository=compatibility_repository,
        )
        opened = False
        app.state.database = database
        app.state.health_service = health_service
        try:
            try:
                await pool.open(
                    wait=True,
                    timeout=configured_settings.pool_open_timeout_seconds,
                )
                opened = True
            except (psycopg.Error, PoolTimeout) as exc:
                raise ConsoleStartupError(
                    "Console API could not open its database connection pool"
                ) from exc
            try:
                await health_service.require_startup_readiness()
            except ConsoleDatabaseUnavailable as exc:
                raise ConsoleStartupError(
                    "Console API could not inspect database compatibility"
                ) from exc
            yield
        finally:
            if opened:
                await pool.close(
                    timeout=configured_settings.pool_close_timeout_seconds
                )

    app = FastAPI(
        title="Trader Console API",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.scope = configured_settings.scope
    app.state.authentication_provider = authentication_provider
    app.include_router(health_router)
    return app


def main(arguments: list[str] | None = None) -> None:
    """Run the Console API using environment-owned configuration."""
    parser = ArgumentParser(description="Run the Trader Console API.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8001)
    parsed = parser.parse_args(arguments)

    import uvicorn

    uvicorn.run(
        "trader_console_api.application:create_app",
        factory=True,
        host=parsed.host,
        port=parsed.port,
        reload=False,
    )


__all__ = [
    "AuthenticationProvider",
    "ConsoleStartupError",
    "create_app",
    "main",
]
