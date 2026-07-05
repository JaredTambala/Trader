"""Tests for event-store-first runtime status helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from trader.config import Config
from trader.runtime.status import assess_runtime_health, evaluate_health, runtime_status, set_halt_state
from tests.support.duckdb_store import DuckDBEventStore


def _config(*, max_age_seconds: int = 60) -> Config:
    return Config(
        mode="loop",
        strategy_type="noop",
        strategy_id="noop",
        strategy_timeframe="1Min",
        sma_short_window=2,
        sma_long_window=3,
        db_path="",
        event_store="postgres",
        market_data_source="noop",
        market_data_asset_class="stocks",
        market_data_stock_feed="iex",
        market_data_symbols=("AAPL",),
        market_data_max_age_seconds=max_age_seconds,
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


def test_assess_runtime_health_returns_typed_healthy_assessment() -> None:
    assessment = assess_runtime_health(
        latest_run={"status": "success"},
        latest_cycle={"status": "success"},
        market_data={"missing_count": 0, "stale_count": 0},
        open_orders={"stale_count": 0},
        halt={"halted": False},
    )

    assert assessment.status == "healthy"
    assert assessment.exit_code == 0
    assert assessment.reasons == ()
    assert assessment.to_record() == {"status": "healthy", "exit_code": 0, "reasons": []}


def test_assess_runtime_health_accumulates_degraded_and_unhealthy_reasons() -> None:
    assessment = assess_runtime_health(
        latest_run={"status": "failed"},
        latest_cycle=None,
        market_data={"missing_count": 1, "stale_count": 1},
        open_orders={"stale_count": 2},
        halt={"halted": True},
    )

    assert assessment.status == "unhealthy"
    assert assessment.exit_code == 2
    assert assessment.reasons == (
        "latest_run_failed",
        "no_cycle",
        "halted",
        "missing_market_data",
        "stale_market_data",
        "stale_open_orders",
    )
    assert evaluate_health(
        latest_run={"status": "failed"},
        latest_cycle=None,
        market_data={"missing_count": 1, "stale_count": 1},
        open_orders={"stale_count": 2},
        halt={"halted": True},
    ) == assessment.to_record()


def test_runtime_status_empty_store_is_degraded(tmp_path) -> None:
    store = DuckDBEventStore(str(tmp_path / "events.duckdb"))

    status = runtime_status(store, _config(), now=datetime(2026, 1, 1, tzinfo=timezone.utc))

    assert status["health"]["exit_code"] == 1
    assert status["health"]["status"] == "degraded"
    assert "no_run" in status["health"]["reasons"]
    assert status["market_data"]["missing_count"] == 1


def test_runtime_status_healthy_store(tmp_path) -> None:
    store = DuckDBEventStore(str(tmp_path / "events.duckdb"))
    now = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
    _seed_successful_runtime(store, now=now)
    store.record_event(
        "stock_bar_events",
        {
            "symbol": "AAPL",
            "timeframe": "1Min",
            "ts": now,
            "ingested_at": now,
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.5,
            "volume": 10.0,
            "trade_count": None,
            "vwap": None,
            "source": "test",
        },
    )
    store.record_event(
        "position_snapshots",
        {
            "asof_ts": now,
            "symbol": "AAPL",
            "qty": 2.0,
            "avg_price": 100.0,
            "cash_balance": 1000.0,
            "run_id": "run_1",
            "session_id": "run_1",
            "cycle_id": "cycle_1",
        },
    )

    status = runtime_status(store, _config(), now=now + timedelta(seconds=10))

    assert status["health"] == {"status": "healthy", "exit_code": 0, "reasons": []}
    assert status["portfolio"]["cash"] == 1000.0
    assert status["portfolio"]["position_count"] == 1


def test_runtime_status_failed_cycle_is_unhealthy(tmp_path) -> None:
    store = DuckDBEventStore(str(tmp_path / "events.duckdb"))
    now = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
    store.record_run_session_start("run_1", "trading", now, strategy_id="noop")
    store.record_run_session_finish("run_1", "trading", now, now, "failed", "boom", strategy_id="noop")
    store.record_cycle_start("run_1", "cycle_1", "noop", "loop", now, now)
    store.record_cycle_finish("run_1", "cycle_1", "noop", "loop", now, now, now, "failed", "boom")

    status = runtime_status(store, _config(), now=now)

    assert status["health"]["exit_code"] == 2
    assert "latest_cycle_failed" in status["health"]["reasons"]
    assert "latest_run_failed" in status["health"]["reasons"]


def test_runtime_status_stale_market_data_is_unhealthy(tmp_path) -> None:
    store = DuckDBEventStore(str(tmp_path / "events.duckdb"))
    now = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
    _seed_successful_runtime(store, now=now)
    store.record_event(
        "stock_bar_events",
        {
            "symbol": "AAPL",
            "timeframe": "1Min",
            "ts": now - timedelta(minutes=10),
            "ingested_at": now - timedelta(minutes=10),
            "open": 100.0,
            "high": 100.0,
            "low": 100.0,
            "close": 100.0,
            "volume": 10.0,
            "trade_count": None,
            "vwap": None,
            "source": "test",
        },
    )

    status = runtime_status(store, _config(max_age_seconds=60), now=now)

    assert status["health"]["exit_code"] == 2
    assert "stale_market_data" in status["health"]["reasons"]


def test_halt_state_degrades_health(tmp_path) -> None:
    store = DuckDBEventStore(str(tmp_path / "events.duckdb"))
    now = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
    set_halt_state(store, halted=True, reason="manual test", now=now)

    status = runtime_status(store, _config(), now=now)

    assert status["halt"]["halted"] is True
    assert status["halt"]["reason"] == "manual test"
    assert status["health"]["exit_code"] == 1
    assert "halted" in status["health"]["reasons"]


def test_stale_open_orders_are_reported(tmp_path) -> None:
    store = DuckDBEventStore(str(tmp_path / "events.duckdb"))
    now = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
    _seed_successful_runtime(store, now=now)
    store.record_event(
        "order_events",
        {
            "order_event_id": "order_evt_1",
            "client_order_id": "cid_1",
            "run_id": "run_1",
            "session_id": "run_1",
            "cycle_id": "cycle_1",
            "symbol": "AAPL",
            "side": "buy",
            "qty": 1.0,
            "order_type": "market",
            "status": "submitted",
            "broker_order_id": "broker_1",
            "rejection_reason": None,
            "created_at": now - timedelta(minutes=5),
        },
    )

    status = runtime_status(store, _config(max_age_seconds=60), now=now)

    assert status["open_orders"]["count"] == 1
    assert status["open_orders"]["stale_count"] == 1
    assert status["health"]["exit_code"] == 1
    assert "stale_open_orders" in status["health"]["reasons"]


def _seed_successful_runtime(store: DuckDBEventStore, *, now: datetime) -> None:
    store.record_run_session_start("run_1", "trading", now, strategy_id="noop")
    store.record_run_session_finish("run_1", "trading", now, now, "success", None, strategy_id="noop")
    store.record_cycle_start("run_1", "cycle_1", "noop", "loop", now, now)
    store.record_cycle_finish("run_1", "cycle_1", "noop", "loop", now, now, now, "success", None)
