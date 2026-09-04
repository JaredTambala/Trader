"""Backtest bar selection, scheduling, and replay-data contracts.

Subject: Asset-specific bar queries and deterministic conversion of stored bars into replay inputs.
Level: Pure data-planning unit contracts.
Collaborators: Real backtest query/replay helpers and in-memory bar values; no event store or provider.
Guarantees: Windows, fallback policy, cursor advancement, and asset types select reproducible market inputs.
Non-goals: Strategy execution, portfolio accounting, database queries, or external market-data ingestion.
"""

from __future__ import annotations

from datetime import datetime, timezone

from trader.backtest.benchmark import _first_price_from_bars
from trader.backtest.data_queries import _bar_event_table_name, _build_symbol_schedule
from trader.backtest.replay import (
    _advance_price_cursors,
    _build_market_event,
    _latest_price_from_bars,
    _select_backtest_bar,
)
from trader.market_data import CryptoBarEvent, StockBarEvent
from trader.signals import Bar


def test_bar_event_table_name_selects_asset_specific_storage_table() -> None:
    """Route stock and crypto aliases to their canonical event tables."""
    assert _bar_event_table_name("stocks") == "stock_bar_events"
    assert _bar_event_table_name("equities") == "stock_bar_events"
    assert _bar_event_table_name("crypto") == "crypto_bar_events"
    assert _bar_event_table_name("cryptocurrency") == "crypto_bar_events"


def test_select_backtest_bar_returns_exact_match_without_warning() -> None:
    """Select an exact timestamp match without emitting fallback evidence."""
    base_ts = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    bars = (_bar(base_ts, 100.0), _bar(base_ts.replace(minute=1), 101.0))

    selection = _select_backtest_bar(
        symbol="AAPL",
        bars=bars,
        timestamps=tuple(bar.ts for bar in bars),
        target=base_ts.replace(minute=1),
        allow_latest_prior_bar=True,
    )

    assert selection.bar == bars[1]
    assert selection.warning is None
    assert selection.warning_kind is None
    assert selection.latest_ts is None


def test_select_backtest_bar_rejects_missing_exact_bar_when_fallback_disabled() -> None:
    """Skip a symbol and explain the gap when exact-match policy applies."""
    base_ts = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    bars = (_bar(base_ts, 100.0),)

    selection = _select_backtest_bar(
        symbol="AAPL",
        bars=bars,
        timestamps=tuple(bar.ts for bar in bars),
        target=base_ts.replace(minute=1),
        allow_latest_prior_bar=False,
    )

    assert selection.bar is None
    assert (
        selection.warning
        == "Missing exact bar for AAPL at 2026-01-20T12:01:00+00:00; skipped symbol."
    )
    assert selection.warning_kind == "missing_exact"


def test_select_backtest_bar_reports_no_prior_bar_when_fallback_has_no_candidate() -> (
    None
):
    """Distinguish an unavailable prior bar from a disabled fallback policy."""
    base_ts = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    bars = (_bar(base_ts.replace(minute=2), 102.0),)

    selection = _select_backtest_bar(
        symbol="AAPL",
        bars=bars,
        timestamps=tuple(bar.ts for bar in bars),
        target=base_ts.replace(minute=1),
        allow_latest_prior_bar=True,
    )

    assert selection.bar is None
    assert (
        selection.warning
        == "No prior bar available for AAPL at 2026-01-20T12:01:00+00:00; skipped symbol."
    )
    assert selection.warning_kind == "no_prior"


def test_select_backtest_bar_uses_latest_prior_bar_when_allowed() -> None:
    """Select the latest prior bar and expose its timestamp in warning evidence."""
    base_ts = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    bars = (
        _bar(base_ts, 100.0),
        _bar(base_ts.replace(minute=2), 102.0),
    )

    selection = _select_backtest_bar(
        symbol="AAPL",
        bars=bars,
        timestamps=tuple(bar.ts for bar in bars),
        target=base_ts.replace(minute=1),
        allow_latest_prior_bar=True,
    )

    assert selection.bar == bars[0]
    assert selection.warning == (
        "Used latest prior bar for AAPL at 2026-01-20T12:01:00+00:00 "
        "from 2026-01-20T12:00:00+00:00."
    )
    assert selection.warning_kind == "latest_prior"
    assert selection.latest_ts == base_ts


def test_build_symbol_schedule_filters_lookback_and_out_of_window_bars() -> None:
    """Schedule only in-window timestamps while retaining their available symbols."""
    base_ts = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)

    schedule = _build_symbol_schedule(
        {
            "AAPL": (
                _bar(base_ts.replace(minute=59, hour=11), 99.0),
                _bar(base_ts, 100.0),
                _bar(base_ts.replace(minute=1), 101.0),
            ),
            "MSFT": (
                _bar(base_ts.replace(minute=1), 50.0),
                _bar(base_ts.replace(minute=2), 51.0),
            ),
        },
        start=base_ts,
        end=base_ts.replace(minute=1),
    )

    assert schedule == {
        base_ts: ["AAPL"],
        base_ts.replace(minute=1): ["AAPL", "MSFT"],
    }


def test_build_market_event_converts_bar_to_stock_or_crypto_event() -> None:
    """Create the asset-specific market event while preserving normalized bar fields."""
    base_ts = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    ingested_at = datetime(2026, 1, 20, 12, 5, tzinfo=timezone.utc)
    bar = Bar(
        ts=base_ts,
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.5,
        volume=25.0,
        vwap=100.25,
        trade_count=7.0,
    )

    stock_event = _build_market_event(
        asset_class="stocks",
        symbol="AAPL",
        timeframe="1Min",
        bar=bar,
        source="backtest",
        ingested_at=ingested_at,
    )
    crypto_event = _build_market_event(
        asset_class="crypto",
        symbol="BTC/USD",
        timeframe="1Min",
        bar=bar,
        source="backtest",
        ingested_at=ingested_at,
    )

    assert isinstance(stock_event, StockBarEvent)
    assert isinstance(crypto_event, CryptoBarEvent)
    assert stock_event.symbol == "AAPL"
    assert stock_event.close == 100.5
    assert stock_event.trade_count == 7.0
    assert stock_event.vwap == 100.25
    assert stock_event.ingested_at == ingested_at
    assert crypto_event.symbol == "BTC/USD"
    assert crypto_event.table_name == "crypto_bar_events"


def test_latest_price_from_bars_returns_normalized_last_close() -> None:
    """Return the final close with a timezone-normalized timestamp when available."""
    naive_ts = datetime(2026, 1, 20, 12, 1)

    latest = _latest_price_from_bars(
        (
            _bar(datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc), 100.0),
            _bar(naive_ts, 101.0),
        )
    )

    assert latest == (naive_ts.replace(tzinfo=timezone.utc), 101.0)
    assert _latest_price_from_bars(()) is None


def test_first_price_from_bars_returns_first_close_inside_window() -> None:
    """Select the first close within the requested benchmark allocation window."""
    base_ts = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    bars = (
        _bar(base_ts, 100.0),
        _bar(base_ts.replace(minute=1), 101.0),
        _bar(base_ts.replace(minute=2), 102.0),
    )

    assert _first_price_from_bars(bars, base_ts.replace(minute=1)) == 101.0
    assert _first_price_from_bars(bars, base_ts.replace(minute=3)) is None


def test_advance_price_cursors_returns_exact_timestamp_prices_without_mutation() -> (
    None
):
    """Advance cursors to exact prices without changing caller-owned replay state."""
    base_ts = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    bars_by_symbol = {
        "AAPL": (
            _bar(base_ts, 100.0),
            _bar(base_ts.replace(minute=2), 102.0),
        ),
        "MSFT": (_bar(base_ts.replace(minute=1), 50.0),),
    }
    indices = {"AAPL": 0, "MSFT": 0}
    previous_prices = {"AAPL": 99.0}

    advanced = _advance_price_cursors(
        bars_by_symbol,
        indices=indices,
        previous_prices=previous_prices,
        target=base_ts.replace(minute=1),
        allow_price_carry_forward=False,
    )

    assert advanced.indices == {"AAPL": 1, "MSFT": 1}
    assert advanced.prices == {"MSFT": 50.0}
    assert indices == {"AAPL": 0, "MSFT": 0}
    assert previous_prices == {"AAPL": 99.0}


def test_advance_price_cursors_carries_latest_prior_prices_forward() -> None:
    """Carry the latest known close across timestamps when replay policy permits."""
    base_ts = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    bars_by_symbol = {
        "AAPL": (
            _bar(base_ts, 100.0),
            _bar(base_ts.replace(minute=2), 102.0),
        ),
        "MSFT": (_bar(base_ts.replace(minute=1), 50.0),),
    }

    first = _advance_price_cursors(
        bars_by_symbol,
        indices={"AAPL": 0, "MSFT": 0},
        previous_prices={},
        target=base_ts.replace(minute=1),
        allow_price_carry_forward=True,
    )
    second = _advance_price_cursors(
        bars_by_symbol,
        indices=first.indices,
        previous_prices=first.prices,
        target=base_ts.replace(minute=3),
        allow_price_carry_forward=True,
    )

    assert first.indices == {"AAPL": 1, "MSFT": 1}
    assert first.prices == {"AAPL": 100.0, "MSFT": 50.0}
    assert second.indices == {"AAPL": 2, "MSFT": 1}
    assert second.prices == {"AAPL": 102.0, "MSFT": 50.0}


def _bar(ts: datetime, close: float) -> Bar:
    return Bar(
        ts=ts,
        open=close,
        high=close,
        low=close,
        close=close,
        volume=1.0,
        vwap=None,
        trade_count=None,
    )
