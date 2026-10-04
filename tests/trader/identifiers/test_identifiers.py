"""Protect reproducible identifiers used across runs, cycles, and broker orders.

Subject: Deterministic identifier derivation from normalized domain inputs and timestamps.
Level: Pure unit contracts.
Collaborators: Identifier helpers and fixed in-memory values only.
Guarantees: Equivalent inputs repeat identifiers while material identity changes alter them.
Non-goals: Database uniqueness, distributed allocation, cryptographic secrecy, or collision analysis.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from trader.identifiers import (
    deterministic_backtest_cycle_id,
    deterministic_client_order_id,
    deterministic_cycle_id,
    deterministic_fill_event_id,
    deterministic_run_session_id,
    deterministic_signal_event_id,
)


def test_deterministic_cycle_id_stable():
    """Repeat a cycle identifier and change it when the decision timestamp changes."""
    decision_ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
    first = deterministic_cycle_id("demo", decision_ts)
    second = deterministic_cycle_id("demo", decision_ts)
    assert first == second

    different = deterministic_cycle_id("demo", decision_ts + timedelta(seconds=1))
    assert first != different


def test_backtest_cycle_identity_separates_runs_and_symbol_subsets() -> None:
    """Normalize retries while separating independent replay decisions across symbol subsets."""
    timestamp = datetime(2024, 1, 1, tzinfo=timezone.utc)
    first = deterministic_backtest_cycle_id("run-1", "demo", timestamp, (" aaa ", "bbb"))
    same = deterministic_backtest_cycle_id("run-1", "demo", timestamp, ("BBB", "AAA"))
    assert first == same
    assert first != deterministic_backtest_cycle_id("run-2", "demo", timestamp, ("AAA", "BBB"))
    assert first != deterministic_backtest_cycle_id("run-1", "demo", timestamp, ("AAA",))
    assert first != deterministic_backtest_cycle_id("run-1", "demo", timestamp, ("BBB",))


def test_deterministic_run_session_id_stable():
    """Repeat a run-session identifier and vary it with the run start time."""
    started_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
    first = deterministic_run_session_id("backtest", started_at)
    second = deterministic_run_session_id("backtest", started_at)
    assert first == second

    different = deterministic_run_session_id(
        "backtest", started_at + timedelta(seconds=1)
    )
    assert first != different


def test_deterministic_client_order_id_stable():
    """Treat equivalent symbol, side, and quantity representations as one order identity."""
    order_id = deterministic_client_order_id("cycle-1", "aapl", "BUY", 1.0)
    same = deterministic_client_order_id("cycle-1", "AAPL", "buy", "1.00000000")
    assert order_id == same


def test_deterministic_signal_event_id_stable_and_source_sensitive():
    """Keep signal identity reproducible while separating named producer inputs."""
    first = deterministic_signal_event_id("run-1", "cycle-1", "aapl", "sma")
    same = deterministic_signal_event_id("run-1", "cycle-1", "AAPL", "sma")
    different = deterministic_signal_event_id("run-1", "cycle-1", "AAPL", "rsi")

    assert first == same
    assert first != different


def test_deterministic_fill_event_id_disambiguates_repeated_fills():
    """Keep repeated identical fills distinct through an explicit sequence."""
    fill_ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
    first = deterministic_fill_event_id("order-1", fill_ts, 1.0, 100.0)
    same = deterministic_fill_event_id("order-1", fill_ts, 1.0, 100.0)
    second = deterministic_fill_event_id("order-1", fill_ts, 1.0, 100.0, sequence=1)

    assert first == same
    assert first != second
