"""Stdio MCP server bound to the controlled optimization verification runtime.

The subprocess composes real MCP transport with guarded core data and research
artifact stores for the cross-package evidence graph.
"""

from __future__ import annotations

from trader.event_store import PostgresEventStore
from trader_mcp.catalogue.policy import load_local_environment
from trader_mcp.runtime.server import create_server
from trader_research.experiments import (
    ExperimentTrackingSinkRegistry,
    OptimizationEngineRegistry,
)
from trader_research.infrastructure.postgres import PostgresResearchArtifactStore
from tests.cross_package.qualification.support.postgres_verification import (
    assert_verification_database,
    load_test_settings,
)
from tests.cross_package.qualification.support.postgres_57n import (
    AuditedPostgresEventStore,
    configured_access_stage,
)
from tests.cross_package.qualification.support.realistic_optimization_fixture import build_backtest_config


def main() -> None:
    """Run the public MCP surface against the isolated verification database."""
    settings = load_test_settings(required=True)
    if settings is None:  # pragma: no cover - required=True fails first
        raise RuntimeError("PG_TEST settings are required")
    assert_verification_database(settings)
    connect_kwargs = settings.connect_kwargs()
    access_stage = configured_access_stage()
    event_store = (
        AuditedPostgresEventStore(stage=access_stage, **connect_kwargs)
        if access_stage is not None
        else PostgresEventStore(**connect_kwargs)
    )
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
