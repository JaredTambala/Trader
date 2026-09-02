"""Guarded stdio MCP server for first-slice agentic qualification."""

from __future__ import annotations

from trader.event_store import PostgresEventStore
from trader_mcp.environment import load_local_environment
from trader_mcp.server import create_server
from trader_research.experiments import (
    ExperimentTrackingSinkRegistry,
    OptimizationEngineRegistry,
)
from trader_research.infrastructure.postgres import PostgresResearchArtifactStore

from tests.support.agentic_fixture import (
    build_qualification_data_policy,
    build_qualification_strategy_validation_service,
    load_server_scenario_from_environment,
)
from tests.support.postgres_verification import (
    AGENTIC_VERIFICATION_PROFILE,
    assert_verification_database,
    load_qualification_profile,
    load_test_settings,
)


def main() -> None:
    """Run production tools against only the guarded qualification database.

    Raises:
        RuntimeError: If the controlled profile or PG_TEST settings are absent.
        VerificationConfigurationError: If the database marker, role, locale,
            timezone, or frozen revision does not match the active campaign.
    """
    profile = load_qualification_profile()
    if profile.name != AGENTIC_VERIFICATION_PROFILE:
        raise RuntimeError("agentic MCP requires the controlled agentic profile")
    scenario, sessions, freeze_revision = load_server_scenario_from_environment()
    settings = load_test_settings(required=True)
    if settings is None:  # pragma: no cover - required=True raises first
        raise RuntimeError("PG_TEST settings are required")
    assert_verification_database(settings, freeze_revision=freeze_revision)
    event_store = PostgresEventStore(dsn=settings.conninfo())
    artifact_store = PostgresResearchArtifactStore(dsn=settings.conninfo())
    environment = load_local_environment("env.template")
    data_policy = build_qualification_data_policy(
        scenario,
        sessions,
        allow_data_loading=environment.allow_data_loading,
    )
    server = create_server(
        environment,
        event_store_provider=lambda: event_store,
        data_loading_policy=data_policy,
        research_artifact_store_provider=lambda: artifact_store,
        optimizer_registry=OptimizationEngineRegistry(),
        tracking_sink_registry=ExperimentTrackingSinkRegistry(),
        strategy_validation_service=(
            build_qualification_strategy_validation_service(
                scenario,
                sessions,
            )
        ),
    )
    try:
        server.run(transport=environment.transport)
    finally:
        artifact_store.close()
        event_store.close()


if __name__ == "__main__":
    main()
