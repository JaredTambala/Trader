"""Example of running BacktestRunner with direct strategy/risk injection."""

from __future__ import annotations

from collections.abc import Mapping

from dotenv import load_dotenv

from trader.backtest import BacktestRunner, BacktestSpec
from trader.config import build_config, load_yaml_config
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

from backtest_support import assumptions_from_backtest_config, parse_datetime


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
    config = build_config(config_data)
    risk_cfg = config_data.get("risk", {})
    if risk_cfg is None:
        risk_cfg = {}
    if not isinstance(risk_cfg, Mapping):
        raise ValueError("risk section must be a mapping")
    backtest_cfg = config_data.get("backtest", {})
    if not isinstance(backtest_cfg, dict):
        raise ValueError("backtest section must be a mapping")

    spec = BacktestSpec(
        start=parse_datetime(str(backtest_cfg["start"])),
        end=parse_datetime(str(backtest_cfg["end"])),
        timeframe=str(backtest_cfg.get("timeframe", config.strategy_timeframe)),
        max_runs=int(backtest_cfg["max_runs"]) if backtest_cfg.get("max_runs") is not None else None,
    )
    strategy = ToggleUnitStrategy(
        symbols=tuple(str(symbol).strip().upper() for symbol in backtest_cfg.get("symbols", config.market_data_symbols)),
        order_qty=config.toggle_order_qty,
    )
    risk_manager = _build_risk_manager(risk_cfg)
    runner = BacktestRunner(
        config=config,
        spec=spec,
        symbols=backtest_cfg.get("symbols"),
        asset_class=backtest_cfg.get("asset_class"),
        initial_cash=backtest_cfg.get("initial_cash"),
        strategy=strategy,
        risk_manager=risk_manager,
        config_snapshot=config_data,
        assumptions=assumptions_from_backtest_config(backtest_cfg),
    )
    runner.run(log_cycle_details=bool(backtest_cfg.get("log_cycle_details", False)))


if __name__ == "__main__":
    main()
