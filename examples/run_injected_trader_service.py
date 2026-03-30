"""Example of running TraderService with direct strategy/risk injection."""

from __future__ import annotations

from dataclasses import replace
import logging
from typing import Mapping

from dotenv import load_dotenv

from trader.config import build_config, load_yaml_config, resolve_log_level
from trader.trader_service import TraderService
from trader.risk import RiskManager, RiskPipeline
from trader_standard.risk import (
    HaltRiskManager,
    MaxGrossExposureRiskManager,
    MaxOrdersPerRunRiskManager,
    MaxPositionUsdPerSymbolRiskManager,
    NoOpRiskManager,
    OpenBuyOrderLimitRiskManager,
)
from trader_standard.strategies import ToggleUnitStrategy


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


def _build_risk_manager(risk_cfg: Mapping[str, object] | None = None) -> RiskManager:
    risk_cfg = risk_cfg or {}
    managers: list[RiskManager] = []
    if bool(risk_cfg.get("halted", False)):
        managers.append(HaltRiskManager())
    if risk_cfg.get("max_orders_per_run") is not None:
        managers.append(MaxOrdersPerRunRiskManager(limit=int(risk_cfg["max_orders_per_run"])))
    if risk_cfg.get("max_gross_usd") is not None:
        managers.append(MaxGrossExposureRiskManager(limit_usd=float(risk_cfg["max_gross_usd"])))
    if risk_cfg.get("max_pos_usd_per_symbol") is not None:
        managers.append(
            MaxPositionUsdPerSymbolRiskManager(limit_usd=float(risk_cfg["max_pos_usd_per_symbol"]))
        )
    if risk_cfg.get("max_open_buy_orders_per_symbol") is not None:
        managers.append(
            OpenBuyOrderLimitRiskManager(
                max_open_buy_orders_per_symbol=int(risk_cfg["max_open_buy_orders_per_symbol"])
            )
        )
    if not managers:
        return NoOpRiskManager()
    return RiskPipeline(managers)


def main() -> None:
    load_dotenv(".env")
    config_data = load_yaml_config("configs/example.yaml")
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

    strategy = ToggleUnitStrategy(
        symbols=config.market_data_symbols,
        order_qty=config.toggle_order_qty,
    )
    risk_manager = _build_risk_manager(risk_cfg)

    logger.info(
        "Starting injected trader service mode=%s symbols=%s timeframe=%s strategy=%s risk_manager=%s",
        config.mode,
        ",".join(config.market_data_symbols) if config.market_data_symbols else "<none>",
        config.strategy_timeframe,
        strategy.__class__.__name__,
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
