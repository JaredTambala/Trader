"""Run a backtest using the trader_standard policy-driven strategies."""

from __future__ import annotations

from collections.abc import Mapping

from dotenv import load_dotenv

from trader.backtest import BacktestRunner, BacktestSpec
from trader.config import build_config, load_yaml_config

from backtest_support import assumptions_from_backtest_config, parse_datetime
from strategy_library_support import build_library_risk_manager, build_library_strategy

def main() -> None:
    load_dotenv(".env")
    config_data = load_yaml_config("configs/library_example.yaml")
    config = build_config(config_data)

    risk_cfg = config_data.get("risk", {})
    if risk_cfg is None:
        risk_cfg = {}
    if not isinstance(risk_cfg, Mapping):
        raise ValueError("risk section must be a mapping")

    backtest_cfg = config_data.get("backtest", {})
    if not isinstance(backtest_cfg, dict):
        raise ValueError("backtest section must be a mapping")

    strategy = build_library_strategy(config_data, config)
    risk_manager = build_library_risk_manager(risk_cfg)
    spec = BacktestSpec(
        start=parse_datetime(str(backtest_cfg["start"])),
        end=parse_datetime(str(backtest_cfg["end"])),
        timeframe=str(backtest_cfg.get("timeframe", config.strategy_timeframe)),
        max_runs=int(backtest_cfg["max_runs"]) if backtest_cfg.get("max_runs") is not None else None,
    )

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
