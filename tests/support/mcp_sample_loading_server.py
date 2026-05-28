"""Test-only MCP stdio server with an empty store and sample loading enabled."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from tests.support.duckdb_store import DuckDBEventStore
from trader_mcp.environment import load_local_environment
from trader_mcp.server import create_server


def main() -> None:
    """Run an empty DuckDB-backed MCP server for workflow evidence tests."""
    local_env = load_local_environment()
    with TemporaryDirectory(prefix="trader-mcp-loading-evidence-") as tmp_dir:
        store = DuckDBEventStore(str(Path(tmp_dir) / "events.duckdb"))
        try:
            create_server(local_env, event_store_provider=lambda: store).run(transport=local_env.transport)
        finally:
            store.close()


if __name__ == "__main__":
    main()
