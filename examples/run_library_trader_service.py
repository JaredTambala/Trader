"""Run TraderService with one of the trader_standard policy-driven strategies."""

from __future__ import annotations

from dataclasses import replace
import logging
from typing import Mapping

from dotenv import load_dotenv

from trader.config import build_config, load_yaml_config, resolve_log_level
from trader.trader_service import TraderService

from strategy_library_support import build_library_risk_manager, build_library_strategy


logger = logging.getLogger(__name__)


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
    config_data = load_yaml_config("configs/library_example.yaml")
    _configure_logging(resolve_log_level(config_data))
    config = build_config(config_data)

    risk_cfg = config_data.get("risk", {})
    if risk_cfg is None:
        risk_cfg = {}
    if not isinstance(risk_cfg, Mapping):
        raise ValueError("risk section must be a mapping")

    service_cfg = config_data.get("trader_service", {})
    mode = service_cfg.get("mode", config.mode) if isinstance(service_cfg, dict) else config.mode
    config = replace(config, mode=str(mode))

    strategy = build_library_strategy(config_data, config)
    risk_manager = build_library_risk_manager(risk_cfg)

    logger.info(
        "Starting library trader service mode=%s symbols=%s timeframe=%s strategy=%s risk_manager=%s",
        config.mode,
        ",".join(config.market_data_symbols) if config.market_data_symbols else "<none>",
        config.strategy_timeframe,
        strategy.strategy_id,
        risk_manager.__class__.__name__,
    )

    service = TraderService(
        config=config,
        strategy=strategy,
        risk_manager=risk_manager,
        config_snapshot=config_data,
    )
    service.run()


if __name__ == "__main__":
    main()
