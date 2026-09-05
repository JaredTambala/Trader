"""Controlled MCP server that rejects optional optimizer and tracking imports.

The subprocess fixture proves built-in optimization and canonical reads remain
available without Optuna or MLflow packages.
"""

from __future__ import annotations

import builtins


_real_import = builtins.__import__


def _guarded_import(name: str, *args: object, **kwargs: object) -> object:
    if name.split(".", 1)[0] in {"mlflow", "optuna"}:
        raise ModuleNotFoundError(name)
    return _real_import(name, *args, **kwargs)


builtins.__import__ = _guarded_import

from trader.event_store import PostgresEventStore  # noqa: E402
from trader_mcp.catalogue.policy import load_local_environment  # noqa: E402
from trader_mcp.runtime.server import create_server  # noqa: E402
from trader_research.experiments import (  # noqa: E402
    ExperimentTrackingSinkRegistry,
    OptimizationEngineRegistry,
)
from trader_research.infrastructure.postgres import (  # noqa: E402
    PostgresResearchArtifactStore,
)
from tests.cross_package.qualification.support.postgres_verification import (  # noqa: E402
    assert_verification_database,
    load_test_settings,
)
from tests.cross_package.qualification.support.realistic_optimization_fixture import (  # noqa: E402
    build_backtest_config,
)


def main() -> None:
    """Run MCP using only built-in optimization and canonical Postgres state."""
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
