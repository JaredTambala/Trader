"""Exercise the typed replay recent-bar reader and strategy injection boundary.

Subject: Point-in-time replay bar reads and BacktestRunner reader construction.
Level: Deterministic unit and in-process strategy integration tests.
Collaborators: ``InMemoryRecentBarReader``, maintained Bollinger strategy, and a
no-op event store.
Guarantees: Reads are latest-first, bounded, as-of safe, metadata-scoped, and
usable without a database connection.
Non-goals: Database query-plan performance, Postgres qualification, or strategy
profitability.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from trader.backtest import InMemoryRecentBarReader
from trader.backtest import BacktestRunner, BacktestSpec
from trader.config import Config, build_config
from trader.event_store import NoOpEventStore
from trader.market_data import RecentBarRequest
from trader.signals import Bar
from trader.strategies import Strategy
from trader_standard.strategies import build_bollinger_band_strategy
from trader_standard.bar_signals import fetch_recent_bars
from trader_standard.risk import NoOpRiskManager
from trader.portfolio import Portfolio
from tests.support.duckdb_store import DuckDBEventStore


class _NoMarketDataConnectionStore(NoOpEventStore):
    """Fail if a strategy attempts to open a market-data connection."""

    def connection(self) -> object:
        """Reject the legacy SQL read path during replay-reader testing."""
        raise AssertionError("replay strategy requested an event-store connection")


def _bars(count: int = 25) -> list[Bar]:
    """Build chronological bars with distinct closes for window assertions."""
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [
        Bar(
            ts=start + timedelta(minutes=index),
            open=100.0 + index,
            high=101.0 + index,
            low=99.0 + index,
            close=100.0 + index,
            volume=1.0,
            vwap=None,
            trade_count=None,
        )
        for index in range(count)
    ]


def test_reader_returns_bounded_latest_first_as_of_window() -> None:
    """Exclude future bars and preserve warmup order in a bounded read."""
    bars = _bars()
    reader = InMemoryRecentBarReader(
        bars_by_symbol={"BTC/USD": bars},
        asset_class="crypto",
        timeframe="1Min",
    )

    window = reader.read(
        request=RecentBarRequest(
            symbol=" btc/usd ",
            asset_class="crypto",
            timeframe="1Min",
            as_of_ts=bars[10].ts,
            limit=4,
        )
    )

    assert [bar.close for bar in window] == [110.0, 109.0, 108.0, 107.0]
    assert reader.stats.request_count == 1
    assert reader.stats.query_count == 1
    assert reader.stats.bars_returned == 4


def test_reader_rejects_scope_mismatch() -> None:
    """Prevent a replay reader from silently serving a different data scope."""
    reader = InMemoryRecentBarReader(
        bars_by_symbol={"BTC/USD": _bars()},
        asset_class="crypto",
        timeframe="1Min",
    )

    with pytest.raises(ValueError, match="asset class mismatch"):
        reader.read(
            RecentBarRequest(
                symbol="BTC/USD",
                asset_class="stocks",
                timeframe="1Min",
                as_of_ts=_bars()[0].ts,
                limit=1,
            )
        )


def test_bollinger_strategy_uses_reader_without_event_store_connection() -> None:
    """Use the injected reader for strategy history when SQL access is absent."""
    bars = _bars()
    reader = InMemoryRecentBarReader(
        bars_by_symbol={"BTC/USD": bars},
        asset_class="crypto",
        timeframe="1Min",
    )
    strategy = build_bollinger_band_strategy(
        symbols=("BTC/USD",),
        asset_class="crypto",
        timeframe="1Min",
        period=20,
    )

    orders = strategy.generate_orders_with_recent_bar_reader(
        run_id="run",
        cycle_id="cycle",
        decision_ts=bars[-1].ts,
        event_store=_NoMarketDataConnectionStore(),
        portfolio=Portfolio.empty(cash_balance=1000.0),
        recent_bar_reader=reader,
    )

    assert orders == []
    assert reader.stats.request_count == 1


def test_reader_matches_database_window_order_and_cutoff(tmp_path: Path) -> None:
    """Keep the replay reader equivalent to the established database read path."""
    bars = _bars()
    store = DuckDBEventStore(str(tmp_path / "events.duckdb"))
    for bar in bars:
        store.record_event(
            "crypto_bar_events",
            {
                "symbol": "BTC/USD",
                "timeframe": "1Min",
                "ts": bar.ts,
                "ingested_at": bar.ts,
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume,
                "vwap": bar.vwap,
                "trade_count": bar.trade_count,
                "source": "test",
            },
        )
    reader = InMemoryRecentBarReader(
        bars_by_symbol={"BTC/USD": bars},
        asset_class="crypto",
        timeframe="1Min",
    )

    database_window = fetch_recent_bars(
        store,
        table="crypto_bar_events",
        symbol="BTC/USD",
        timeframe="1Min",
        limit=5,
        as_of_ts=bars[12].ts,
    )
    replay_window = reader.read(
        RecentBarRequest(
            symbol="BTC/USD",
            asset_class="crypto",
            timeframe="1Min",
            as_of_ts=bars[12].ts,
            limit=5,
        )
    )

    assert [(bar.ts.replace(tzinfo=timezone.utc), bar.close) for bar in replay_window] == [
        (bar.ts.replace(tzinfo=timezone.utc), bar.close) for bar in database_window
    ]


class _DatabasePathStrategy(Strategy):
    """Delegate to a maintained strategy while deliberately using its DB path."""

    def __init__(self, delegate: Strategy) -> None:
        self._delegate = delegate

    @property
    def strategy_id(self) -> str:
        return self._delegate.strategy_id

    @property
    def required_lookback(self) -> int:
        return self._delegate.required_lookback

    def generate_orders(self, **kwargs: object) -> list[dict[str, object]]:
        """Use the delegate's ordinary event-store reads for parity comparison."""
        return list(self._delegate.generate_orders(**kwargs))

    def generate_orders_with_recent_bar_reader(self, **kwargs: object) -> list[dict[str, object]]:
        """Ignore the replay reader to preserve the pre-optimization comparison path."""
        return self.generate_orders(**kwargs)


def _replay_config() -> Config:
    """Build the minimal backtest configuration used by the parity fixture."""
    return build_config(
        {
            "runtime": {"mode": "backtest"},
            "strategy": {"id": "bollinger_band", "type": "library", "timeframe": "1Min"},
            "market_data": {"source": "noop", "asset_class": "crypto", "symbols": ["BTC/USD"]},
            "broker": {"type": "internal", "internal": {"rng_seed": 241}},
            "database": {"event_store": "postgres", "buffering": {"enabled": False}},
            "logging": {
                "persist": {
                    "signals": True,
                    "indicators": True,
                    "orders": True,
                    "fills": True,
                    "positions": True,
                }
            },
        }
    )


def _seed_bars(store: DuckDBEventStore, bars: list[Bar]) -> None:
    """Seed the same immutable fixture into an isolated event store."""
    for bar in bars:
        store.record_event(
            "crypto_bar_events",
            {
                "symbol": "BTC/USD",
                "timeframe": "1Min",
                "ts": bar.ts,
                "ingested_at": bar.ts,
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume,
                "vwap": bar.vwap,
                "trade_count": bar.trade_count,
                "source": "test",
            },
        )


def test_replay_reader_preserves_backtest_result_against_database_strategy_path(tmp_path: Path) -> None:
    """Keep strategy orders and deterministic accounting identical across read paths."""
    bars = _bars(35)
    start = bars[0].ts
    spec = BacktestSpec(start=start, end=bars[-1].ts, timeframe="1Min")
    config = _replay_config()
    database_store = DuckDBEventStore(str(tmp_path / "database.duckdb"))
    replay_store = DuckDBEventStore(str(tmp_path / "replay.duckdb"))
    _seed_bars(database_store, bars)
    _seed_bars(replay_store, bars)

    database_result = BacktestRunner(
        config,
        spec,
        symbols=("BTC/USD",),
        asset_class="crypto",
        event_store=database_store,
        strategy=_DatabasePathStrategy(build_bollinger_band_strategy(
            symbols=("BTC/USD",), asset_class="crypto", timeframe="1Min", period=20
        )),
        risk_manager=NoOpRiskManager(),
        initial_cash=1000.0,
        run_id="parity-run",
        started_at=start,
    ).run()
    replay_result = BacktestRunner(
        config,
        spec,
        symbols=("BTC/USD",),
        asset_class="crypto",
        event_store=replay_store,
        strategy=build_bollinger_band_strategy(
            symbols=("BTC/USD",), asset_class="crypto", timeframe="1Min", period=20
        ),
        risk_manager=NoOpRiskManager(),
        initial_cash=1000.0,
        run_id="parity-run",
        started_at=start,
    ).run()

    assert replay_result.total_runs == database_result.total_runs
    assert replay_result.success_runs == database_result.success_runs
    assert replay_result.failed_runs == database_result.failed_runs
    assert replay_result.trades == database_result.trades
    assert replay_result.strategy_performance == database_result.strategy_performance
    assert replay_result.benchmark_performance == database_result.benchmark_performance
    assert replay_result.equity_curve == database_result.equity_curve
