"""Package-local MCP stdio server with sample loading explicitly enabled.

The subprocess fixture belongs to the MCP Data loading contract and keeps its
temporary event store isolated from other test owners.
"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from tests.support.duckdb_store import DuckDBEventStore
from trader_mcp.catalogue.policy import load_local_environment
from trader_mcp.runtime.server import create_server
from trader_research.foundation import InMemoryResearchArtifactStore


def main() -> None:
    """Run an empty DuckDB-backed MCP server for workflow evidence tests."""
    local_env = load_local_environment()
    with TemporaryDirectory(prefix="trader-mcp-loading-evidence-") as tmp_dir:
        store = DuckDBEventStore(str(Path(tmp_dir) / "events.duckdb"))
        journal = InMemoryResearchArtifactStore()
        try:
            create_server(
                local_env,
                event_store_provider=lambda: store,
                research_artifact_store_provider=lambda: journal,
            ).run(transport=local_env.transport)
        finally:
            store.close()


if __name__ == "__main__":
    main()
