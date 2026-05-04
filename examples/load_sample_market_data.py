"""Load deterministic sample market data into the configured event store."""

from __future__ import annotations

import argparse
from pathlib import Path

from dotenv import load_dotenv

from trader.config import build_config, load_yaml_config
from trader.data import build_event_store
from trader.sample_data import load_sample_market_data_csv


def main() -> None:
    """Load the checked-in sample CSV into the configured event store."""
    parser = argparse.ArgumentParser(description="Load deterministic sample market data.")
    parser.add_argument(
        "config",
        nargs="?",
        default="configs/reproducible_backtest.yaml",
        help="Path to the YAML configuration file.",
    )
    parser.add_argument(
        "--csv",
        default="examples/data/demo_stock_1min.csv",
        help="Path to the sample CSV file.",
    )
    args = parser.parse_args()

    load_dotenv(".env")
    config_data = load_yaml_config(args.config)
    config = build_config(config_data)
    event_store = build_event_store(config)
    try:
        loaded = load_sample_market_data_csv(event_store, Path(args.csv))
    finally:
        event_store.close()
    print(f"Loaded {loaded} sample rows from {args.csv}")


if __name__ == "__main__":
    main()
