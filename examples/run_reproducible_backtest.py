"""Run a deterministic sample backtest and export stable artifacts."""

from __future__ import annotations

import argparse
from pathlib import Path

from dotenv import load_dotenv

from backtest_support import assumptions_from_backtest_config, parse_datetime
from strategy_library_support import build_library_risk_manager, build_library_strategy
from trader.backtest import (
    BacktestRunner,
    BacktestSpec,
    export_backtest_equity_curve_csv,
    export_backtest_result_json,
    export_backtest_trades_csv,
)
from trader.config import build_config, load_yaml_config


def main() -> None:
    """Run the checked-in reproducible sample backtest."""
    parser = argparse.ArgumentParser(description="Run the reproducible sample backtest.")
    parser.add_argument(
        "config",
        nargs="?",
        default="configs/reproducible_backtest.yaml",
        help="Path to the YAML configuration file.",
    )
    parser.add_argument(
        "--output-dir",
        default="artifacts/reproducible_backtest",
        help="Directory for exported JSON/CSV artifacts.",
    )
    args = parser.parse_args()

    load_dotenv(".env")
    config_data = load_yaml_config(args.config)
    config = build_config(config_data)
    risk_cfg = config_data.get("risk", {})
    if risk_cfg is None:
        risk_cfg = {}
    if not isinstance(risk_cfg, dict):
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
    result = runner.run(log_cycle_details=bool(backtest_cfg.get("log_cycle_details", False)))

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = export_backtest_result_json(result, output_dir / "result.json")
    equity_path = export_backtest_equity_curve_csv(result, output_dir / "equity_curve.csv")
    trades_path = export_backtest_trades_csv(result, output_dir / "trades.csv")

    print(f"total_runs={result.total_runs}")
    print(f"total_return={result.strategy_performance.total_return}")
    print(f"trade_count={result.strategy_performance.trade_count}")
    print(f"realized_pnl={result.realized_pnl}")
    print(f"total_fees={result.total_fees}")
    print(f"total_slippage={result.total_slippage}")
    print(f"warnings={len(result.warnings)}")
    print(f"result_json={json_path}")
    print(f"equity_csv={equity_path}")
    print(f"trades_csv={trades_path}")


if __name__ == "__main__":
    main()
