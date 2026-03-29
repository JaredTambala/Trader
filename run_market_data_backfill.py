"""External entrypoint for market data backfills."""

from __future__ import annotations

import argparse
import logging
from datetime import datetime, timezone
from typing import Mapping

from dotenv import load_dotenv

from trader.config import build_config, load_yaml_config, resolve_log_level
from trader.market_data_backfill import (
    BackfillSpec,
    MarketDataBackfillRunner,
    _parse_symbols_value,
    _parse_timeframe,
    _resolve_window_from_config,
)


logger = logging.getLogger(__name__)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill Alpaca market data bars.")
    parser.add_argument("config", help="Path to the YAML configuration file.")
    return parser.parse_args()


def _configure_logging(level_name: str | None = None) -> None:
    level_name = (level_name or "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logger.info("Logging configured level=%s", level_name)


def main() -> None:
    load_dotenv(".env")
    args = _parse_args()
    config_data = load_yaml_config(args.config)
    _configure_logging(resolve_log_level(config_data))
    config = build_config(config_data)

    backfill = config_data.get("backfill", {})
    if backfill is None:
        backfill = {}
    if not isinstance(backfill, Mapping):
        raise ValueError("backfill section must be a mapping")
    service_cfg = config_data.get("trader_service", {})
    if service_cfg is None:
        service_cfg = {}
    if not isinstance(service_cfg, Mapping):
        raise ValueError("trader_service section must be a mapping")

    end = datetime.now(timezone.utc)
    start, end = _resolve_window_from_config(backfill, end)
    timeframe_value = backfill.get("timeframe", config.strategy_timeframe)
    limit_value = backfill.get("limit")
    limit = int(limit_value) if limit_value is not None else None
    spec = BackfillSpec(
        start=start,
        end=end,
        timeframe=_parse_timeframe(str(timeframe_value)),
        limit=limit,
    )
    symbols = _parse_symbols_value(backfill.get("symbols"))
    asset_class = backfill.get("asset_class")
    notify_channel = service_cfg.get("notify_channel")
    runner = MarketDataBackfillRunner(
        config,
        spec,
        symbols=symbols,
        asset_class=str(asset_class) if asset_class else None,
        notify_channel=str(notify_channel) if notify_channel else None,
    )
    runner.run()


if __name__ == "__main__":
    main()
