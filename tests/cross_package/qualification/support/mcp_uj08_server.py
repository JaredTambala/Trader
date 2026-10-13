"""Compose the public MCP server over one test-owned UJ-08 schema."""

from __future__ import annotations

import os
import re

import psycopg

from trader.event_store import PostgresEventStore
from trader_mcp.catalogue.policy import load_local_environment
from trader_mcp.runtime.server import create_server
from trader_research.infrastructure.postgres import (
    PostgresResearchArtifactStore,
    PostgresResearchJobStore,
)


def campaign_dsn() -> str:
    """Require an explicit disposable database and test-owned search path."""
    dsn = os.environ["UJ08_DSN"]
    settings = psycopg.conninfo.conninfo_to_dict(dsn)
    if not settings.get("dbname", "").endswith(("_test", "_testing")):
        raise ValueError("UJ-08 requires a disposable test database")
    if not re.fullmatch(
        r"-c search_path=trader_uj08_[0-9a-f]{32}", settings.get("options", "")
    ):
        raise ValueError("UJ-08 requires an isolated campaign schema")
    return dsn


def main() -> None:
    """Run production registrations over real schema-scoped persistence."""
    dsn = campaign_dsn()
    events = PostgresEventStore(dsn=dsn)
    artifacts = PostgresResearchArtifactStore(dsn=dsn)
    jobs = PostgresResearchJobStore(artifacts.connection())
    environment = load_local_environment("env.template")
    server = create_server(
        environment,
        event_store_provider=lambda: events,
        research_artifact_store_provider=lambda: artifacts,
        research_job_store_provider=lambda: jobs,
    )
    try:
        server.run(transport="stdio")
    finally:
        artifacts.close()
        events.close()


if __name__ == "__main__":
    main()
