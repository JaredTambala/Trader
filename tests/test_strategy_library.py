"""Tests for the built-in indicator, signal, and strategy library."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from trader.backtest import BacktestRunner, BacktestSpec
from trader.config import Config
from trader.cycle import run_cycle
from trader.market_data import StaticMarketDataSource, StockBarEvent
from trader.portfolio import Portfolio, Position
from trader.signals import Bar
from tests.support.duckdb_store import DuckDBEventStore
from trader_standard.indicators import BollingerBandsIndicator, EmaIndicator, MacdIndicator, RsiIndicator
from trader_standard.risk import NoOpRiskManager
from trader_standard.signals import (
    BollingerBandSignal,
    EmaCrossoverSignal,
    MacdCrossoverSignal,
    RsiThresholdSignal,
    SmaStretchSignal,
)
from trader_standard.strategies import (
    FixedStopLossPolicy,
    StrategySnapshot,
    TrailingStopPolicy,
    build_bollinger_band_strategy,
    build_mean_reversion_strategy,
    build_trend_following_strategy,
)


def _bars_from_closes(closes: list[float]) -> list[Bar]:
    base_ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
    bars: list[Bar] = []
    for idx, close in enumerate(closes):
        ts = base_ts + timedelta(minutes=idx)
        bars.append(
            Bar(
                ts=ts,
                open=close,
                high=close,
                low=close,
                close=close,
                volume=1.0,
                vwap=None,
                trade_count=None,
            )
        )
    return list(reversed(bars))


def _seed_stock_bars(store: DuckDBEventStore, symbol: str, closes: list[float]) -> list[StockBarEvent]:
    base_ts = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    events: list[StockBarEvent] = []
    for idx, close in enumerate(closes):
        ts = base_ts + timedelta(minutes=idx)
        payload = {
            "symbol": symbol,
            "timeframe": "1Min",
            "ts": ts,
            "ingested_at": ts,
            "open": close,
            "high": close,
            "low": close,
            "close": close,
            "volume": 1.0,
            "trade_count": None,
            "vwap": None,
            "source": "test",
        }
        store.record_event("stock_bar_events", payload)
        events.append(StockBarEvent(**payload))
    return events


def _config(tmp_path: Path) -> Config:
    return Config(
        mode="backtest",
        strategy_type="library",
        strategy_id="library",
        strategy_timeframe="1Min",
        sma_short_window=2,
        sma_long_window=3,
        db_path=str(tmp_path / "events.duckdb"),
        event_store="postgres",
        market_data_source="noop",
        market_data_asset_class="stocks",
        market_data_stock_feed="iex",
        market_data_symbols=("AAPL",),
        market_data_max_age_seconds=60,
        alpaca_api_key="",
        alpaca_secret_key="",
        alpaca_data_base_url="https://data.alpaca.markets",
        alpaca_base_url="https://paper-api.alpaca.markets",
        pg_dsn="",
        pg_host="",
        pg_port=5432,
        pg_db="",
        pg_user="",
        pg_password="",
        buffered_event_store=False,
        buffer_flush_interval_ms=250,
        buffer_max_batch_size=500,
        buffer_max_queue_size=10000,
        buffer_block_on_full=True,
        log_signal_events=True,
        log_indicator_events=True,
        log_order_events=True,
        log_fill_events=True,
        log_position_snapshots=True,
        broker_type="internal",
    )


def test_indicator_helpers_compute_expected_values() -> None:
    ema_series = EmaIndicator(period=3).compute_series(_bars_from_closes([1, 2, 3, 4, 5, 6]))
    assert list(ema_series) == pytest.approx([5.0, 4.0, 3.0, 2.0])

    rsi_series = RsiIndicator(period=5).compute_series(_bars_from_closes([1, 2, 3, 4, 5, 6]))
    assert rsi_series[0] == pytest.approx(100.0)

    macd_series = MacdIndicator(fast_period=3, slow_period=6, signal_period=3).compute_series(
        _bars_from_closes([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11])
    )
    assert macd_series[0].macd_line > 0.0
    assert macd_series[0].signal_line > 0.0

    bands = BollingerBandsIndicator(period=5, stddev_multiplier=2.0).compute_series(
        _bars_from_closes([10, 10, 10, 10, 10, 8])
    )
    assert bands[0].middle == pytest.approx(9.6)
    assert bands[0].upper > bands[0].middle > bands[0].lower
    assert bands[0].bandwidth > 0.0


def test_signals_cover_crossovers_thresholds_and_band_reentry() -> None:
    ema_signal = EmaCrossoverSignal(fast=EmaIndicator(period=2), slow=EmaIndicator(period=4))
    assert ema_signal.compute(_bars_from_closes([8.43, 10.27, 9.22, 10.62, 10.75, 7.39, 7.08, 12.02])) == 1.0
    assert ema_signal.compute(_bars_from_closes([8.56, 8.41, 12.97, 9.82, 12.02, 9.86, 10.83, 7.9])) == -1.0

    rsi_signal = RsiThresholdSignal(indicator=RsiIndicator(period=5), oversold=30.0, overbought=70.0)
    assert rsi_signal.compute(_bars_from_closes([10, 9, 8, 7, 6, 5])) == 1.0
    assert rsi_signal.compute(_bars_from_closes([1, 2, 3, 4, 5, 6])) == -1.0

    macd_signal = MacdCrossoverSignal(indicator=MacdIndicator(fast_period=3, slow_period=6, signal_period=3))
    assert macd_signal.compute(_bars_from_closes([9.77, 10.18, 9.94, 12.55, 10.01, 11.99, 9.12, 12.3, 12.4, 9.77, 10.41, 12.52])) == 1.0
    assert macd_signal.compute(_bars_from_closes([12.45, 8.15, 11.47, 7.35, 10.92, 8.64, 8.36, 12.25, 7.64, 10.13, 12.12, 8.47])) == -1.0

    bollinger_signal = BollingerBandSignal(indicator=BollingerBandsIndicator(period=5, stddev_multiplier=1.0))
    assert bollinger_signal.compute(_bars_from_closes([10, 10, 10, 10, 10, 7, 8])) == 1.0


def test_trailing_stop_policy_tracks_high_water_and_resets() -> None:
    policy = TrailingStopPolicy(trailing_stop_pct=0.1)
    first = StrategySnapshot(
        symbol="AAPL",
        decision_ts=datetime(2026, 1, 1, tzinfo=timezone.utc),
        last_price=12.0,
        position_qty=1.0,
        avg_price=10.0,
        signals={},
    )
    policy.observe(first)
    assert policy.should_exit(first) is False

    second = StrategySnapshot(
        symbol="AAPL",
        decision_ts=datetime(2026, 1, 1, 0, 1, tzinfo=timezone.utc),
        last_price=10.5,
        position_qty=1.0,
        avg_price=10.0,
        signals={},
    )
    policy.observe(second)
    assert policy.should_exit(second) is True

    policy.reset("AAPL")
    policy.observe(second)
    assert policy.should_exit(second) is False


def test_strategy_stop_precedes_entry_and_flattens_existing_long(tmp_path: Path) -> None:
    store = DuckDBEventStore(str(tmp_path / "events.duckdb"))
    _seed_stock_bars(store, "AAPL", [10, 10, 10, 10, 10, 8])
    strategy = build_mean_reversion_strategy(
        symbols=["AAPL"],
        asset_class="stocks",
        timeframe="1Min",
        stop_policy=FixedStopLossPolicy(stop_loss_pct=0.1),
        rsi_period=5,
        mean_period=5,
        stretch_pct=0.05,
    )
    portfolio = Portfolio(positions={"AAPL": Position(symbol="AAPL", qty=1.0, avg_price=10.0)}, cash_balance=0.0)
    decision_ts = datetime(2026, 1, 20, 12, 5, tzinfo=timezone.utc)

    orders = strategy.generate_orders(
        run_id="run1",
        cycle_id="cycle1",
        decision_ts=decision_ts,
        event_store=store,
        portfolio=portfolio,
    )

    assert len(orders) == 1
    assert orders[0]["side"] == "sell"
    assert orders[0]["qty"] == pytest.approx(1.0)


def test_strategy_does_not_pyramid_existing_long(tmp_path: Path) -> None:
    store = DuckDBEventStore(str(tmp_path / "events.duckdb"))
    _seed_stock_bars(store, "AAPL", [10, 10, 10, 10, 10, 8])
    strategy = build_mean_reversion_strategy(
        symbols=["AAPL"],
        asset_class="stocks",
        timeframe="1Min",
        rsi_period=5,
        mean_period=5,
        stretch_pct=0.05,
    )
    portfolio = Portfolio(positions={"AAPL": Position(symbol="AAPL", qty=1.0, avg_price=8.0)}, cash_balance=0.0)

    orders = strategy.generate_orders(
        run_id="run1",
        cycle_id="cycle1",
        decision_ts=datetime(2026, 1, 20, 12, 5, tzinfo=timezone.utc),
        event_store=store,
        portfolio=portfolio,
    )

    assert orders == []


def test_built_in_compositions_behave_differently_on_same_bars(tmp_path: Path) -> None:
    store = DuckDBEventStore(str(tmp_path / "events.duckdb"))
    _seed_stock_bars(store, "AAPL", [9.77, 10.18, 9.94, 12.55, 10.01, 11.99, 9.12, 12.3, 12.4, 9.77, 10.41, 12.52])
    decision_ts = datetime(2026, 1, 20, 12, 11, tzinfo=timezone.utc)
    portfolio = Portfolio.empty()

    trend = build_trend_following_strategy(
        symbols=["AAPL"],
        asset_class="stocks",
        timeframe="1Min",
        ema_fast_period=2,
        ema_slow_period=4,
        macd_fast_period=3,
        macd_slow_period=6,
        macd_signal_period=3,
    )
    mean = build_mean_reversion_strategy(
        symbols=["AAPL"],
        asset_class="stocks",
        timeframe="1Min",
        rsi_period=5,
        mean_period=5,
        stretch_pct=0.05,
    )
    boll = build_bollinger_band_strategy(
        symbols=["AAPL"],
        asset_class="stocks",
        timeframe="1Min",
        period=5,
        stddev_multiplier=1.0,
    )

    trend_orders = trend.generate_orders(
        run_id="run",
        cycle_id="cycle",
        decision_ts=decision_ts,
        event_store=store,
        portfolio=portfolio,
    )
    mean_orders = mean.generate_orders(
        run_id="run",
        cycle_id="cycle",
        decision_ts=decision_ts,
        event_store=store,
        portfolio=portfolio,
    )
    boll_orders = boll.generate_orders(
        run_id="run",
        cycle_id="cycle",
        decision_ts=decision_ts,
        event_store=store,
        portfolio=portfolio,
    )

    assert len(trend_orders) == 1
    assert trend_orders[0]["side"] == "buy"
    assert mean_orders == []
    assert boll_orders == []


def test_bollinger_band_strategy_enters_and_exits_on_reversion(tmp_path: Path) -> None:
    entry_store = DuckDBEventStore(str(tmp_path / "entry.duckdb"))
    _seed_stock_bars(entry_store, "AAPL", [10, 10, 10, 10, 10, 7, 8])
    strategy = build_bollinger_band_strategy(
        symbols=["AAPL"],
        asset_class="stocks",
        timeframe="1Min",
        period=5,
        stddev_multiplier=1.0,
    )
    entry_orders = strategy.generate_orders(
        run_id="run",
        cycle_id="cycle",
        decision_ts=datetime(2026, 1, 20, 12, 6, tzinfo=timezone.utc),
        event_store=entry_store,
        portfolio=Portfolio.empty(),
    )
    assert len(entry_orders) == 1
    assert entry_orders[0]["side"] == "buy"

    exit_store = DuckDBEventStore(str(tmp_path / "exit.duckdb"))
    _seed_stock_bars(exit_store, "AAPL", [8, 8, 8, 8, 8, 9, 10])
    exit_orders = strategy.generate_orders(
        run_id="run",
        cycle_id="cycle2",
        decision_ts=datetime(2026, 1, 20, 12, 6, tzinfo=timezone.utc),
        event_store=exit_store,
        portfolio=Portfolio(positions={"AAPL": Position(symbol="AAPL", qty=1.0, avg_price=8.0)}, cash_balance=0.0),
    )
    assert len(exit_orders) == 1
    assert exit_orders[0]["side"] == "sell"


def test_run_cycle_persists_signal_and_indicator_events_for_library_strategy(tmp_path: Path) -> None:
    config = _config(tmp_path)
    store = DuckDBEventStore(config.db_path)
    events = _seed_stock_bars(store, "AAPL", [9.77, 10.18, 9.94, 12.55, 10.01, 11.99, 9.12, 12.3, 12.4, 9.77, 10.41, 12.52])
    strategy = build_trend_following_strategy(
        symbols=["AAPL"],
        asset_class="stocks",
        timeframe="1Min",
        ema_fast_period=2,
        ema_slow_period=4,
        macd_fast_period=3,
        macd_slow_period=6,
        macd_signal_period=3,
    )

    run_cycle(
        event_store=store,
        strategy=strategy,
        risk_manager=NoOpRiskManager(),
        config=config,
        decision_ts=events[-1].ts,
        market_data_source=StaticMarketDataSource([events[-1]]),
        ingest_market_data=False,
        portfolio=Portfolio.from_event_store(store, asof_ts=events[-1].ts),
    )

    conn = store.connection()
    assert conn.execute("SELECT COUNT(*) FROM signal_events").fetchone()[0] > 0
    assert conn.execute("SELECT COUNT(*) FROM indicator_events").fetchone()[0] > 0


def test_backtest_runner_supports_policy_driven_strategy(tmp_path: Path) -> None:
    store = DuckDBEventStore(str(tmp_path / "events.duckdb"))
    _seed_stock_bars(store, "AAPL", [10, 10, 10, 10, 10, 8, 8, 9, 10, 10, 10])
    strategy = build_mean_reversion_strategy(
        symbols=["AAPL"],
        asset_class="stocks",
        timeframe="1Min",
        rsi_period=5,
        mean_period=5,
        stretch_pct=0.05,
    )
    spec = BacktestSpec(
        start=datetime(2026, 1, 20, 12, 5, tzinfo=timezone.utc),
        end=datetime(2026, 1, 20, 12, 10, tzinfo=timezone.utc),
        timeframe="1Min",
    )
    runner = BacktestRunner(
        _config(tmp_path),
        spec,
        symbols=["AAPL"],
        asset_class="stocks",
        event_store=store,
        strategy=strategy,
        risk_manager=NoOpRiskManager(),
        initial_cash=1000.0,
    )

    result = runner.run()

    assert result.total_runs > 0
    assert result.success_runs == result.total_runs
