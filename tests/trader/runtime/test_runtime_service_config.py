"""Contracts for normalizing service configuration and realtime scheduling decisions.

Subject: Notifications, execution modes, startup policy, metrics, initial state, deduplication, and reconciliation.
Level: Pure configuration-boundary and scheduling-policy unit contracts.
Collaborators: Real service-config helpers with typed configuration, fixed timestamps, and plain-data payloads.
Guarantees: Runtime inputs become explicit canonical settings and timing decisions without hidden state mutation.
Non-goals: Starting services, opening listeners, running cycles, broker calls, persistence, or wall-clock sleeps.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from trader.config import Config
from trader.runtime.service_config import (
    build_notify_cycle_config,
    decide_order_reconciliation,
    decide_pending_realtime_cycle,
    deduplicate_market_data_notify,
    parse_initial_cash,
    parse_initial_positions,
    parse_market_data_notify,
    resolve_metrics_worker_settings,
    resolve_notify_channel,
    resolve_portfolio_source,
    resolve_runtime_execution_mode,
    validate_startup_recovery_mode,
)


def _config(**overrides: object) -> Config:
    values = {
        "mode": "loop",
        "strategy_type": "noop",
        "strategy_id": "noop",
        "strategy_timeframe": "1Min",
        "sma_short_window": 2,
        "sma_long_window": 3,
        "db_path": ":memory:",
        "event_store": "postgres",
        "market_data_source": "noop",
        "market_data_asset_class": "stocks",
        "market_data_stock_feed": "iex",
        "market_data_symbols": (),
        "market_data_max_age_seconds": 60,
        "alpaca_api_key": "",
        "alpaca_secret_key": "",
        "alpaca_data_base_url": "https://data.alpaca.markets",
        "alpaca_base_url": "https://paper-api.alpaca.markets",
        "pg_dsn": "",
        "pg_host": "",
        "pg_port": 5432,
        "pg_db": "",
        "pg_user": "",
        "pg_password": "",
        "buffered_event_store": False,
        "buffer_flush_interval_ms": 250,
        "buffer_max_batch_size": 500,
        "buffer_max_queue_size": 10000,
        "buffer_block_on_full": True,
        "log_signal_events": True,
        "log_indicator_events": True,
        "log_order_events": True,
        "log_fill_events": True,
        "log_position_snapshots": True,
        "broker_type": "noop",
    }
    values.update(overrides)
    return Config(**values)


def test_parse_market_data_notify_normalizes_valid_payload() -> None:
    """Ensure a complete notification becomes canonical symbol, asset, and timestamp data."""
    payload = parse_market_data_notify(
        '{"symbol": "btc/usd", "timeframe": "1Min", "asset_class": "Crypto", "ts": "2026-01-01T12:00:00Z"}'
    )

    assert payload == {
        "symbol": "BTC/USD",
        "timeframe": "1Min",
        "asset_class": "crypto",
        "ts": datetime(2026, 1, 1, 12, tzinfo=timezone.utc),
    }


@pytest.mark.parametrize(
    "payload",
    [
        "not-json",
        "[]",
        '{"symbol": "AAPL"}',
        '{"symbol": "AAPL", "timeframe": "1Min", "ts": "not-a-date"}',
    ],
)
def test_parse_market_data_notify_returns_none_for_generic_or_invalid_payloads(
    payload: str,
) -> None:
    """Ensure malformed or incomplete notification content cannot trigger a trading cycle."""
    assert parse_market_data_notify(payload) is None


def test_resolve_runtime_execution_mode_normalizes_service_mode_aliases() -> None:
    """Ensure realtime aliases normalize consistently and unknown modes fall back to loop."""
    assert resolve_runtime_execution_mode("once") == "once"
    assert resolve_runtime_execution_mode("ONCE") == "once"
    assert resolve_runtime_execution_mode("realtime") == "realtime"
    assert resolve_runtime_execution_mode("real_time") == "realtime"
    assert resolve_runtime_execution_mode("real-time") == "realtime"
    assert resolve_runtime_execution_mode("loop") == "loop"
    assert resolve_runtime_execution_mode("anything_else") == "loop"


def test_validate_startup_recovery_mode_preserves_exact_supported_values() -> None:
    """Ensure only the two explicit startup recovery policies pass validation."""
    assert validate_startup_recovery_mode("resume") == "resume"
    assert validate_startup_recovery_mode("fail_closed") == "fail_closed"
    with pytest.raises(
        ValueError, match="startup recovery mode must be 'resume' or 'fail_closed'"
    ):
        validate_startup_recovery_mode("RESUME")


def test_build_notify_cycle_config_scopes_symbol_timeframe_and_asset_class() -> None:
    """Ensure notification evidence narrows cycle configuration to its symbol and market scope."""
    config = _config(
        market_data_symbols=("MSFT",),
        market_data_asset_class="stocks",
        strategy_timeframe="5Min",
    )

    scoped = build_notify_cycle_config(
        config,
        {"symbol": "AAPL", "timeframe": "1Min", "asset_class": "crypto"},
    )

    assert scoped is not config
    assert scoped.market_data_symbols == ("AAPL",)
    assert scoped.strategy_timeframe == "1Min"
    assert scoped.market_data_asset_class == "crypto"
    assert config.market_data_symbols == ("MSFT",)


def test_build_notify_cycle_config_requires_symbol_and_defaults_missing_fields() -> (
    None
):
    """Ensure missing identity blocks cycle configuration while optional fields receive safe defaults."""
    config = _config(
        market_data_symbols=("MSFT",),
        market_data_asset_class="stocks",
        strategy_timeframe="5Min",
    )

    scoped = build_notify_cycle_config(config, {"symbol": "AAPL"})

    assert scoped.market_data_symbols == ("AAPL",)
    assert scoped.strategy_timeframe == "5Min"
    assert scoped.market_data_asset_class == "stocks"
    with pytest.raises(ValueError, match="notify payload missing symbol"):
        build_notify_cycle_config(config, {})


def test_resolve_metrics_worker_settings_returns_none_when_disabled() -> None:
    """Ensure disabled sampling produces no metrics worker configuration."""
    assert (
        resolve_metrics_worker_settings(
            _config(metrics_interval_seconds=0), run_id="run"
        )
        is None
    )
    assert (
        resolve_metrics_worker_settings(
            _config(metrics_interval_seconds=None), run_id="run"
        )
        is None
    )


def test_resolve_metrics_worker_settings_normalizes_enabled_config() -> None:
    """Ensure enabled metrics settings normalize cadence, bounds, and portfolio source."""
    settings = resolve_metrics_worker_settings(
        _config(
            market_data_symbols=("AAPL", "MSFT"),
            market_data_asset_class="stocks",
            metrics_interval_seconds=15,
            metrics_window_seconds=300,
            metrics_enable_snapshots=True,
        ),
        run_id="run_1",
    )

    assert settings is not None
    assert settings.symbols == ("AAPL", "MSFT")
    assert settings.asset_class == "stocks"
    assert settings.interval_seconds == 15.0
    assert settings.window_seconds == 300.0
    assert settings.run_id == "run_1"
    assert settings.persist_snapshots is True


def test_resolve_metrics_worker_settings_treats_empty_window_as_absent() -> None:
    """Ensure empty metrics windows remain unbounded instead of becoming invalid timestamps."""
    settings = resolve_metrics_worker_settings(
        _config(metrics_interval_seconds=15, metrics_window_seconds=0),
        run_id="run_1",
    )

    assert settings is not None
    assert settings.window_seconds is None
    assert settings.persist_snapshots is False


def test_parse_initial_positions_and_cash() -> None:
    """Ensure configured initial portfolio values normalize into typed positions and cash."""
    positions = parse_initial_positions(
        [
            {"symbol": " aapl ", "qty": "2", "avg_price": "100.5"},
            {"symbol": "", "qty": 1},
            {"symbol": "MSFT", "qty": 3},
        ]
    )

    assert [
        (position.symbol, position.qty, position.avg_price) for position in positions
    ] == [
        ("AAPL", 2.0, 100.5),
        ("MSFT", 3.0, None),
    ]
    assert parse_initial_cash(None) == 0.0
    assert parse_initial_cash("") == 0.0
    assert parse_initial_cash("123.45") == 123.45


def test_parse_initial_positions_rejects_invalid_shape() -> None:
    """Ensure malformed initial position collections fail at the configuration boundary."""
    with pytest.raises(ValueError, match="initial_positions must be a list"):
        parse_initial_positions("AAPL")
    with pytest.raises(ValueError, match="entries must be mappings"):
        parse_initial_positions(["AAPL"])


def test_resolve_portfolio_source_precedence() -> None:
    """Ensure explicit portfolio source overrides configuration and defaults remain deterministic."""
    assert (
        resolve_portfolio_source(
            _config(trader_service_portfolio_source="db"),
            {"trader_service": {"portfolio_source": "alpaca"}},
        )
        == "db"
    )
    assert (
        resolve_portfolio_source(
            _config(), {"trader_service": {"portfolio_source": "alpaca"}}
        )
        == "alpaca"
    )
    assert resolve_portfolio_source(_config(broker_type="alpaca"), None) == "alpaca"
    assert resolve_portfolio_source(_config(), None) == "db"


def test_resolve_notify_channel_reports_invalid_fallback() -> None:
    """Ensure unsafe channel names use the fixed fallback and report that decision."""
    assert resolve_notify_channel(None).channel == "market_data"
    assert resolve_notify_channel("market_data").channel == "market_data"
    invalid = resolve_notify_channel("bad-channel")
    assert invalid.channel == "market_data"
    assert invalid.valid is False


def test_deduplicate_market_data_notify_returns_next_state_without_mutating_input() -> (
    None
):
    """Ensure notification deduplication returns new state and preserves caller-owned payloads."""
    first_ts = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
    second_ts = datetime(2026, 1, 1, 12, 1, tzinfo=timezone.utc)
    original_seen: dict[tuple[str, str, str], datetime] = {}

    first = deduplicate_market_data_notify(
        {
            "symbol": "AAPL",
            "timeframe": "1Min",
            "asset_class": "stocks",
            "ts": first_ts,
        },
        original_seen,
    )
    duplicate = deduplicate_market_data_notify(
        {
            "symbol": "AAPL",
            "timeframe": "1Min",
            "asset_class": "stocks",
            "ts": first_ts,
        },
        first.last_seen,
    )
    newer = deduplicate_market_data_notify(
        {
            "symbol": "AAPL",
            "timeframe": "1Min",
            "asset_class": "stocks",
            "ts": second_ts,
        },
        first.last_seen,
    )

    assert original_seen == {}
    assert first.should_run is True
    assert first.last_seen == {("AAPL", "1Min", "stocks"): first_ts}
    assert duplicate.should_run is False
    assert duplicate.duplicate_key == ("AAPL", "1Min", "stocks")
    assert duplicate.duplicate_ts == first_ts
    assert newer.should_run is True
    assert newer.last_seen == {("AAPL", "1Min", "stocks"): second_ts}


def test_deduplicate_market_data_notify_runs_unkeyed_payload_without_state_change() -> (
    None
):
    """Ensure unkeyed notifications may run without corrupting retained deduplication state."""
    last_seen = {
        ("AAPL", "1Min", "stocks"): datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
    }

    decision = deduplicate_market_data_notify({"symbol": "AAPL"}, last_seen)

    assert decision.should_run is True
    assert decision.last_seen == last_seen
    assert decision.last_seen is not last_seen


def test_decide_order_reconciliation_preserves_disabled_and_unavailable_states() -> (
    None
):
    """Ensure disabled cadence and unsupported brokers produce explicit non-running decisions."""
    disabled = decide_order_reconciliation(
        interval_seconds=0,
        reconciler_available=True,
        now_monotonic=100.0,
        last_reconciliation_at=0.0,
        force=True,
    )
    unavailable = decide_order_reconciliation(
        interval_seconds=60,
        reconciler_available=False,
        now_monotonic=100.0,
        last_reconciliation_at=0.0,
        force=True,
    )

    assert disabled.should_reconcile is False
    assert disabled.reason == "disabled"
    assert unavailable.should_reconcile is False
    assert unavailable.reason == "reconciler_unavailable"


def test_decide_order_reconciliation_handles_due_throttled_and_forced_cases() -> None:
    """Ensure elapsed time and force flags yield deterministic reconciliation scheduling decisions."""
    throttled = decide_order_reconciliation(
        interval_seconds=60,
        reconciler_available=True,
        now_monotonic=100.0,
        last_reconciliation_at=50.0,
        force=False,
    )
    due = decide_order_reconciliation(
        interval_seconds=60,
        reconciler_available=True,
        now_monotonic=111.0,
        last_reconciliation_at=50.0,
        force=False,
    )
    forced = decide_order_reconciliation(
        interval_seconds=60,
        reconciler_available=True,
        now_monotonic=100.0,
        last_reconciliation_at=99.0,
        force=True,
    )

    assert throttled.should_reconcile is False
    assert throttled.reason == "too_soon"
    assert due.should_reconcile is True
    assert due.reason == "due"
    assert forced.should_reconcile is True
    assert forced.reason == "forced"


def test_decide_pending_realtime_cycle_handles_not_pending_debounced_and_due() -> None:
    """Ensure pending realtime work distinguishes absent, debounced, and due execution states."""
    not_pending = decide_pending_realtime_cycle(
        pending=False,
        now_monotonic=100.0,
        last_run_monotonic=0.0,
        min_trigger_interval_ms=200,
    )
    debounced = decide_pending_realtime_cycle(
        pending=True,
        now_monotonic=100.1,
        last_run_monotonic=100.0,
        min_trigger_interval_ms=200,
    )
    due = decide_pending_realtime_cycle(
        pending=True,
        now_monotonic=100.3,
        last_run_monotonic=100.0,
        min_trigger_interval_ms=200,
    )

    assert not_pending.should_run is False
    assert not_pending.reason == "not_pending"
    assert debounced.should_run is False
    assert debounced.reason == "debounced"
    assert due.should_run is True
    assert due.reason == "due"
