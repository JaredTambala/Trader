"""Stdio MCP server for the isolated orchestration qualification runtime."""

from __future__ import annotations

from trader.event_store import PostgresEventStore
from trader_mcp.environment import load_local_environment
from trader_mcp.server import create_server
from trader_research.experiments import (
    ExperimentTrackingSinkRegistry,
    OptimizationEngineRegistry,
)
from trader_research.infrastructure.postgres import PostgresResearchArtifactStore
from tests.support.postgres_verification import (
    ORCHESTRATION_VERIFICATION_PROFILE,
    assert_verification_database,
    load_qualification_profile,
    load_test_settings,
)
from tests.support.realistic_optimization_fixture import build_backtest_config


def main() -> None:
    """Run public MCP tools against only the disposable qualification database."""
    profile = load_qualification_profile()
    if profile.name != ORCHESTRATION_VERIFICATION_PROFILE:
        raise RuntimeError("the orchestration MCP server requires its qualification profile")
    settings = load_test_settings(required=True)
    if settings is None:  # pragma: no cover - required=True fails first
        raise RuntimeError("PG_TEST settings are required")
    assert_verification_database(settings)
    connect_kwargs = settings.connect_kwargs()
    event_store = PostgresEventStore(**connect_kwargs)
    artifact_store = PostgresResearchArtifactStore(**connect_kwargs)
    environment = load_local_environment("env.template")
    server = create_server(
        environment,
        event_store_provider=lambda: event_store,
        backtest_config_provider=lambda: build_backtest_config(connect_kwargs),
        research_artifact_store_provider=lambda: artifact_store,
        optimizer_registry=OptimizationEngineRegistry(),
        tracking_sink_registry=ExperimentTrackingSinkRegistry(),
    )
    try:
        server.run(transport=environment.transport)
    finally:
        artifact_store.close()
        event_store.close()


if __name__ == "__main__":
    main()
