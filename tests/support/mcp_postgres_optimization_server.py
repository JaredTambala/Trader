"""Stdio MCP server bound only to the controlled Postgres verification runtime."""

from __future__ import annotations

from trader.event_store import PostgresEventStore
from trader_mcp.environment import load_local_environment
from trader_mcp.server import create_server
from trader_research.optimization import OptimizationEngineRegistry
from trader_research.postgres_artifact_store import PostgresResearchArtifactStore
from trader_research.tracking import ExperimentTrackingSinkRegistry
from tests.support.postgres_verification import (
    assert_verification_database,
    load_test_settings,
)
from tests.support.realistic_optimization_fixture import build_backtest_config


def main() -> None:
    """Run the public MCP surface against the isolated verification database."""
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
