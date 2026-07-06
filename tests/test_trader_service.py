"""Tests for the trader service runner."""

from __future__ import annotations

import pytest

from trader.config import Config
from trader.event_store import NoOpEventStore
from trader.runtime.service import TraderService
from tests.support.duckdb_store import DuckDBEventStore
from trader_standard.risk import NoOpRiskManager
from trader_standard.strategies.noop import NoOpStrategy


class CycleRecorder:
    def __init__(self) -> None:
        self.calls = 0
        self.kwargs: list[dict[str, object]] = []

    def __call__(self, *args, **kwargs) -> None:
        self.calls += 1
        self.kwargs.append(kwargs)


class FakeAlpacaBroker:
    def __init__(self) -> None:
        self.list_calls = 0

    def list_orders(self):
        self.list_calls += 1
        return []

    def get_account(self):
        return {"cash": "100000"}

    def get_positions(self):
        return [
            {
                "symbol": "BTC",
                "asset_class": "us_equity",
                "qty": "-1",
                "avg_entry_price": "39.77",
                "side": "short",
            }
        ]


class FakeReconcileBroker:
    def __init__(self) -> None:
        self.reconcile_calls = 0

    def reconcile_orders(self):
        self.reconcile_calls += 1
        return [{"client_order_id": "cid_1", "status": "filled"}]

    def submit_orders(self, orders):
        return []


def _config() -> Config:
    return Config(
        mode="loop",
        strategy_type="noop",
        strategy_id="noop",
        strategy_timeframe="1Min",
        sma_short_window=2,
        sma_long_window=3,
        db_path=":memory:",
        event_store="postgres",
        market_data_source="noop",
        market_data_asset_class="stocks",
        market_data_stock_feed="iex",
        market_data_symbols=(),
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
        broker_type="noop",
    )


def test_trader_service_loop_runs_expected_iterations(monkeypatch) -> None:
    recorder = CycleRecorder()
    broker = object()
    monkeypatch.setattr("trader.runtime.service.run_cycle", recorder)
    monkeypatch.setattr("trader.runtime.service.build_runtime_broker", lambda config, event_store: broker)

    service = TraderService(
        _config(),
        event_store=NoOpEventStore(),
        cadence_seconds=0.0,
        max_iterations=3,
        strategy=NoOpStrategy(),
        risk_manager=NoOpRiskManager(),
    )
    service.run()

    assert recorder.calls == 3
    assert all(call["broker"] is broker for call in recorder.kwargs)


def test_trader_service_requires_injected_risk_manager() -> None:
    with pytest.raises(TypeError):
        TraderService(
            _config(),
            event_store=NoOpEventStore(),
            strategy=NoOpStrategy(),
        )


def test_trader_service_fails_closed_on_broker_position_mismatch(monkeypatch) -> None:
    broker = FakeAlpacaBroker()
    config = _config()
    config = Config(
        **{
            **config.__dict__,
            "broker_type": "alpaca",
            "market_data_asset_class": "crypto",
            "market_data_symbols": ("BTC/USD",),
        }
    )
    monkeypatch.setattr("trader.runtime.service.build_runtime_broker", lambda config, event_store: broker)
    monkeypatch.setattr("trader.runtime.service.run_cycle", CycleRecorder())

    service = TraderService(
        config,
        event_store=NoOpEventStore(),
        cadence_seconds=0.0,
        max_iterations=1,
        strategy=NoOpStrategy(),
        risk_manager=NoOpRiskManager(),
    )

    with pytest.raises(ValueError, match="Broker portfolio mismatch"):
        service.run()

    assert broker.list_calls == 1


def test_trader_service_resets_local_portfolio_from_alpaca_before_mismatch_failure(monkeypatch, tmp_path) -> None:
    broker = FakeAlpacaBroker()
    store = DuckDBEventStore(str(tmp_path / "events.duckdb"))
    store.record_event(
        "position_snapshots",
        {
            "asof_ts": "2026-01-01T00:00:00+00:00",
            "symbol": "ETH/USD",
            "qty": 5.0,
            "avg_price": 2000.0,
            "cash_balance": 12345.0,
            "run_id": "run_old",
            "cycle_id": "cycle_old",
            "session_id": "run_old",
        },
    )
    config = _config()
    config = Config(
        **{
            **config.__dict__,
            "broker_type": "alpaca",
            "market_data_asset_class": "crypto",
            "market_data_symbols": ("BTC/USD",),
        }
    )
    monkeypatch.setattr("trader.runtime.service.build_runtime_broker", lambda config, event_store: broker)
    monkeypatch.setattr("trader.runtime.service.run_cycle", CycleRecorder())

    service = TraderService(
        config,
        event_store=store,
        cadence_seconds=0.0,
        max_iterations=1,
        strategy=NoOpStrategy(),
        risk_manager=NoOpRiskManager(),
    )

    with pytest.raises(ValueError, match="Broker portfolio mismatch"):
        service.run()

    rows = store.connection().execute(
        """
        SELECT symbol, qty, avg_price, cash_balance
        FROM position_snapshots
        ORDER BY asof_ts DESC, symbol
        """
    ).fetchall()
    assert rows == [("BTC", -1.0, 39.77, 100000.0)]


def test_trader_service_periodic_reconcile_uses_broker_capability(monkeypatch) -> None:
    broker = FakeReconcileBroker()
    config = Config(
        **{
            **_config().__dict__,
            "trader_service_order_reconciliation_interval_seconds": 60,
        }
    )
    monkeypatch.setattr("trader.runtime.service.build_runtime_broker", lambda config, event_store: broker)

    service = TraderService(
        config,
        event_store=NoOpEventStore(),
        cadence_seconds=0.0,
        max_iterations=1,
        strategy=NoOpStrategy(),
        risk_manager=NoOpRiskManager(),
    )

    service._maybe_reconcile_orders(run_id="run_1", force=True)

    assert broker.reconcile_calls == 1
