"""Tests for cycle event persistence and order lifecycle."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from dataclasses import replace

import pytest

from trader.cycle import (
    assess_market_data_event_freshness,
    assess_market_data_readiness,
    build_enriched_cycle_order,
    build_broker_fill_event_payload,
    build_broker_response_recording_plan,
    build_metrics_snapshot_event,
    build_metrics_snapshot_payload,
    build_order_lifecycle_event_payload,
    normalize_cycle_order_intent,
    resolve_order_lifecycle_event_timestamp,
    resolve_terminal_event_timestamp,
    run_cycle,
)
from trader.cycle.broker_state import (
    _build_cycle_broker_response_plan,
    _build_portfolio_from_broker_payload,
    _build_processed_order_from_broker_response,
    _broker_position_views_to_positions,
    _coerce_broker_cash,
    _resolve_broker_response_status,
    _should_sync_portfolio_for_broker_response,
)
from trader.cycle.filters import _allowed_cycle_event_types
from trader.cycle.lifecycle import (
    _build_cycle_execution_plan,
    _build_cycle_identity,
    _build_cycle_run_session_outcome,
    _build_post_order_portfolio_snapshot_plan,
    _resolve_cycle_run_type,
    _resolve_cycle_snapshot_ts,
    _resolve_decision_ts,
    _resolve_market_data_freshness_ts,
    _resolve_portfolio_asof_ts,
    _should_halt_cycle,
    _should_load_broker_portfolio,
    _should_use_stream_ingestion,
)
from trader.cycle.market_data import (
    _build_recent_market_data_query,
    _empty_market_data_pipeline_result,
    _market_data_event_table_name,
    _row_to_market_event,
)
from trader.cycle.metrics import _resolve_metrics_price_lookup
from trader.cycle.order_state import (
    _dedupe_latest_order_event_rows,
    _latest_order_event_row_to_record,
    _latest_order_events_query,
)
from trader.cycle.orders import _attach_order_metadata
from trader.cycle.portfolio_updates import build_internal_fill_portfolio_application
from trader.cycle.risk import (
    _build_cycle_risk_context,
    _build_stream_risk_price_lookup,
    _evaluate_cycle_order_risk,
)
from trader.cycle.recording import (
    _record_owned_run_session_finish,
    _record_owned_run_session_start,
)
from trader.cycle.stream import _build_cycle_stream_state, _latest_stream_prices, _plan_cycle_stream_market_event
from trader.cycle.stream import CycleStreamRuntime
from trader.cycle.stream_pipeline import _generate_universe_snapshot_orders
from trader.cycle.startup import _mask_secret, _startup_config_log_values
from trader.identifiers import deterministic_client_order_id, deterministic_run_session_id
from trader.config import Config
from trader.market_data import CryptoBarEvent, StaticMarketDataSource, StockBarEvent
from trader.portfolio import Portfolio, Position
from trader.risk import RiskContext, RiskManager
from trader.signals import Bar
from trader.strategies import Strategy
from trader.symbols import BrokerPositionView
from tests.support.duckdb_store import DuckDBEventStore
from trader_standard.indicators import SmaIndicator
from trader_standard.risk import NoOpRiskManager
from trader_standard.signal_generators import InMemoryBarsSignalGenerator
from trader_standard.signals import SmaCrossoverSignal
from trader_standard.strategies import SimpleStrategy


class SingleOrderStrategy(Strategy):
    """Strategy that always emits a single buy order."""

    @property
    def strategy_id(self) -> str:
        return "single_order"

    def generate_orders(
        self,
        *,
        run_id: str,
        cycle_id: str,
        decision_ts: datetime,
        event_store,
        portfolio,
    ):
        return [
            {
                "symbol": "AAPL",
                "side": "buy",
                "qty": 1.0,
                "order_type": "market",
            }
        ]


class UniverseOrderStrategy(Strategy):
    """Record synchronized callbacks and emit one order per configured symbol."""

    def __init__(self) -> None:
        self.calls: list[datetime] = []

    @property
    def strategy_id(self) -> str:
        return "universe_order"

    @property
    def decision_scope(self) -> str:
        return "universe_snapshot"

    def generate_orders(
        self,
        *,
        run_id: str,
        cycle_id: str,
        decision_ts: datetime,
        event_store,
        portfolio,
    ):
        del run_id, cycle_id, event_store, portfolio
        self.calls.append(decision_ts)
        return [
            {"symbol": symbol, "side": "buy", "qty": 1.0, "order_type": "market"}
            for symbol in ("AAPL", "MSFT")
        ]


class _UnusedBroker:
    def submit_orders(self, orders):
        del orders
        return ()


class RejectSymbolRiskManager(RiskManager):
    """Test risk manager that rejects one configured symbol."""

    def __init__(self, symbol: str, reason: str) -> None:
        self.symbol = symbol
        self.reason = reason

    def validate(
        self,
        orders,
        context: RiskContext,
    ):
        del context
        return [order for order in orders if order.get("symbol") != self.symbol]

    def evaluate(
        self,
        orders,
        context: RiskContext,
    ):
        del context
        approved = []
        rejected = []
        for order in orders:
            if order.get("symbol") == self.symbol:
                rejected.append({**order, "rejection_reason": self.reason})
            else:
                approved.append(order)
        return approved, rejected


class RunSessionRecorder:
    """Minimal event-store recorder for run-session helper tests."""

    def __init__(self) -> None:
        self.starts: list[dict[str, object]] = []
        self.finishes: list[dict[str, object]] = []

    def record_run_session_start(self, **kwargs) -> None:
        self.starts.append(dict(kwargs))

    def record_run_session_finish(self, **kwargs) -> None:
        self.finishes.append(dict(kwargs))


def _stock_event(*, ts: datetime, close: float = 100.0) -> StockBarEvent:
    return StockBarEvent(
        symbol="AAPL",
        timeframe="1Min",
        ts=ts,
        ingested_at=ts,
        open=close,
        high=close,
        low=close,
        close=close,
        volume=1.0,
        trade_count=None,
        vwap=None,
        source="test",
    )


def test_assess_market_data_readiness_blocks_missing_market_data() -> None:
    now = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)

    readiness = assess_market_data_readiness([], now=now, max_age_seconds=60)

    assert readiness.should_skip is True
    assert readiness.latest_ts is None
    assert readiness.age_seconds is None
    assert readiness.is_stale is False
    assert readiness.reason == "missing_market_data"


def test_assess_market_data_readiness_reports_fresh_latest_event() -> None:
    now = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    older = _stock_event(ts=now - timedelta(seconds=30), close=99.0)
    latest = _stock_event(ts=now - timedelta(seconds=10), close=101.0)

    readiness = assess_market_data_readiness([older, latest], now=now, max_age_seconds=60)

    assert readiness.should_skip is False
    assert readiness.latest_ts == latest.ts
    assert readiness.age_seconds == 10.0
    assert readiness.is_stale is False
    assert readiness.reason is None


def test_assess_market_data_readiness_reports_stale_latest_event_and_normalizes_now() -> None:
    now = datetime(2026, 1, 20, 12, 0)
    latest = _stock_event(ts=datetime(2026, 1, 20, 11, 58, tzinfo=timezone.utc))

    readiness = assess_market_data_readiness([latest], now=now, max_age_seconds=60)

    assert readiness.should_skip is True
    assert readiness.latest_ts == latest.ts
    assert readiness.age_seconds == 120.0
    assert readiness.is_stale is True
    assert readiness.reason == "stale_market_data"


def test_assess_market_data_readiness_rejects_negative_staleness_window() -> None:
    now = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)

    with pytest.raises(ValueError, match="max_age_seconds must be non-negative"):
        assess_market_data_readiness([_stock_event(ts=now)], now=now, max_age_seconds=-1)


def test_assess_market_data_event_freshness_reports_fresh_event() -> None:
    now = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    event = _stock_event(ts=now - timedelta(seconds=5))

    freshness = assess_market_data_event_freshness(event, now=now, max_age_seconds=60)

    assert freshness.ts == event.ts
    assert freshness.age_seconds == 5.0
    assert freshness.max_age_seconds == 60
    assert freshness.is_stale is False


def test_assess_market_data_event_freshness_reports_stale_event_and_normalizes_now() -> None:
    event_ts = datetime(2026, 1, 20, 11, 58, tzinfo=timezone.utc)
    now = datetime(2026, 1, 20, 12, 0)

    freshness = assess_market_data_event_freshness(
        _stock_event(ts=event_ts),
        now=now,
        max_age_seconds=60,
    )

    assert freshness.ts == event_ts
    assert freshness.age_seconds == 120.0
    assert freshness.is_stale is True


def test_assess_market_data_event_freshness_rejects_negative_staleness_window() -> None:
    now = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)

    with pytest.raises(ValueError, match="max_age_seconds must be non-negative"):
        assess_market_data_event_freshness(_stock_event(ts=now), now=now, max_age_seconds=-1)


def test_build_metrics_snapshot_payload_excludes_unpriced_positions() -> None:
    positions = {
        "AAPL": Position(symbol="AAPL", qty=2.0, avg_price=90.0),
        "MSFT": Position(symbol="MSFT", qty=-1.0, avg_price=200.0),
        "NVDA": Position(symbol="NVDA", qty=5.0, avg_price=50.0),
    }

    payload = build_metrics_snapshot_payload(
        positions=positions,
        cash_balance=1000.0,
        price_lookup={"AAPL": 100.0, "MSFT": 250.0},
        asset_class="stocks",
        symbols=("AAPL", "MSFT", "NVDA"),
    )

    assert payload.equity == 950.0
    assert payload.cash == 1000.0
    assert payload.net_exposure == -50.0
    assert payload.gross_exposure == 450.0
    assert payload.to_payload() == {
        "equity": 950.0,
        "cash": 1000.0,
        "net_exposure": -50.0,
        "gross_exposure": 450.0,
        "asset_class": "stocks",
        "symbols": ["AAPL", "MSFT", "NVDA"],
    }


def test_build_metrics_snapshot_event_serializes_payload_deterministically() -> None:
    asof_ts = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)

    event = build_metrics_snapshot_event(
        positions={"AAPL": Position(symbol="AAPL", qty=1.0, avg_price=90.0)},
        cash_balance=500.0,
        price_lookup={"AAPL": 125.0},
        asof_ts=asof_ts,
        run_id="run_1",
        cycle_id="cycle_1",
        asset_class="stocks",
        symbols=("AAPL",),
    )

    record = event.to_record()
    assert record["ts"] == asof_ts
    assert record["run_id"] == "run_1"
    assert record["session_id"] == "run_1"
    assert record["cycle_id"] == "cycle_1"
    assert json.loads(str(record["payload"])) == {
        "equity": 625.0,
        "cash": 500.0,
        "net_exposure": 125.0,
        "gross_exposure": 125.0,
        "asset_class": "stocks",
        "symbols": ["AAPL"],
    }


def test_resolve_metrics_price_lookup_prefers_stream_prices_and_falls_back_to_events() -> None:
    base_ts = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    older = _stock_event(ts=base_ts - timedelta(minutes=1), close=99.0)
    latest = _stock_event(ts=base_ts, close=101.0)

    assert (
        _resolve_metrics_price_lookup(
            price_lookup={"AAPL": 105.0},
            market_data_events=[older, latest],
        )
        == {"AAPL": 105.0}
    )
    assert (
        _resolve_metrics_price_lookup(
            price_lookup={},
            market_data_events=[older, latest],
        )
        == {"AAPL": 101.0}
    )
    assert _resolve_metrics_price_lookup(price_lookup={}, market_data_events=[]) == {}


def test_normalize_cycle_order_intent_preserves_source_without_mutation() -> None:
    order = {"symbol": " aapl ", "side": " BUY ", "qty": "2.5"}
    original = dict(order)

    intent = normalize_cycle_order_intent(order)

    assert order == original
    assert intent.source is order
    assert intent.symbol == "AAPL"
    assert intent.side == "buy"
    assert intent.qty == 2.5


def test_build_enriched_cycle_order_attaches_deterministic_metadata() -> None:
    created_at = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    order = {"symbol": " aapl ", "side": " BUY ", "qty": "2.5"}
    original = dict(order)

    enriched = build_enriched_cycle_order(
        order,
        run_id="run_1",
        cycle_id="cycle_1",
        created_at=created_at,
        price_lookup={"AAPL": 101.25},
        asset_class="stocks",
        time_in_force="day",
    )

    assert order == original
    assert enriched.to_record() == {
        **order,
        "symbol": "AAPL",
        "run_id": "run_1",
        "session_id": "run_1",
        "cycle_id": "cycle_1",
        "client_order_id": deterministic_client_order_id("cycle_1", "AAPL", "buy", 2.5),
        "price": 101.25,
        "created_at": created_at,
        "asset_class": "stocks",
        "time_in_force": "day",
    }


def test_build_enriched_cycle_order_preserves_explicit_order_fields() -> None:
    created_at = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    explicit_created_at = created_at.replace(hour=13)
    order = {
        "symbol": "MSFT",
        "side": "sell",
        "qty": 1.0,
        "client_order_id": "cid_explicit",
        "created_at": explicit_created_at,
        "time_in_force": "gtc",
    }

    enriched = build_enriched_cycle_order(
        order,
        run_id="run_1",
        cycle_id="cycle_1",
        created_at=created_at,
        price_lookup={},
        asset_class="stocks",
        time_in_force="day",
    )

    record = enriched.to_record()
    assert record["client_order_id"] == "cid_explicit"
    assert record["created_at"] == explicit_created_at
    assert record["time_in_force"] == "gtc"
    assert record["price"] is None


def test_attach_order_metadata_enriches_batch_without_mutating_inputs() -> None:
    created_at = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    orders = [
        {"symbol": " aapl ", "side": "BUY", "qty": "2"},
        {"symbol": "MSFT", "side": "sell", "qty": 1.5, "time_in_force": "gtc"},
    ]
    originals = [dict(order) for order in orders]

    enriched = _attach_order_metadata(
        orders,
        run_id="run_1",
        cycle_id="cycle_1",
        created_at=created_at,
        price_lookup={"AAPL": 101.0, "MSFT": 250.0},
        asset_class="stocks",
        time_in_force="day",
    )

    assert orders == originals
    assert [order["symbol"] for order in enriched] == ["AAPL", "MSFT"]
    assert [order["price"] for order in enriched] == [101.0, 250.0]
    assert [order["time_in_force"] for order in enriched] == ["day", "gtc"]
    assert enriched[0]["client_order_id"] == deterministic_client_order_id(
        "cycle_1",
        "AAPL",
        "buy",
        2.0,
    )


def test_resolve_order_lifecycle_event_timestamp_is_pure_and_stably_ordered() -> None:
    base_ts = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    fallback_ts = base_ts + timedelta(minutes=5)
    order = {"created_at": base_ts}

    assert (
        resolve_order_lifecycle_event_timestamp(order, status="created", fallback_ts=fallback_ts)
        == base_ts
    )
    assert (
        resolve_order_lifecycle_event_timestamp(order, status="validated", fallback_ts=fallback_ts)
        == base_ts + timedelta(microseconds=1)
    )
    assert (
        resolve_order_lifecycle_event_timestamp(order, status="submitted", fallback_ts=fallback_ts)
        == base_ts + timedelta(microseconds=2)
    )
    explicit_ts = base_ts + timedelta(seconds=10)
    assert (
        resolve_order_lifecycle_event_timestamp(
            order,
            status="created",
            fallback_ts=fallback_ts,
            event_ts=explicit_ts,
        )
        == explicit_ts
    )
    assert (
        resolve_order_lifecycle_event_timestamp({}, status="created", fallback_ts=fallback_ts)
        == fallback_ts
    )


def test_build_order_lifecycle_event_payload_does_not_mutate_input() -> None:
    created_at = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    order = {
        "client_order_id": "cid_1",
        "run_id": "run_1",
        "cycle_id": "cycle_1",
        "symbol": "AAPL",
        "side": "buy",
        "qty": 1.0,
        "rejection_reason": "risk_limit",
    }
    original = dict(order)

    payload = build_order_lifecycle_event_payload(
        order,
        status="rejected",
        broker_order_id=None,
        created_at=created_at,
        order_event_id="order_evt_fixed",
    )

    assert order == original
    assert payload.to_record() == {
        "order_event_id": "order_evt_fixed",
        "client_order_id": "cid_1",
        "run_id": "run_1",
        "session_id": "run_1",
        "cycle_id": "cycle_1",
        "symbol": "AAPL",
        "side": "buy",
        "qty": 1.0,
        "order_type": "market",
        "status": "rejected",
        "broker_order_id": None,
        "rejection_reason": "risk_limit",
        "decision_evidence": None,
        "created_at": created_at,
    }


def test_build_broker_fill_event_payload_returns_fill_record_or_none() -> None:
    fill_ts = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    order = {
        "run_id": "run_1",
        "cycle_id": "cycle_1",
        "qty": 2.0,
        "price": 100.0,
    }
    response = {
        "client_order_id": "cid_1",
        "fill_qty": "1.5",
        "fill_price": "100.25",
        "raw_fill_price": 100.0,
        "slippage_amount": 0.375,
        "fee_amount": 0.1,
    }

    payload = build_broker_fill_event_payload(order, response, fill_ts=fill_ts)

    assert payload is not None
    assert payload.to_record() == {
        "client_order_id": "cid_1",
        "run_id": "run_1",
        "session_id": "run_1",
        "cycle_id": "cycle_1",
        "fill_ts": fill_ts,
        "fill_qty": 1.5,
        "raw_fill_price": 100.0,
        "fill_price": 100.25,
        "slippage_amount": 0.375,
        "fee_amount": 0.1,
    }
    assert (
        build_broker_fill_event_payload(
            order,
            {"client_order_id": "cid_1", "fill_price": None},
            fill_ts=fill_ts,
        )
        is None
    )


def test_build_broker_response_recording_plan_prepares_order_and_fill_records() -> None:
    terminal_ts = datetime(2026, 1, 20, 12, 0, 3, tzinfo=timezone.utc)
    order = {
        "client_order_id": "cid_1",
        "run_id": "run_1",
        "cycle_id": "cycle_1",
        "symbol": "AAPL",
        "side": "buy",
        "qty": 2.0,
        "order_type": "market",
        "price": 100.0,
    }
    response = {
        "client_order_id": "cid_1",
        "status": "filled",
        "broker_order_id": "broker_1",
        "fill_qty": 2.0,
        "fill_price": 101.0,
        "raw_fill_price": 100.0,
        "slippage_amount": 2.0,
        "fee_amount": 0.25,
    }

    plan = build_broker_response_recording_plan(
        order,
        response,
        terminal_ts=terminal_ts,
        order_event_id="order_evt_fixed",
    )

    assert plan.order_event.to_record() == {
        "order_event_id": "order_evt_fixed",
        "client_order_id": "cid_1",
        "run_id": "run_1",
        "session_id": "run_1",
        "cycle_id": "cycle_1",
        "symbol": "AAPL",
        "side": "buy",
        "qty": 2.0,
        "order_type": "market",
        "status": "filled",
        "broker_order_id": "broker_1",
        "rejection_reason": None,
        "decision_evidence": None,
        "created_at": terminal_ts,
    }
    assert plan.fill_event is not None
    assert plan.fill_event.to_record() == {
        "client_order_id": "cid_1",
        "run_id": "run_1",
        "session_id": "run_1",
        "cycle_id": "cycle_1",
        "fill_ts": terminal_ts,
        "fill_qty": 2.0,
        "raw_fill_price": 100.0,
        "fill_price": 101.0,
        "slippage_amount": 2.0,
        "fee_amount": 0.25,
    }
    assert plan.missing_fill_evidence is False


def test_build_broker_response_recording_plan_flags_missing_fill_evidence() -> None:
    terminal_ts = datetime(2026, 1, 20, 12, 0, 3, tzinfo=timezone.utc)

    plan = build_broker_response_recording_plan(
        {
            "client_order_id": "cid_1",
            "run_id": "run_1",
            "cycle_id": "cycle_1",
            "symbol": "AAPL",
            "side": "buy",
            "qty": 2.0,
        },
        {
            "client_order_id": "cid_1",
            "status": "filled",
            "fill_qty": None,
            "fill_price": None,
        },
        terminal_ts=terminal_ts,
        order_event_id="order_evt_missing_fill",
    )

    assert plan.order_event.status == "filled"
    assert plan.fill_event is None
    assert plan.missing_fill_evidence is True


def test_resolve_terminal_event_timestamp_preserves_later_broker_time() -> None:
    latest_ts = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    proposed_ts = latest_ts + timedelta(seconds=1)
    fallback_ts = latest_ts + timedelta(minutes=1)

    assert (
        resolve_terminal_event_timestamp(
            proposed_ts=proposed_ts,
            latest_order_ts=latest_ts,
            fallback_ts=fallback_ts,
        )
        == proposed_ts
    )


def test_resolve_terminal_event_timestamp_nudges_stale_or_equal_time() -> None:
    latest_ts = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)

    assert (
        resolve_terminal_event_timestamp(
            proposed_ts=latest_ts,
            latest_order_ts=latest_ts,
            fallback_ts=latest_ts + timedelta(minutes=1),
        )
        == latest_ts + timedelta(microseconds=1)
    )
    assert (
        resolve_terminal_event_timestamp(
            proposed_ts=latest_ts - timedelta(seconds=1),
            latest_order_ts=latest_ts,
            fallback_ts=latest_ts + timedelta(minutes=1),
        )
        == latest_ts + timedelta(microseconds=1)
    )


def test_resolve_terminal_event_timestamp_uses_fallback_and_normalizes_naive_datetimes() -> None:
    latest_ts = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    fallback_ts = latest_ts + timedelta(seconds=10)
    naive_proposed_ts = datetime(2026, 1, 20, 12, 0, 20)

    assert (
        resolve_terminal_event_timestamp(
            proposed_ts=None,
            latest_order_ts=latest_ts,
            fallback_ts=fallback_ts,
        )
        == fallback_ts
    )
    assert (
        resolve_terminal_event_timestamp(
            proposed_ts=naive_proposed_ts,
            latest_order_ts=None,
            fallback_ts=fallback_ts,
        )
        == naive_proposed_ts.replace(tzinfo=timezone.utc)
    )


def test_resolve_cycle_run_type_uses_mode_and_explicit_override() -> None:
    assert _resolve_cycle_run_type("backtest", None) == "backtest"
    assert _resolve_cycle_run_type("once", None) == "trading"
    assert _resolve_cycle_run_type("once", "BACKTEST") == "backtest"
    assert _resolve_cycle_run_type("backtest", "TRADING") == "trading"


def test_build_cycle_execution_plan_captures_shell_decisions() -> None:
    plan = _build_cycle_execution_plan(
        mode="backtest",
        broker_type="internal",
        portfolio_source="",
        run_type=None,
    )

    assert plan.run_type == "backtest"
    assert plan.broker_kind == "internal"
    assert plan.stream_mode is False
    assert plan.sync_portfolio_on_fill is True
    assert plan.portfolio_source == ""
    assert _should_load_broker_portfolio(plan) is False

    live_alpaca_plan = _build_cycle_execution_plan(
        mode="once",
        broker_type="ALPACA",
        portfolio_source="alpaca",
        run_type=None,
    )

    assert live_alpaca_plan.run_type == "trading"
    assert live_alpaca_plan.broker_kind == "alpaca"
    assert live_alpaca_plan.stream_mode is True
    assert live_alpaca_plan.sync_portfolio_on_fill is True
    assert _should_load_broker_portfolio(live_alpaca_plan) is True


def test_build_cycle_identity_is_deterministic_and_preserves_explicit_run_id() -> None:
    decision_ts = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    started_at = datetime(2026, 1, 20, 12, 1, tzinfo=timezone.utc)

    owned = _build_cycle_identity(
        strategy_id="strategy_1",
        decision_ts=decision_ts,
        run_type="trading",
        started_at=started_at,
        run_id=None,
    )

    assert owned.run_id == deterministic_run_session_id("trading", started_at)
    assert owned.owns_run_session is True
    assert owned.cycle_id

    explicit = _build_cycle_identity(
        strategy_id="strategy_1",
        decision_ts=decision_ts,
        run_type="trading",
        started_at=started_at,
        run_id="run_existing",
    )

    assert explicit.run_id == "run_existing"
    assert explicit.cycle_id == owned.cycle_id
    assert explicit.owns_run_session is False


def test_cycle_run_session_outcome_and_recording_helpers() -> None:
    recorder = RunSessionRecorder()
    started_at = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    success = _build_cycle_run_session_outcome("success")
    failed = _build_cycle_run_session_outcome("failed", "boom")

    _record_owned_run_session_start(
        event_store=recorder,
        owns_run_session=False,
        run_id="run_ignored",
        run_type="trading",
        started_at=started_at,
        strategy_id="strategy_ignored",
        config_snapshot=None,
        mode="once",
        symbols=("AAPL",),
        timeframe="1Min",
    )
    _record_owned_run_session_finish(
        event_store=recorder,
        owns_run_session=False,
        run_id="run_ignored",
        run_type="trading",
        started_at=started_at,
        outcome=success,
        strategy_id="strategy_ignored",
        mode="once",
        symbols=("AAPL",),
        timeframe="1Min",
    )

    assert recorder.starts == []
    assert recorder.finishes == []
    assert success.status == "success"
    assert success.error_message is None
    assert failed.status == "failed"
    assert failed.error_message == "boom"

    _record_owned_run_session_start(
        event_store=recorder,
        owns_run_session=True,
        run_id="run_1",
        run_type="trading",
        started_at=started_at,
        strategy_id="strategy_1",
        config_snapshot={"mode": "once"},
        mode="once",
        symbols=("AAPL",),
        timeframe="1Min",
    )
    _record_owned_run_session_finish(
        event_store=recorder,
        owns_run_session=True,
        run_id="run_1",
        run_type="trading",
        started_at=started_at,
        outcome=failed,
        strategy_id="strategy_1",
        mode="once",
        symbols=("AAPL",),
        timeframe="1Min",
    )

    assert recorder.starts == [
        {
            "run_id": "run_1",
            "run_type": "trading",
            "started_at": started_at,
            "strategy_id": "strategy_1",
            "config_snapshot": {"mode": "once"},
            "mode": "once",
            "symbols": ("AAPL",),
            "timeframe": "1Min",
        }
    ]
    assert len(recorder.finishes) == 1
    assert recorder.finishes[0]["run_id"] == "run_1"
    assert recorder.finishes[0]["run_type"] == "trading"
    assert recorder.finishes[0]["started_at"] == started_at
    assert recorder.finishes[0]["status"] == "failed"
    assert recorder.finishes[0]["error_message"] == "boom"
    assert recorder.finishes[0]["strategy_id"] == "strategy_1"
    assert recorder.finishes[0]["mode"] == "once"
    assert recorder.finishes[0]["symbols"] == ("AAPL",)
    assert recorder.finishes[0]["timeframe"] == "1Min"
    assert isinstance(recorder.finishes[0]["finished_at"], datetime)


def test_resolve_decision_ts_uses_current_time_and_normalizes_naive_values() -> None:
    current_ts = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    naive_ts = datetime(2026, 1, 20, 13, 0)

    assert _resolve_decision_ts(None, current_ts=current_ts) == current_ts
    assert _resolve_decision_ts(naive_ts, current_ts=current_ts) == naive_ts.replace(
        tzinfo=timezone.utc
    )


def test_should_halt_cycle_never_halts_backtests() -> None:
    assert _should_halt_cycle(run_type="trading", halted=True) is True
    assert _should_halt_cycle(run_type="trading", halted=False) is False
    assert _should_halt_cycle(run_type="backtest", halted=True) is False


def test_cycle_timestamp_resolvers_keep_backtest_time_deterministic() -> None:
    decision_ts = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    current_ts = decision_ts + timedelta(minutes=5)

    assert _resolve_portfolio_asof_ts("backtest", decision_ts) == decision_ts
    assert _resolve_portfolio_asof_ts("once", decision_ts) is None
    assert (
        _resolve_cycle_snapshot_ts(
            mode="backtest",
            decision_ts=decision_ts,
            current_ts=current_ts,
        )
        == decision_ts
    )
    assert (
        _resolve_cycle_snapshot_ts(
            mode="once",
            decision_ts=decision_ts,
            current_ts=current_ts,
        )
        == current_ts
    )


def test_post_order_portfolio_snapshot_plan_selects_side_effect_path() -> None:
    orders = [{"symbol": "AAPL", "side": "buy", "qty": 1.0}]

    assert (
        _build_post_order_portfolio_snapshot_plan(
            processed_orders=[],
            sync_portfolio_on_fill=False,
            broker_kind="noop",
        ).action
        == "none"
    )
    assert (
        _build_post_order_portfolio_snapshot_plan(
            processed_orders=orders,
            sync_portfolio_on_fill=True,
            broker_kind="alpaca",
        ).action
        == "skip_alpaca_synced"
    )
    assert (
        _build_post_order_portfolio_snapshot_plan(
            processed_orders=orders,
            sync_portfolio_on_fill=True,
            broker_kind="internal",
        ).action
        == "persist_broker_fill_snapshot"
    )
    assert (
        _build_post_order_portfolio_snapshot_plan(
            processed_orders=orders,
            sync_portfolio_on_fill=False,
            broker_kind="noop",
        ).action
        == "persist_order_intent_snapshot"
    )


def test_broker_portfolio_payload_helpers_build_runtime_portfolio() -> None:
    config = _base_config(":memory:")
    views = [
        BrokerPositionView(
            symbol="AAPL",
            asset_class="stocks",
            qty=2.0,
            avg_entry_price=95.0,
            side="long",
            raw_symbol="AAPL",
            raw_asset_class="us_equity",
        )
    ]

    positions = _broker_position_views_to_positions(views)
    portfolio = _build_portfolio_from_broker_payload(
        account={"cash": "1234.50"},
        positions_raw=[
            {
                "symbol": "AAPL",
                "asset_class": "us_equity",
                "qty": "2",
                "avg_entry_price": "95",
                "side": "long",
            }
        ],
        config=config,
    )

    assert _coerce_broker_cash({"cash": "1234.50"}) == 1234.5
    assert _coerce_broker_cash({}) == 0.0
    assert _coerce_broker_cash(object()) == 0.0
    assert positions == {"AAPL": Position(symbol="AAPL", qty=2.0, avg_price=95.0)}
    assert portfolio.cash_balance == 1234.5
    assert portfolio.positions == positions


def test_broker_portfolio_payload_rejects_positions_outside_configured_universe() -> None:
    config = _base_config(":memory:")

    with pytest.raises(ValueError, match="Broker portfolio mismatch"):
        _build_portfolio_from_broker_payload(
            account={"cash": "0"},
            positions_raw=[
                {
                    "symbol": "MSFT",
                    "asset_class": "us_equity",
                    "qty": "1",
                    "avg_entry_price": "100",
                    "side": "long",
                }
            ],
            config=config,
        )


def test_market_data_pipeline_planning_helpers_are_deterministic() -> None:
    decision_ts = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    current_ts = decision_ts + timedelta(minutes=1)

    assert _should_use_stream_ingestion(ingest_market_data=True, stream_mode=True) is True
    assert _should_use_stream_ingestion(ingest_market_data=False, stream_mode=True) is False
    assert _should_use_stream_ingestion(ingest_market_data=True, stream_mode=False) is False
    assert (
        _resolve_market_data_freshness_ts(
            mode="backtest",
            decision_ts=decision_ts,
            current_ts=current_ts,
        )
        == decision_ts
    )
    assert (
        _resolve_market_data_freshness_ts(
            mode="once",
            decision_ts=decision_ts,
            current_ts=current_ts,
        )
        == current_ts
    )


def test_empty_market_data_pipeline_result_is_stable() -> None:
    result = _empty_market_data_pipeline_result()

    assert result.processed_orders == ()
    assert result.market_data_events == ()
    assert result.price_lookup == {}


def test_cycle_stream_state_starts_empty_and_exposes_latest_prices() -> None:
    ts = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    state = _build_cycle_stream_state()

    assert state.processed_orders == []
    assert state.latest_prices == {}
    assert state.counters.orders_emitted == 0

    state.latest_prices["AAPL"] = (ts, 101.25)
    state.latest_prices["MSFT"] = (ts, 250.5)

    assert _latest_stream_prices(state) == {"AAPL": 101.25, "MSFT": 250.5}


def test_plan_cycle_stream_market_event_normalizes_fresh_event() -> None:
    event_ts = datetime(2026, 1, 20, 12, 0)
    event = _stock_event(ts=event_ts, close=101.25)

    plan = _plan_cycle_stream_market_event(
        event,
        enforce_staleness=True,
        now=datetime(2026, 1, 20, 12, 0, 30, tzinfo=timezone.utc),
        max_age_seconds=60,
    )

    assert plan.symbol == "AAPL"
    assert plan.decision_ts == event_ts.replace(tzinfo=timezone.utc)
    assert plan.close_price == 101.25
    assert plan.should_skip is False
    assert plan.freshness.age_seconds == 30.0


def test_plan_cycle_stream_market_event_skips_stale_event_only_when_enforced() -> None:
    event = _stock_event(ts=datetime(2026, 1, 20, 11, 58, tzinfo=timezone.utc))
    now = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)

    enforced = _plan_cycle_stream_market_event(
        event,
        enforce_staleness=True,
        now=now,
        max_age_seconds=60,
    )
    unenforced = _plan_cycle_stream_market_event(
        event,
        enforce_staleness=False,
        now=now,
        max_age_seconds=60,
    )

    assert enforced.freshness.is_stale is True
    assert enforced.should_skip is True
    assert unenforced.freshness.is_stale is True
    assert unenforced.should_skip is False


def test_market_data_event_table_name_selects_asset_class_table() -> None:
    assert _market_data_event_table_name("stocks") == "stock_bar_events"
    assert _market_data_event_table_name("stock") == "stock_bar_events"
    assert _market_data_event_table_name("crypto") == "crypto_bar_events"
    assert _market_data_event_table_name("cryptocurrency") == "crypto_bar_events"


def test_build_recent_market_data_query_shapes_sql_and_params() -> None:
    as_of_ts = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)

    latest = _build_recent_market_data_query(
        table="stock_bar_events",
        symbol="aapl",
        timeframe="1Min",
        as_of_ts=None,
    )
    bounded = _build_recent_market_data_query(
        table="crypto_bar_events",
        symbol="btc/usd",
        timeframe="5Min",
        as_of_ts=as_of_ts,
    )

    assert "FROM stock_bar_events" in latest.sql
    assert "ts <= %s" not in latest.sql
    assert latest.params == ("AAPL", "1Min")
    assert "FROM crypto_bar_events" in bounded.sql
    assert "ts <= %s" in bounded.sql
    assert bounded.params == ("BTC/USD", "5Min", as_of_ts)


def test_row_to_market_event_selects_stock_or_crypto_event() -> None:
    ts = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    row = (ts, ts, 100.0, 101.0, 99.0, 100.5, 10.0, None, None, "event_store")

    stock = _row_to_market_event("stocks", "AAPL", "1Min", row)
    crypto = _row_to_market_event("crypto", "BTC/USD", "1Min", row)

    assert isinstance(stock, StockBarEvent)
    assert stock.symbol == "AAPL"
    assert stock.close == 100.5
    assert isinstance(crypto, CryptoBarEvent)
    assert crypto.symbol == "BTC/USD"
    assert crypto.close == 100.5


def test_build_stream_risk_price_lookup_uses_latest_prices_and_order_override() -> None:
    base_ts = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)

    price_lookup = _build_stream_risk_price_lookup(
        {
            "AAPL": (base_ts, 100.0),
            "MSFT": (base_ts, 200.0),
        },
        {"symbol": " aapl ", "price": "101.25"},
    )

    assert price_lookup == {"AAPL": 101.25, "MSFT": 200.0}


def test_build_cycle_risk_context_uses_explicit_state_without_storage() -> None:
    base_ts = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    position = Position(symbol="AAPL", qty=1.0, avg_price=90.0)
    open_order = {"client_order_id": "cid_open", "symbol": "AAPL"}
    order = {"symbol": "AAPL", "price": 105.0, "created_at": base_ts}

    context = _build_cycle_risk_context(
        positions={"AAPL": position},
        open_orders=[open_order],
        latest_prices={"AAPL": (base_ts - timedelta(minutes=1), 100.0)},
        order=order,
        run_id="run_1",
        cycle_id="cycle_1",
        halted=True,
        fallback_ts=base_ts + timedelta(minutes=5),
    )

    assert context.positions == {"AAPL": position}
    assert context.open_orders == [open_order]
    assert context.price_lookup == {"AAPL": 105.0}
    assert context.run_id == "run_1"
    assert context.cycle_id == "cycle_1"
    assert context.decision_ts == base_ts
    assert context.halted is True


def test_build_cycle_risk_context_uses_fallback_for_missing_order_time() -> None:
    fallback_ts = datetime(2026, 1, 20, 12, 5, tzinfo=timezone.utc)

    context = _build_cycle_risk_context(
        positions={},
        open_orders=[],
        latest_prices={},
        order={"symbol": "AAPL"},
        run_id="run_1",
        cycle_id="cycle_1",
        halted=False,
        fallback_ts=fallback_ts,
    )

    assert context.decision_ts == fallback_ts


def test_latest_order_events_query_selects_lifecycle_fields_in_order() -> None:
    query = _latest_order_events_query()

    assert "SELECT client_order_id, run_id, cycle_id, symbol, side, qty, order_type" in query
    assert "FROM order_events" in query
    assert "ORDER BY created_at DESC, order_event_id DESC" in query


def test_latest_order_event_row_helpers_normalize_and_dedupe_rows() -> None:
    created_new = datetime(2026, 1, 20, 12, 1, tzinfo=timezone.utc)
    created_old = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    newest = (
        "cid_1",
        "run_1",
        "cycle_1",
        "AAPL",
        "buy",
        1.0,
        "market",
        "submitted",
        "broker_1",
        created_new,
    )
    older_duplicate = (
        "cid_1",
        "run_1",
        "cycle_0",
        "AAPL",
        "buy",
        1.0,
        "market",
        "created",
        None,
        created_old,
    )
    second_order = (
        "cid_2",
        "run_1",
        "cycle_1",
        "MSFT",
        "sell",
        2.0,
        "market",
        "filled",
        "broker_2",
        created_new,
    )

    assert _latest_order_event_row_to_record(newest) == {
        "client_order_id": "cid_1",
        "run_id": "run_1",
        "cycle_id": "cycle_1",
        "symbol": "AAPL",
        "side": "buy",
        "qty": 1.0,
        "order_type": "market",
        "status": "submitted",
        "broker_order_id": "broker_1",
        "created_at": created_new,
    }
    assert _dedupe_latest_order_event_rows(
        [
            newest,
            older_duplicate,
            (None, "run_1", "cycle_1", "NVDA", "buy", 1.0, "market", "created", None, created_new),
            second_order,
        ]
    ) == (
        _latest_order_event_row_to_record(newest),
        _latest_order_event_row_to_record(second_order),
    )


def test_evaluate_cycle_order_risk_returns_approved_and_manager_rejection_logs() -> None:
    base_ts = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    context = RiskContext(
        positions={},
        open_orders=[],
        price_lookup={},
        run_id="run_1",
        cycle_id="cycle_1",
        decision_ts=base_ts,
    )
    manager = RejectSymbolRiskManager("AAPL", "blocked_symbol")
    order = {"symbol": "AAPL", "side": "buy", "qty": 1.0}

    result = _evaluate_cycle_order_risk(
        order=order,
        context=context,
        risk_manager=manager,
    )

    assert result.approved_orders == ()
    assert result.rejected_orders == ({**order, "rejection_reason": "blocked_symbol"},)
    assert len(result.rejection_logs) == 1
    assert result.rejection_logs[0].order == result.rejected_orders[0]
    assert result.rejection_logs[0].manager_name == "RejectSymbolRiskManager"


def test_broker_response_helpers_normalize_status_sync_and_processed_order() -> None:
    order = {"symbol": "AAPL", "side": "buy", "qty": 1.0, "price": 100.0}
    fallback_fill_ts = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    filled_response = {
        "status": "filled",
        "fill_qty": "0.5",
        "fill_price": "101.25",
    }

    assert _resolve_broker_response_status({}) == "submitted"
    assert _resolve_broker_response_status(filled_response) == "filled"
    assert (
        _should_sync_portfolio_for_broker_response(
            status="filled",
            sync_portfolio_on_fill=True,
        )
        is True
    )
    assert (
        _should_sync_portfolio_for_broker_response(
            status="submitted",
            sync_portfolio_on_fill=True,
        )
        is False
    )
    assert _build_processed_order_from_broker_response(order, filled_response) == {
        **order,
        "qty": 0.5,
        "price": 101.25,
    }
    assert (
        _build_processed_order_from_broker_response(
            order,
            {"status": "rejected", "rejection_reason": "broker_reject"},
        )
        is None
    )
    plan = _build_cycle_broker_response_plan(
        order,
        filled_response,
        sync_portfolio_on_fill=True,
        fallback_fill_ts=fallback_fill_ts,
    )
    assert plan.status == "filled"
    assert plan.processed_order == {**order, "qty": 0.5, "price": 101.25}
    assert plan.should_sync_portfolio is True
    assert plan.fill_ts == fallback_fill_ts
    rejected_plan = _build_cycle_broker_response_plan(
        order,
        {"status": "rejected", "rejection_reason": "broker_reject"},
        sync_portfolio_on_fill=True,
        fallback_fill_ts=fallback_fill_ts,
    )
    assert rejected_plan.processed_order is None
    assert rejected_plan.should_sync_portfolio is False


def test_build_internal_fill_portfolio_application_normalizes_fill_response() -> None:
    order = {"symbol": " AAPL ", "side": " BUY ", "qty": "2", "price": "99.0"}
    response = {"fill_qty": "1.5", "fill_price": "101.25", "fee_amount": "0.25"}

    application = build_internal_fill_portfolio_application(order=order, response=response)

    assert application is not None
    assert application.order == {
        "symbol": "AAPL",
        "side": "buy",
        "qty": 1.5,
        "price": "101.25",
        "fee_amount": "0.25",
    }
    assert application.price_lookup == {"AAPL": 101.25}


def test_build_internal_fill_portfolio_application_skips_invalid_fill_inputs() -> None:
    assert (
        build_internal_fill_portfolio_application(
            order={"symbol": "", "side": "buy", "qty": 1.0},
            response={},
        )
        is None
    )
    assert (
        build_internal_fill_portfolio_application(
            order={"symbol": "AAPL", "side": "hold", "qty": 1.0},
            response={},
        )
        is None
    )
    assert (
        build_internal_fill_portfolio_application(
            order={"symbol": "AAPL", "side": "buy", "qty": "bad"},
            response={},
        )
        is None
    )


def _base_config(db_path: str) -> Config:
    return Config(
        mode="once",
        strategy_type="noop",
        strategy_id="test",
        strategy_timeframe="1Min",
        sma_short_window=2,
        sma_long_window=3,
        db_path=db_path,
        event_store="postgres",
        market_data_source="noop",
        market_data_asset_class="stocks",
        market_data_stock_feed="iex",
        market_data_symbols=("AAPL",),
        market_data_max_age_seconds=300,
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


def test_allowed_cycle_event_types_respects_logging_flags(tmp_path) -> None:
    config = _base_config(str(tmp_path / "events.duckdb"))

    assert _allowed_cycle_event_types(config) == {
        "runs",
        "run_events",
        "stock_bar_events",
        "crypto_bar_events",
        "config_kv",
        "signal_events",
        "indicator_events",
        "prediction_events",
        "order_events",
        "fill_events",
        "position_snapshots",
    }

    quiet = replace(
        config,
        log_signal_events=False,
        log_indicator_events=False,
        log_order_events=False,
        log_fill_events=False,
        log_position_snapshots=False,
    )

    assert _allowed_cycle_event_types(quiet) == {
        "runs",
        "run_events",
        "stock_bar_events",
        "crypto_bar_events",
        "config_kv",
        "prediction_events",
    }


def test_stream_universe_barrier_invokes_strategy_once_for_aligned_symbols(
    tmp_path,
) -> None:
    store = DuckDBEventStore(str(tmp_path / "universe-stream.duckdb"))
    strategy = UniverseOrderStrategy()
    config = replace(
        _base_config(str(tmp_path / "universe-stream.duckdb")),
        market_data_symbols=("AAPL", "MSFT"),
    )
    decision_ts = datetime.now(timezone.utc)
    events = [
        StockBarEvent(
            symbol=symbol,
            timeframe="1Min",
            ts=decision_ts,
            ingested_at=decision_ts,
            open=price,
            high=price,
            low=price,
            close=price,
            volume=1.0,
            trade_count=None,
            vwap=None,
            source="test",
        )
        for symbol, price in (("AAPL", 100.0), ("MSFT", 200.0))
    ]

    async def _run() -> list[object]:
        event_queue = asyncio.Queue()
        order_queue = asyncio.Queue()
        for event in events:
            await event_queue.put(event)
        await event_queue.put(None)
        await _generate_universe_snapshot_orders(
            runtime=CycleStreamRuntime(
                event_store=store,
                strategy=strategy,
                broker=_UnusedBroker(),
                portfolio=Portfolio.empty(cash_balance=100_000.0),
                run_id="run_1",
                cycle_id="cycle_1",
                max_age_seconds=300,
                enforce_staleness=True,
                asset_class="stocks",
                time_in_force="day",
                sync_portfolio_on_fill=False,
                broker_type="noop",
                config=config,
                risk_manager=NoOpRiskManager(),
            ),
            state=_build_cycle_stream_state(),
            event_queue=event_queue,
            order_queue=order_queue,
        )
        return [await order_queue.get(), await order_queue.get(), await order_queue.get()]

    orders = asyncio.run(_run())

    assert strategy.calls == [decision_ts]
    assert [order["symbol"] for order in orders[:-1]] == ["AAPL", "MSFT"]
    assert orders[-1] is None


def test_startup_config_log_values_mask_secrets(tmp_path) -> None:
    config = replace(
        _base_config(str(tmp_path / "events.duckdb")),
        alpaca_api_key="abcdefghijkl",
        alpaca_secret_key="short",
        pg_dsn="postgres://user:password@example/db",
        pg_password="",
    )

    values = _startup_config_log_values(config)

    assert _mask_secret(None) == "<unset>"
    assert _mask_secret("short") == "*****"
    assert _mask_secret("abcdefghijkl") == "abcd***ijkl"
    assert values["alpaca_api_key"] == "abcd***ijkl"
    assert values["alpaca_secret_key"] == "*****"
    assert values["pg_dsn"] == "post***e/db"
    assert values["pg_password"] == "<unset>"
    assert values["market_data_symbols"] == "AAPL"


def test_indicator_events_persisted(tmp_path) -> None:
    """Ensure indicator events are written when enabled."""
    store = DuckDBEventStore(str(tmp_path / "events.duckdb"))
    base_ts = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    bars = [
        Bar(ts=base_ts - timedelta(minutes=3), open=100, high=101, low=99, close=100, volume=1, vwap=None, trade_count=None),
        Bar(ts=base_ts - timedelta(minutes=2), open=101, high=102, low=100, close=101, volume=1, vwap=None, trade_count=None),
        Bar(ts=base_ts - timedelta(minutes=1), open=102, high=103, low=101, close=102, volume=1, vwap=None, trade_count=None),
        Bar(ts=base_ts, open=103, high=104, low=102, close=103, volume=1, vwap=None, trade_count=None),
    ]
    signal = SmaCrossoverSignal(SmaIndicator(period=2), SmaIndicator(period=3))
    generator = InMemoryBarsSignalGenerator(
        bars_by_symbol={"AAPL": bars},
        signals=[signal],
        symbols=["AAPL"],
        timeframe="1Min",
        event_store=store,
    )
    strategy = SimpleStrategy(signal_generator=generator, primary_signal=signal.name)

    event = StockBarEvent(
        symbol="AAPL",
        timeframe="1Min",
        ts=base_ts,
        ingested_at=base_ts,
        open=103,
        high=104,
        low=102,
        close=103,
        volume=10,
        trade_count=None,
        vwap=None,
        source="test",
    )

    config = replace(_base_config(str(tmp_path / "events.duckdb")), mode="backtest")
    run_cycle(
        event_store=store,
        strategy=strategy,
        risk_manager=NoOpRiskManager(),
        market_data_source=StaticMarketDataSource([event]),
        config=config,
        decision_ts=base_ts,
        ingest_market_data=False,
        portfolio=Portfolio.from_event_store(store, asof_ts=base_ts),
    )

    count = store.connection().execute("SELECT COUNT(*) FROM indicator_events").fetchone()[0]
    assert count > 0


def test_order_lifecycle_and_fill_events(tmp_path) -> None:
    """Verify order lifecycle and fill events are persisted for internal broker."""
    store = DuckDBEventStore(str(tmp_path / "events.duckdb"))
    now = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    event = StockBarEvent(
        symbol="AAPL",
        timeframe="1Min",
        ts=now,
        ingested_at=now,
        open=100,
        high=101,
        low=99,
        close=100.5,
        volume=10,
        trade_count=None,
        vwap=None,
        source="test",
    )

    config = replace(
        _base_config(str(tmp_path / "events.duckdb")),
        broker_type="internal",
        mode="backtest",
    )

    strategy = SingleOrderStrategy()
    run_cycle(
        event_store=store,
        strategy=strategy,
        risk_manager=NoOpRiskManager(),
        market_data_source=StaticMarketDataSource([event]),
        config=config,
        decision_ts=now,
        ingest_market_data=False,
        portfolio=Portfolio.from_event_store(store, asof_ts=now),
    )

    statuses = {
        row[0] for row in store.connection().execute("SELECT status FROM order_events").fetchall()
    }
    assert {"created", "validated", "submitted", "filled"}.issubset(statuses)

    fill_count = store.connection().execute("SELECT COUNT(*) FROM fill_events").fetchone()[0]
    assert fill_count == 1
