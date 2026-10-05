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
    ConsoleResourceRepository,
    SchemaCompatibilityRepository,
    create_connection_pool,
)
from .routers import (
    backtest_definition_router,
    backtest_execution_router,
    catalogue_router,
    context_router,
    agent_session_router,
    health_router,
    resource_router,
    saved_data_scope_router,
    data_scope_comparison_router,
    paper_runtime_router,
    paper_operator_command_router,
    next_research_decision_router,
)
from .services.catalogue import (
    CatalogueService,
    ImplementationLineageResolver,
    PreflightService,
)
from .services.backtest_definitions import BacktestDefinitionService
from .services.backtest_executions import BacktestExecutionService
from .services import ContextService, HealthService, ResourceService
from .services.saved_data_scopes import SavedDataScopeService
from .services.paper_runtime import PaperRuntimeService
from .repositories.paper_runtime import PaperRuntimeRepository
from .repositories.paper_operator_commands import PaperOperatorCommandRepository
from .services.paper_operator_commands import PaperOperatorCommandService
from .repositories.next_research_decisions import NextResearchDecisionRepository
from .services.next_research_decisions import NextResearchDecisionService
from .repositories.agent_sessions import AgentSessionRepository
from .services.agent_sessions import AgentSessionService


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
    implementation_lineage_resolver: ImplementationLineageResolver | None = None,
) -> FastAPI:
    """Create the Trader Console API for one configured scope.

    Args:
        settings: Explicit settings, or ``None`` to load the local environment
            baseline.
        pool_factory: Injectable database connection/authentication composition.
            The default consumes the configured DSN; a deployment can provide a
            secret-manager, managed-identity, or proxy-backed factory later.
        authentication_provider: Optional request-principal extension point.
            Current health and public configuration routes do not invoke it or
            make authorization claims. Authenticated deployment is later work.
        implementation_lineage_resolver: Optional research-owned resolver for
            rechecking exact implementation and validation evidence during
            Console preflight.

    Returns:
        A FastAPI application whose lifespan owns exactly one bounded pool.
    """
    configured_settings = settings or ConsoleApiSettings.from_environment()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        from .repositories.comparison_views import ComparisonViewRepository
        from .services.comparison_views import ComparisonViewService
        from .repositories.backtest_definitions import BacktestDefinitionRepository
        from .repositories.backtest_executions import BacktestExecutionRepository
        from .repositories.data_scope_comparisons import DataScopeComparisonRepository
        from .services.data_scope_comparisons import DataScopeComparisonService

        pool = pool_factory(configured_settings)
        database = ConsoleDatabase(pool, configured_settings)
        compatibility_repository = SchemaCompatibilityRepository(database)
        health_service = HealthService(
            scope_id=configured_settings.scope.scope_id,
            compatibility_repository=compatibility_repository,
        )
        resource_repository = ConsoleResourceRepository(database)
        resource_service = ResourceService(resource_repository)
        catalogue_service = CatalogueService.default()
        from .repositories.saved_data_scopes import SavedDataScopeRepository
        saved_data_scope_service = SavedDataScopeService(
            SavedDataScopeRepository(database, configured_settings.scope.scope_id)
        )
        data_scope_comparison_service = DataScopeComparisonService(
            DataScopeComparisonRepository(database, configured_settings.scope.scope_id)
        )
        preflight_service = PreflightService.default(
            resource_repository,
            lineage_resolver=implementation_lineage_resolver,
            saved_scope_lookup=saved_data_scope_service,
        )
        backtest_definition_service = BacktestDefinitionService(
            BacktestDefinitionRepository(database, configured_settings.scope.scope_id),
            preflight_service,
        )
        backtest_execution_service = BacktestExecutionService(
            BacktestExecutionRepository(database, configured_settings.scope.scope_id)
        )
        comparison_view_service = ComparisonViewService(
            ComparisonViewRepository(database, configured_settings.scope.scope_id)
        )
        paper_runtime_service = PaperRuntimeService(
            PaperRuntimeRepository(database), configured_settings.scope
        )
        paper_operator_command_service = PaperOperatorCommandService(
            PaperOperatorCommandRepository(database, configured_settings.scope.scope_id),
            configured_settings.scope,
        )
        next_research_decision_service = NextResearchDecisionService(
            NextResearchDecisionRepository(database, configured_settings.scope.scope_id)
        )
        agent_session_service = AgentSessionService(
            AgentSessionRepository(database, configured_settings.scope.scope_id)
        )
        opened = False
        app.state.database = database
        app.state.health_service = health_service
        app.state.resource_service = resource_service
        app.state.catalogue_service = catalogue_service
        app.state.preflight_service = preflight_service
        app.state.backtest_definition_service = backtest_definition_service
        app.state.backtest_execution_service = backtest_execution_service
        app.state.comparison_view_service = comparison_view_service
        app.state.saved_data_scope_service = saved_data_scope_service
        app.state.data_scope_comparison_service = data_scope_comparison_service
        app.state.paper_runtime_service = paper_runtime_service
        app.state.paper_operator_command_service = paper_operator_command_service
        app.state.next_research_decision_service = next_research_decision_service
        app.state.agent_session_service = agent_session_service
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
    app.state.context_service = ContextService(configured_settings.scope)
    app.state.authentication_provider = authentication_provider
    app.include_router(health_router)
    app.include_router(context_router)
    app.include_router(catalogue_router)
    app.include_router(backtest_definition_router)
    app.include_router(backtest_execution_router)
    app.include_router(resource_router)
    app.include_router(saved_data_scope_router)
    app.include_router(data_scope_comparison_router)
    app.include_router(paper_runtime_router)
    app.include_router(paper_operator_command_router)
    app.include_router(next_research_decision_router)
    app.include_router(agent_session_router)
    from .routers.comparison_views import router as comparison_view_router

    app.include_router(comparison_view_router)
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
