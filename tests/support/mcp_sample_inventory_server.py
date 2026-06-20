"""Test-only MCP stdio server seeded with sample inventory data."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from tests.support.duckdb_store import DuckDBEventStore
from trader.market_data.sample import load_sample_market_data_csv
from trader_mcp.environment import load_local_environment
from trader_mcp.server import create_server


SAMPLE_CSV = Path(__file__).resolve().parents[2] / "examples/data/demo_stock_1min.csv"


def main() -> None:
    """Run a sample-data MCP server for stdio evidence tests."""
    local_env = load_local_environment()
    with TemporaryDirectory(prefix="trader-mcp-evidence-") as tmp_dir:
        store = DuckDBEventStore(str(Path(tmp_dir) / "events.duckdb"))
        load_sample_market_data_csv(store, SAMPLE_CSV)
        try:
            create_server(local_env, event_store_provider=lambda: store).run(transport=local_env.transport)
        finally:
            store.close()


if __name__ == "__main__":
    main()
