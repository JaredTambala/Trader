"""Contracts for constructing JSON-safe runtime status payloads from query evidence.

Subject: Market-data freshness, latest orders, portfolio and halt values, and run-row normalization.
Level: Pure projection unit contracts.
Collaborators: Real status-payload builders supplied with fixed timestamps and database-shaped rows.
Guarantees: Raw status evidence becomes ordered, typed, JSON-safe operator data with explicit staleness.
Non-goals: Query execution, health severity, event persistence, CLI presentation, or runtime mutation.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from trader.runtime.status_payloads import (
    build_halt_state,
    build_market_data_status,
    build_open_orders_status,
    build_portfolio_status,
    map_run_status_row,
)


def test_market_data_status_classifies_fresh_stale_and_missing_symbols() -> None:
    """Ensure per-symbol timestamps map to fresh, stale, and missing status categories."""
    now = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)

    status = build_market_data_status(
        symbols=("AAPL", "MSFT", "TSLA"),
        timeframe="1Min",
        latest_by_symbol={
            "AAPL": now - timedelta(seconds=30),
            "MSFT": now - timedelta(seconds=90),
        },
        now=now,
        max_age_seconds=60,
    )

    assert status["missing_count"] == 1
    assert status["stale_count"] == 1
    assert status["items"] == [
        {
            "symbol": "AAPL",
            "timeframe": "1Min",
            "latest_ts": "2026-01-01T11:59:30+00:00",
            "age_seconds": 30.0,
            "missing": False,
            "stale": False,
        },
        {
            "symbol": "MSFT",
            "timeframe": "1Min",
            "latest_ts": "2026-01-01T11:58:30+00:00",
            "age_seconds": 90.0,
            "missing": False,
            "stale": True,
        },
        {
            "symbol": "TSLA",
            "timeframe": "1Min",
            "latest_ts": None,
            "age_seconds": None,
            "missing": True,
            "stale": False,
        },
    ]


def test_open_orders_status_uses_newest_order_row_per_client_order() -> None:
    """Ensure only each order's newest transition determines open and stale status."""
    now = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)

    status = build_open_orders_status(
        rows=[
            (
                "closed",
                "run",
                "session",
                "cycle",
                "AAPL",
                "buy",
                1,
                "market",
                "filled",
                "broker",
                None,
                now,
            ),
            (
                "open",
                "run",
                "session",
                "cycle",
                "MSFT",
                "sell",
                "2.5",
                "market",
                "submitted",
                "broker",
                None,
                now - timedelta(minutes=5),
            ),
            (
                "closed",
                "run",
                "session",
                "cycle",
                "AAPL",
                "buy",
                1,
                "market",
                "submitted",
                "broker",
                None,
                now - timedelta(minutes=10),
            ),
        ],
        now=now,
        stale_after_seconds=60,
    )

    assert status["count"] == 1
    assert status["stale_count"] == 1
    assert status["max_age_seconds"] == 300.0
    assert status["items"][0]["client_order_id"] == "open"
    assert status["items"][0]["qty"] == 2.5


def test_portfolio_and_halt_payloads_are_json_safe() -> None:
    """Ensure database portfolio and halt values normalize into JSON-safe public payloads."""
    now = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)

    portfolio = build_portfolio_status(
        position_rows=[("AAPL", "2.0", "100.5", 1000.0, now)],
        cash_rows=[("1000.25", now)],
    )

    assert portfolio == {
        "cash": 1000.25,
        "asof_ts": "2026-01-01T12:00:00+00:00",
        "positions": [
            {
                "symbol": "AAPL",
                "qty": 2.0,
                "avg_price": 100.5,
                "asof_ts": "2026-01-01T12:00:00+00:00",
            }
        ],
        "position_count": 1,
    }
    assert build_halt_state(
        {"halt": "yes", "halt_reason": "manual", "halt_updated_at": "ts"}
    ) == {
        "halted": True,
        "reason": "manual",
        "updated_at": "ts",
    }


def test_run_status_row_mapper_normalizes_json_symbols_and_timestamps() -> None:
    """Ensure run rows decode symbols, timestamps, and configuration into stable values."""
    now = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)

    payload = map_run_status_row(
        (
            "run",
            "trading",
            now,
            None,
            "success",
            None,
            "loop",
            '["AAPL", "MSFT"]',
            "1Min",
            "2026-01-01T00:00:00Z",
            "2026-01-01T12:00:00Z",
        )
    )

    assert payload["started_at"] == "2026-01-01T12:00:00+00:00"
    assert payload["symbols"] == ["AAPL", "MSFT"]
    assert payload["start_ts"] == "2026-01-01T00:00:00Z"
