"""External entrypoint for market data streaming."""

from __future__ import annotations

import argparse
import logging
from typing import Mapping

from dotenv import load_dotenv

from trader.config import build_config, load_yaml_config, resolve_log_level
from trader.market_data.stream import MarketDataStreamRunner
from trader.timeframes import normalize_timeframe


logger = logging.getLogger(__name__)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stream Alpaca market data bars.")
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


def _parse_symbols_value(value: object | None) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, str):
        symbols = [symbol.strip().upper() for symbol in value.split(",") if symbol.strip()]
        return symbols or None
    if isinstance(value, (list, tuple)):
        symbols = [str(symbol).strip().upper() for symbol in value if str(symbol).strip()]
        return symbols or None
    raise ValueError("stream.symbols must be a string or list")


def main() -> None:
    load_dotenv(".env")
    args = _parse_args()
    config_data = load_yaml_config(args.config)
    _configure_logging(resolve_log_level(config_data))
    config = build_config(config_data)

    stream = config_data.get("stream", {})
    if stream is None:
        stream = {}
    if not isinstance(stream, Mapping):
        raise ValueError("stream section must be a mapping")

    service_cfg = config_data.get("trader_service", {})
    if service_cfg is None:
        service_cfg = {}
    if not isinstance(service_cfg, Mapping):
        raise ValueError("trader_service section must be a mapping")

    symbols = _parse_symbols_value(stream.get("symbols"))
    asset_class = stream.get("asset_class")
    timeframe = stream.get("timeframe")
    if timeframe:
        timeframe = normalize_timeframe(str(timeframe))
    notify_channel = service_cfg.get("notify_channel")
    runner = MarketDataStreamRunner(
        config,
        symbols=symbols,
        asset_class=str(asset_class) if asset_class else None,
        timeframe=str(timeframe) if timeframe else None,
        notify_channel=str(notify_channel) if notify_channel else None,
    )
    runner.run()


if __name__ == "__main__":
    main()
