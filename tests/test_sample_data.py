"""Tests for the deterministic sample-data workflow."""

from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path

from tests.support.duckdb_store import DuckDBEventStore
from trader.backtest import BacktestRunner, BacktestSpec, build_backtest_assumptions, serialize_backtest_result
from trader.config import build_config, load_yaml_config
from trader.sample_data import load_sample_market_data_csv
from trader_standard.risk import NoOpRiskManager
from trader_standard.strategies import build_trend_following_strategy


SAMPLE_CSV = Path("examples/data/demo_stock_1min.csv")
SAMPLE_CONFIG = Path("configs/reproducible_backtest.yaml")


def test_sample_data_loader_is_idempotent(tmp_path: Path) -> None:
    store = DuckDBEventStore(str(tmp_path / "events.duckdb"))

    loaded_first = load_sample_market_data_csv(store, SAMPLE_CSV)
    loaded_second = load_sample_market_data_csv(store, SAMPLE_CSV)

    count = store.connection().execute("SELECT COUNT(*) FROM stock_bar_events").fetchone()[0]
    assert loaded_first == 12
    assert loaded_second == 12
    assert count == 12


def test_reproducible_sample_backtest_emits_stable_payload(tmp_path: Path) -> None:
    os.environ.setdefault("PG_HOST", "127.0.0.1")
    os.environ.setdefault("PG_PORT", "5432")
    os.environ.setdefault("PG_DB", "trader")
    os.environ.setdefault("PG_USER", "trader")
    os.environ.setdefault("PG_PASSWORD", "traderpass")
    config_data = load_yaml_config(SAMPLE_CONFIG)
    config = build_config(config_data)
    store = DuckDBEventStore(str(tmp_path / "events.duckdb"))
    load_sample_market_data_csv(store, SAMPLE_CSV)

    first = _run_sample_backtest(config_data, config, store)
    second = _run_sample_backtest(config_data, config, store)

    assert first["symbols"] == ["DEMO"]
    assert first["timeframe"] == "1Min"
    assert first["assumptions"]["slippage"]["bps"] == 10.0
    assert first["assumptions"]["fees"]["fixed_per_order"] == 0.1
    assert _stable_payload(first) == _stable_payload(second)


def _run_sample_backtest(config_data, config, store: DuckDBEventStore) -> dict[str, object]:
    backtest_cfg = config_data["backtest"]
    strategy = build_trend_following_strategy(
        symbols=["DEMO"],
        asset_class="stocks",
        timeframe="1Min",
        target_qty_when_long=1.0,
        ema_fast_period=2,
        ema_slow_period=4,
        macd_fast_period=3,
        macd_slow_period=6,
        macd_signal_period=3,
    )
    spec = BacktestSpec(
        start=_parse_ts(str(backtest_cfg["start"])),
        end=_parse_ts(str(backtest_cfg["end"])),
        timeframe=str(backtest_cfg["timeframe"]),
        max_runs=None,
    )
    result = BacktestRunner(
        config=config,
        spec=spec,
        symbols=["DEMO"],
        asset_class="stocks",
        event_store=store,
        initial_cash=float(backtest_cfg["initial_cash"]),
        strategy=strategy,
        risk_manager=NoOpRiskManager(),
        assumptions=build_backtest_assumptions(backtest_cfg["assumptions"]),
        config_snapshot=config_data,
    ).run()
    return serialize_backtest_result(result)


def _stable_payload(payload: dict[str, object]) -> dict[str, object]:
    clone = dict(payload)
    clone.pop("started_at", None)
    clone.pop("finished_at", None)
    clone.pop("duration_seconds", None)
    clone.pop("run_id", None)
    clone.pop("experiment_id", None)
    clone.pop("experiment_run_id", None)
    clone.pop("provenance", None)
    trades = []
    for trade in clone.get("trades", []):
        if not isinstance(trade, dict):
            continue
        trade_clone = dict(trade)
        trade_clone.pop("client_order_id", None)
        trade_clone.pop("cycle_id", None)
        trade_clone.pop("fill_ts", None)
        trades.append(trade_clone)
    clone["trades"] = trades
    return clone


def _parse_ts(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
