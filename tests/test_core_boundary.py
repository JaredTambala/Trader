from __future__ import annotations

from datetime import datetime, timezone

import trader
import trader.cycle.core as cycle_module
from trader.config import Config
from trader.cycle import run_cycle
from trader.data import NoOpEventStore
from trader.market_data import StaticMarketDataSource, StockBarEvent
from trader.portfolio import Portfolio
from trader.risk import RiskContext, RiskManager
from trader.strategies import Strategy
import trader_standard


class RecordingEventStore(NoOpEventStore):
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, object]]] = []

    def record_event(self, event_type: str, payload: dict[str, object]) -> None:
        self.events.append((event_type, dict(payload)))


class AcceptAllRiskManager(RiskManager):
    def validate(self, orders, context: RiskContext):
        return list(orders)


class BuyOnceStrategy(Strategy):
    @property
    def strategy_id(self) -> str:
        return "buy-once"

    def generate_orders(self, *, run_id, cycle_id, decision_ts, event_store, portfolio):
        return [{"symbol": "AAPL", "side": "buy", "qty": 1.0, "order_type": "market"}]


def _config() -> Config:
    return Config(
        mode="once",
        strategy_type="buy-once",
        strategy_id="buy-once",
        strategy_timeframe="1Min",
        sma_short_window=2,
        sma_long_window=3,
        db_path="",
        event_store="noop",
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
        broker_type="noop",
    )


def test_trader_core_exports_contracts_not_standard_implementations() -> None:
    assert hasattr(trader, "Strategy")
    assert hasattr(trader, "RiskManager")
    assert hasattr(trader, "BacktestRunner")
    assert not hasattr(trader, "ToggleUnitStrategy")
    assert not hasattr(trader, "NoOpRiskManager")
    assert not hasattr(trader, "build_trend_following_strategy")

    assert hasattr(trader_standard, "ToggleUnitStrategy")
    assert hasattr(trader_standard, "NoOpRiskManager")
    assert hasattr(trader_standard, "build_trend_following_strategy")


def test_run_cycle_does_not_apply_hidden_open_buy_order_guard(monkeypatch) -> None:
    store = RecordingEventStore()
    decision_ts = datetime.now(timezone.utc)
    market_data = StaticMarketDataSource(
        [
            StockBarEvent(
                symbol="AAPL",
                timeframe="1Min",
                ts=decision_ts,
                ingested_at=decision_ts,
                open=100.0,
                high=101.0,
                low=99.0,
                close=100.5,
                volume=10.0,
                trade_count=None,
                vwap=None,
                source="test",
            )
        ]
    )
    existing_open_order = {
        "client_order_id": "existing_open_buy",
        "run_id": "run_existing",
        "cycle_id": "cycle_existing",
        "symbol": "AAPL",
        "side": "buy",
        "qty": 1.0,
        "order_type": "market",
        "status": "submitted",
        "broker_order_id": None,
        "created_at": decision_ts,
    }
    monkeypatch.setattr(
        cycle_module,
        "_load_latest_order_events",
        lambda event_store: [existing_open_order],
    )
    monkeypatch.setattr(cycle_module, "_load_halt_flag", lambda event_store: False)

    result = run_cycle(
        event_store=store,
        strategy=BuyOnceStrategy(),
        risk_manager=AcceptAllRiskManager(),
        market_data_source=market_data,
        config=_config(),
        decision_ts=decision_ts,
        ingest_market_data=False,
        portfolio=Portfolio.empty(cash_balance=1000.0),
    )

    assert result.status == "success"
    order_statuses = [
        payload["status"]
        for event_type, payload in store.events
        if event_type == "order_events"
    ]
    assert order_statuses == ["created", "validated", "submitted"]
