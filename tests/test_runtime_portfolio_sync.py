"""Pure tests for broker portfolio sync value builders."""

from __future__ import annotations

from trader.runtime.portfolio_sync import (
    build_initial_portfolio_seed,
    build_broker_portfolio_sync_snapshot,
    format_broker_portfolio_mismatch,
    matched_position_log_records,
    mismatched_position_log_records,
    resolve_initial_portfolio_seed_config,
)


def test_broker_portfolio_sync_snapshot_preserves_all_positions_and_flags_mismatches() -> None:
    snapshot = build_broker_portfolio_sync_snapshot(
        account={"cash": "1000.25"},
        positions_raw=[
            {
                "symbol": "BTCUSD",
                "asset_class": "crypto",
                "qty": "0.5",
                "avg_entry_price": "42000.0",
                "side": "long",
            },
            {
                "symbol": "AAPL",
                "asset_class": "us_equity",
                "qty": "2",
                "avg_entry_price": "190.0",
                "side": "long",
            },
        ],
        configured_symbols=("BTC/USD",),
        configured_asset_class="crypto",
    )

    assert snapshot.cash == 1000.25
    assert snapshot.configured_symbols == frozenset({"BTC/USD"})
    assert [(position.symbol, position.qty, position.avg_price) for position in snapshot.positions] == [
        ("BTC/USD", 0.5, 42000.0),
        ("AAPL", 2.0, 190.0),
    ]
    assert [position.symbol for position in snapshot.matched_positions] == ["BTC/USD"]
    assert [position.raw_symbol for position in snapshot.mismatches] == ["AAPL"]
    assert matched_position_log_records(snapshot) == [
        {"symbol": "BTC/USD", "asset_class": "crypto", "qty": 0.5}
    ]
    assert mismatched_position_log_records(snapshot) == [
        {
            "symbol": "AAPL",
            "asset_class": "stocks",
            "raw_symbol": "AAPL",
            "raw_asset_class": "us_equity",
            "qty": 2.0,
        }
    ]
    assert format_broker_portfolio_mismatch(snapshot.mismatches) == (
        "Broker portfolio mismatch with configured trading universe: AAPL/us_equity qty=2.0"
    )


def test_broker_portfolio_sync_snapshot_treats_missing_cash_as_zero() -> None:
    snapshot = build_broker_portfolio_sync_snapshot(
        account={"cash": None},
        positions_raw=[],
        configured_symbols=(),
        configured_asset_class="stocks",
    )

    assert snapshot.cash == 0.0
    assert snapshot.positions == ()
    assert snapshot.mismatches == ()


def test_initial_portfolio_seed_config_is_resolved_before_reading_existing_state() -> None:
    assert resolve_initial_portfolio_seed_config(
        portfolio_source="alpaca",
        config_snapshot={"trader_service": {"initial_cash": 1000}},
    ).reason == "portfolio_source_alpaca"
    assert resolve_initial_portfolio_seed_config(
        portfolio_source="db",
        config_snapshot=None,
    ).reason == "missing_config_snapshot"
    assert resolve_initial_portfolio_seed_config(
        portfolio_source="db",
        config_snapshot={"trader_service": {}},
    ).reason == "missing_seed_config"

    seed_config = resolve_initial_portfolio_seed_config(
        portfolio_source="db",
        config_snapshot={
            "trader_service": {
                "initial_cash": "1000.25",
                "initial_positions": [{"symbol": "aapl", "qty": "2", "avg_price": "100.5"}],
            }
        },
    )

    assert seed_config.should_inspect_existing is True
    assert seed_config.reason == "configured"


def test_initial_portfolio_seed_decision_respects_existing_state() -> None:
    seed_config = resolve_initial_portfolio_seed_config(
        portfolio_source="db",
        config_snapshot={"trader_service": {"initial_cash": "1000.25"}},
    )

    decision = build_initial_portfolio_seed(
        seed_config=seed_config,
        existing_positions_count=1,
        existing_cash_balance=0.0,
    )
    cash_decision = build_initial_portfolio_seed(
        seed_config=seed_config,
        existing_positions_count=0,
        existing_cash_balance=0.01,
    )

    assert decision.should_seed is False
    assert decision.reason == "existing_state"
    assert cash_decision.should_seed is False
    assert cash_decision.reason == "existing_state"


def test_initial_portfolio_seed_decision_builds_seed_positions_and_cash() -> None:
    seed_config = resolve_initial_portfolio_seed_config(
        portfolio_source="db",
        config_snapshot={
            "trader_service": {
                "initial_cash": "1000.25",
                "initial_positions": [{"symbol": "aapl", "qty": "2", "avg_price": "100.5"}],
            }
        },
    )

    decision = build_initial_portfolio_seed(
        seed_config=seed_config,
        existing_positions_count=0,
        existing_cash_balance=0.0,
    )

    assert decision.should_seed is True
    assert decision.reason == "configured"
    assert decision.cash == 1000.25
    assert [(position.symbol, position.qty, position.avg_price) for position in decision.positions] == [
        ("AAPL", 2.0, 100.5)
    ]
