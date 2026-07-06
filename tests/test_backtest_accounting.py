"""Scenario tests for deterministic backtest accounting."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from tests.support.duckdb_store import DuckDBEventStore
from trader.market_data import CryptoBarEvent, StockBarEvent
from trader.backtest import (
    BacktestAssumptions,
    EquityPoint,
    PortfolioSummary,
    PositionSummary,
    TradeRecord,
    _build_performance_summary,
    _compute_trade_stats,
)
from trader.backtest.benchmark import (
    _allocate_buy_hold_cash,
    _compute_equity,
    _compute_portfolio_state_equity,
    _first_price_from_bars,
)
from trader.backtest.result_builders import (
    _build_completed_backtest_result,
    _build_empty_backtest_result,
)
from trader.backtest.data_queries import (
    _bar_event_table_name,
    _build_symbol_schedule,
)
from trader.backtest.models import (
    FillAccountingEvent as _FillAccountingEvent,
    OrderAccountingEvent as _OrderAccountingEvent,
    TradeStats as _TradeStats,
)
from trader.backtest.performance import (
    _RelativeMetrics,
    _build_relative_metrics_from_returns,
    _empty_performance_summary,
    _summarize_exposure_samples,
    _summarize_return_performance,
)
from trader.backtest.portfolio_state import (
    _fill_missing_initial_avg_prices,
    _parse_initial_position,
    _select_positions_for_symbols,
    _summarize_portfolio_positions,
)
from trader.backtest.replay import (
    _advance_price_cursors,
    _build_market_event,
    _latest_price_from_bars,
    _select_backtest_bar,
)
from trader.backtest.trade_accounting import (
    _PositionAccountingState,
    _apply_fill_to_position_state,
    _compute_trade_stats_from_events,
    _compute_turnover,
    _summarize_realized_trade_pnls,
)
from trader.portfolio import Portfolio, PortfolioState, Position
from trader.signals import Bar


def test_portfolio_apply_orders_supports_fee_amount() -> None:
    portfolio = Portfolio.empty(cash_balance=1000.0)

    portfolio.apply_orders(
        [{"symbol": "AAPL", "side": "buy", "qty": 1.0, "price": 100.0, "fee_amount": 0.5}]
    )
    assert portfolio.positions["AAPL"].qty == 1.0
    assert portfolio.positions["AAPL"].avg_price == 100.0
    assert portfolio.cash_balance == pytest.approx(899.5)

    portfolio.apply_orders(
        [{"symbol": "AAPL", "side": "sell", "qty": 1.0, "price": 110.0, "fee_amount": 0.5}]
    )
    assert "AAPL" not in portfolio.positions
    assert portfolio.cash_balance == pytest.approx(1009.0)


def test_portfolio_average_price_after_multiple_buys() -> None:
    portfolio = Portfolio.empty(cash_balance=1000.0)
    portfolio.apply_orders([{"symbol": "AAPL", "side": "buy", "qty": 1.0, "price": 100.0}])
    portfolio.apply_orders([{"symbol": "AAPL", "side": "buy", "qty": 3.0, "price": 110.0}])

    position = portfolio.positions["AAPL"]
    assert position.qty == 4.0
    assert position.avg_price == pytest.approx(107.5)
    assert portfolio.cash_balance == pytest.approx(570.0)


def test_bar_event_table_name_selects_asset_specific_storage_table() -> None:
    assert _bar_event_table_name("stocks") == "stock_bar_events"
    assert _bar_event_table_name("equities") == "stock_bar_events"
    assert _bar_event_table_name("crypto") == "crypto_bar_events"
    assert _bar_event_table_name("cryptocurrency") == "crypto_bar_events"


def test_compute_equity_returns_named_valuation_and_skips_unpriced_positions() -> None:
    portfolio = Portfolio(
        positions={
            "AAPL": Position(symbol="AAPL", qty=2.0, avg_price=90.0),
            "MSFT": Position(symbol="MSFT", qty=-1.0, avg_price=210.0),
            "TSLA": Position(symbol="TSLA", qty=3.0, avg_price=20.0),
        },
        cash_balance=1000.0,
    )

    valuation = _compute_equity(portfolio, {"AAPL": 100.0, "MSFT": 200.0})

    assert valuation.equity == pytest.approx(1000.0)
    assert valuation.net_notional == pytest.approx(0.0)
    assert valuation.gross_notional == pytest.approx(400.0)
    assert valuation.invested_pct == pytest.approx(0.4)


def test_compute_equity_leaves_invested_pct_empty_when_equity_is_zero() -> None:
    portfolio = Portfolio(
        positions={"AAPL": Position(symbol="AAPL", qty=-1.0, avg_price=100.0)},
        cash_balance=100.0,
    )

    valuation = _compute_equity(portfolio, {"AAPL": 100.0})

    assert valuation.equity == 0.0
    assert valuation.net_notional == pytest.approx(-100.0)
    assert valuation.gross_notional == pytest.approx(100.0)
    assert valuation.invested_pct is None


def test_compute_portfolio_state_equity_uses_immutable_state() -> None:
    state = PortfolioState(
        positions={
            "AAPL": Position(symbol="AAPL", qty=2.0, avg_price=90.0),
            "MSFT": Position(symbol="MSFT", qty=-1.0, avg_price=210.0),
        },
        cash_balance=1000.0,
    )

    valuation = _compute_portfolio_state_equity(state, {"AAPL": 100.0, "MSFT": 200.0})

    assert valuation.equity == pytest.approx(1000.0)
    assert valuation.net_notional == pytest.approx(0.0)
    assert valuation.gross_notional == pytest.approx(400.0)
    assert valuation.invested_pct == pytest.approx(0.4)


def test_allocate_buy_hold_cash_adds_equal_weight_quantities_to_existing_holdings() -> None:
    holdings = _allocate_buy_hold_cash(
        holdings={"AAPL": 1.0},
        cash_balance=600.0,
        symbols=("AAPL", "MSFT"),
        first_prices={"AAPL": 100.0, "MSFT": 50.0},
    )

    assert holdings.cash_balance == 0.0
    assert holdings.positions["AAPL"] == pytest.approx(4.0)
    assert holdings.positions["MSFT"] == pytest.approx(6.0)


def test_allocate_buy_hold_cash_preserves_cash_when_no_symbols_have_prices() -> None:
    holdings = _allocate_buy_hold_cash(
        holdings={"AAPL": 1.0},
        cash_balance=600.0,
        symbols=("AAPL", "MSFT"),
        first_prices={},
    )

    assert holdings.cash_balance == 600.0
    assert holdings.positions == {"AAPL": 1.0}


def test_allocate_buy_hold_cash_preserves_zero_price_allocation_semantics() -> None:
    holdings = _allocate_buy_hold_cash(
        holdings={},
        cash_balance=600.0,
        symbols=("AAPL", "MSFT"),
        first_prices={"AAPL": 0.0, "MSFT": 50.0},
    )

    assert holdings.cash_balance == 0.0
    assert "AAPL" not in holdings.positions
    assert holdings.positions["MSFT"] == pytest.approx(6.0)


def test_parse_initial_position_normalizes_symbol_and_numeric_fields() -> None:
    position = _parse_initial_position(
        {
            "symbol": " aapl ",
            "qty": "2.5",
            "avg_price": "100.25",
        }
    )

    assert position == Position(symbol="AAPL", qty=2.5, avg_price=100.25)


def test_parse_initial_position_rejects_invalid_entries() -> None:
    with pytest.raises(ValueError, match="entries must be mappings"):
        _parse_initial_position("AAPL")
    with pytest.raises(ValueError, match="requires symbol"):
        _parse_initial_position({"qty": 1.0})
    with pytest.raises(ValueError, match="requires qty"):
        _parse_initial_position({"symbol": "AAPL"})
    with pytest.raises(ValueError, match="Invalid qty"):
        _parse_initial_position({"symbol": "AAPL", "qty": "not-a-number"})
    with pytest.raises(ValueError, match="Invalid avg_price"):
        _parse_initial_position({"symbol": "AAPL", "qty": 1.0, "avg_price": "not-a-number"})


def test_summarize_portfolio_positions_values_longs_shorts_and_unpriced_positions() -> None:
    base_ts = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)

    summary = _summarize_portfolio_positions(
        (
            Position(symbol="MSFT", qty=-2.0, avg_price=50.0),
            Position(symbol="AAPL", qty=3.0, avg_price=90.0),
            Position(symbol="TSLA", qty=4.0, avg_price=20.0),
        ),
        {
            "AAPL": (base_ts, 100.0),
            "MSFT": (base_ts, 40.0),
        },
    )

    assert summary.position_count == 3
    assert summary.long_positions == 2
    assert summary.short_positions == 1
    assert summary.net_qty == pytest.approx(5.0)
    assert summary.gross_qty == pytest.approx(9.0)
    assert summary.net_notional == pytest.approx((3.0 * 100.0) + (-2.0 * 40.0) + (4.0 * 20.0))
    assert summary.gross_notional == pytest.approx(300.0 + 80.0 + 80.0)
    assert [position.symbol for position in summary.positions] == ["AAPL", "MSFT", "TSLA"]
    assert summary.positions[0].market_value == pytest.approx(300.0)
    assert summary.positions[0].unrealized_pnl == pytest.approx(30.0)
    assert summary.positions[1].market_value == pytest.approx(-80.0)
    assert summary.positions[1].unrealized_pnl == pytest.approx(20.0)
    assert summary.positions[2].last_price is None
    assert summary.positions[2].market_value is None
    assert summary.positions[2].unrealized_pnl is None


def test_summarize_portfolio_positions_leaves_notional_empty_without_price_basis() -> None:
    summary = _summarize_portfolio_positions(
        (Position(symbol="AAPL", qty=3.0, avg_price=None),),
        {},
    )

    assert summary.position_count == 1
    assert summary.net_qty == pytest.approx(3.0)
    assert summary.gross_qty == pytest.approx(3.0)
    assert summary.net_notional is None
    assert summary.gross_notional is None
    assert summary.positions[0].last_price is None
    assert summary.positions[0].market_value is None


def test_select_positions_for_symbols_reports_ignored_positions_without_logging() -> None:
    positions = (
        Position(symbol="AAPL", qty=1.0, avg_price=100.0),
        Position(symbol="MSFT", qty=2.0, avg_price=50.0),
        Position(symbol="TSLA", qty=3.0, avg_price=20.0),
    )

    selection = _select_positions_for_symbols(positions, {"AAPL", "TSLA"})

    assert selection.selected == (positions[0], positions[2])
    assert selection.ignored_symbols == ("MSFT",)


def test_select_positions_for_symbols_keeps_all_positions_when_universe_is_empty() -> None:
    positions = (
        Position(symbol="AAPL", qty=1.0, avg_price=100.0),
        Position(symbol="MSFT", qty=2.0, avg_price=50.0),
    )

    selection = _select_positions_for_symbols(positions, set())

    assert selection.selected == positions
    assert selection.ignored_symbols == ()


def test_fill_missing_initial_avg_prices_uses_first_prices_without_mutation() -> None:
    positions = (
        Position(symbol="AAPL", qty=1.0, avg_price=None),
        Position(symbol="MSFT", qty=2.0, avg_price=55.0),
        Position(symbol="TSLA", qty=3.0, avg_price=None),
    )

    result = _fill_missing_initial_avg_prices(positions, {"AAPL": 100.0})

    assert result.positions == (
        Position(symbol="AAPL", qty=1.0, avg_price=100.0),
        Position(symbol="MSFT", qty=2.0, avg_price=55.0),
        Position(symbol="TSLA", qty=3.0, avg_price=None),
    )
    assert result.missing_price_symbols == ("TSLA",)
    assert positions[0].avg_price is None


def test_fill_missing_initial_avg_prices_reports_all_unresolved_symbols() -> None:
    result = _fill_missing_initial_avg_prices(
        (
            Position(symbol="AAPL", qty=1.0, avg_price=None),
            Position(symbol="MSFT", qty=2.0, avg_price=None),
        ),
        {},
    )

    assert result.positions == (
        Position(symbol="AAPL", qty=1.0, avg_price=None),
        Position(symbol="MSFT", qty=2.0, avg_price=None),
    )
    assert result.missing_price_symbols == ("AAPL", "MSFT")


def test_select_backtest_bar_returns_exact_match_without_warning() -> None:
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
    assert selection.warning == "Missing exact bar for AAPL at 2026-01-20T12:01:00+00:00; skipped symbol."
    assert selection.warning_kind == "missing_exact"


def test_select_backtest_bar_reports_no_prior_bar_when_fallback_has_no_candidate() -> None:
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
    assert selection.warning == "No prior bar available for AAPL at 2026-01-20T12:01:00+00:00; skipped symbol."
    assert selection.warning_kind == "no_prior"


def test_select_backtest_bar_uses_latest_prior_bar_when_allowed() -> None:
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
    base_ts = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    bars = (
        _bar(base_ts, 100.0),
        _bar(base_ts.replace(minute=1), 101.0),
        _bar(base_ts.replace(minute=2), 102.0),
    )

    assert _first_price_from_bars(bars, base_ts.replace(minute=1)) == 101.0
    assert _first_price_from_bars(bars, base_ts.replace(minute=3)) is None


def test_advance_price_cursors_returns_exact_timestamp_prices_without_mutation() -> None:
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


def test_apply_fill_to_position_state_opens_and_adds_long_position() -> None:
    opened = _apply_fill_to_position_state(None, side="buy", qty=2.0, effective_unit_price=100.0)
    assert opened.state == _PositionAccountingState(qty=2.0, avg_price=100.0)
    assert opened.realized_pnl is None

    added = _apply_fill_to_position_state(
        opened.state,
        side="buy",
        qty=2.0,
        effective_unit_price=110.0,
    )

    assert added.state == _PositionAccountingState(qty=4.0, avg_price=105.0)
    assert added.realized_pnl is None


def test_apply_fill_to_position_state_closes_and_reverses_long_position() -> None:
    current = _PositionAccountingState(qty=2.0, avg_price=100.0)

    reduced = _apply_fill_to_position_state(
        current,
        side="sell",
        qty=1.0,
        effective_unit_price=110.0,
    )
    assert reduced.state == _PositionAccountingState(qty=1.0, avg_price=100.0)
    assert reduced.realized_pnl == pytest.approx(10.0)

    closed = _apply_fill_to_position_state(
        current,
        side="sell",
        qty=2.0,
        effective_unit_price=95.0,
    )
    assert closed.state is None
    assert closed.realized_pnl == pytest.approx(-10.0)

    reversed_position = _apply_fill_to_position_state(
        current,
        side="sell",
        qty=3.0,
        effective_unit_price=90.0,
    )
    assert reversed_position.state == _PositionAccountingState(qty=-1.0, avg_price=90.0)
    assert reversed_position.realized_pnl == pytest.approx(-20.0)


def test_apply_fill_to_position_state_adds_and_reverses_short_position() -> None:
    current = _PositionAccountingState(qty=-1.0, avg_price=100.0)

    added = _apply_fill_to_position_state(
        current,
        side="sell",
        qty=3.0,
        effective_unit_price=90.0,
    )
    assert added.state == _PositionAccountingState(qty=-4.0, avg_price=92.5)
    assert added.realized_pnl is None

    reversed_position = _apply_fill_to_position_state(
        _PositionAccountingState(qty=-2.0, avg_price=50.0),
        side="buy",
        qty=3.0,
        effective_unit_price=45.0,
    )
    assert reversed_position.state == _PositionAccountingState(qty=1.0, avg_price=45.0)
    assert reversed_position.realized_pnl == pytest.approx(10.0)


def test_compute_turnover_uses_average_equity_when_available() -> None:
    base_ts = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)

    turnover = _compute_turnover(
        traded_notional=300.0,
        equity_curve=(
            EquityPoint(ts=base_ts, equity=100.0),
            EquityPoint(ts=base_ts, equity=200.0),
        ),
    )

    assert turnover == pytest.approx(2.0)


def test_compute_turnover_is_empty_without_average_equity() -> None:
    base_ts = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)

    assert _compute_turnover(traded_notional=300.0, equity_curve=()) is None
    assert _compute_turnover(
        traded_notional=300.0,
        equity_curve=(EquityPoint(ts=base_ts, equity=0.0),),
    ) is None


def test_trade_stats_capture_fees_slippage_and_realized_pnl(tmp_path) -> None:
    store = DuckDBEventStore(str(tmp_path / "events.duckdb"))
    base_ts = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)

    _record_order(store, "cid_buy", "cycle_1", "AAPL", "buy", 1.0, base_ts)
    _record_fill(
        store,
        "cid_buy",
        "cycle_1",
        fill_ts=base_ts,
        fill_qty=1.0,
        raw_fill_price=100.0,
        fill_price=100.1,
        fee_amount=0.1,
        slippage_amount=0.1,
    )
    _record_order(store, "cid_sell", "cycle_2", "AAPL", "sell", 1.0, base_ts)
    _record_fill(
        store,
        "cid_sell",
        "cycle_2",
        fill_ts=base_ts,
        fill_qty=1.0,
        raw_fill_price=110.0,
        fill_price=109.89,
        fee_amount=0.1,
        slippage_amount=0.11,
    )

    stats = _compute_trade_stats(
        store,
        "run_1",
        [
            EquityPoint(ts=base_ts, equity=1000.0),
            EquityPoint(ts=base_ts, equity=1009.59),
        ],
    )

    assert stats is not None
    assert stats.trade_count == 1
    assert stats.realized_pnl == pytest.approx(9.59)
    assert stats.total_fees == pytest.approx(0.2)
    assert stats.total_slippage == pytest.approx(0.21)
    assert stats.turnover == pytest.approx((100.1 + 109.89) / ((1000.0 + 1009.59) / 2.0))
    assert len(stats.trades) == 2
    assert stats.trades[0].realized_pnl is None
    assert stats.trades[1].realized_pnl == pytest.approx(9.59)


def test_trade_stats_from_events_is_database_free_and_deterministic() -> None:
    base_ts = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)

    stats = _compute_trade_stats_from_events(
        order_events=(
            _OrderAccountingEvent("cid_buy", "AAPL", "buy", "cycle_1"),
            _OrderAccountingEvent("cid_buy", "AAPL", "buy", "duplicate_ignored"),
            _OrderAccountingEvent("cid_sell", "AAPL", "sell", "cycle_2"),
        ),
        fill_events=(
            _FillAccountingEvent("cid_buy", base_ts, 1.0, 100.1, 100.0, 0.1, 0.1),
            _FillAccountingEvent("cid_sell", base_ts, 1.0, 109.89, 110.0, 0.1, 0.11),
        ),
        equity_curve=(
            EquityPoint(ts=base_ts, equity=1000.0),
            EquityPoint(ts=base_ts, equity=1009.59),
        ),
    )

    assert stats.trade_count == 1
    assert stats.hit_rate == 1.0
    assert stats.realized_pnl == pytest.approx(9.59)
    assert stats.total_fees == pytest.approx(0.2)
    assert stats.total_slippage == pytest.approx(0.21)
    assert len(stats.trades) == 2
    assert stats.trades[0].cycle_id == "cycle_1"
    assert stats.trades[1].realized_pnl == pytest.approx(9.59)


def test_trade_stats_from_events_ignores_unmatched_and_invalid_fills() -> None:
    base_ts = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)

    stats = _compute_trade_stats_from_events(
        order_events=(
            _OrderAccountingEvent("cid_valid", "AAPL", "buy", "cycle_1"),
        ),
        fill_events=(
            _FillAccountingEvent(None, base_ts, 1.0, 100.0, None, 0.0, 0.0),
            _FillAccountingEvent("missing_order", base_ts, 1.0, 100.0, None, 0.0, 0.0),
            _FillAccountingEvent("cid_valid", base_ts, 0.0, 100.0, None, 0.0, 0.0),
            _FillAccountingEvent("cid_valid", base_ts, 1.0, 0.0, None, 0.0, 0.0),
        ),
        equity_curve=(EquityPoint(ts=base_ts, equity=1000.0),),
    )

    assert stats.trade_count == 0
    assert stats.realized_pnl is None
    assert stats.total_fees == 0.0
    assert stats.total_slippage == 0.0
    assert stats.trades == ()


def test_build_empty_backtest_result_uses_explicit_values() -> None:
    timestamp = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    assumptions = BacktestAssumptions()

    result = _build_empty_backtest_result(
        asset_class="stocks",
        symbols=("AAPL", "MSFT"),
        timeframe="1Min",
        assumptions=assumptions,
        run_id="run_empty",
        timestamp=timestamp,
        warning="No bars found for backtest window.",
    )

    assert result.run_id == "run_empty"
    assert result.started_at == timestamp
    assert result.finished_at == timestamp
    assert result.duration_seconds == 0.0
    assert result.asset_class == "stocks"
    assert result.symbols == ("AAPL", "MSFT")
    assert result.assumptions == assumptions
    assert result.warnings == ("No bars found for backtest window.",)
    assert result.strategy_performance.start_equity is None
    assert result.benchmark_performance.start_equity is None


def test_build_completed_backtest_result_maps_summaries_and_metrics() -> None:
    started_at = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    finished_at = datetime(2026, 1, 20, 12, 1, tzinfo=timezone.utc)
    position = PositionSummary(
        symbol="AAPL",
        qty=2.0,
        avg_price=100.0,
        last_price=110.0,
        last_ts=finished_at,
        market_value=220.0,
        unrealized_pnl=20.0,
    )
    trade = TradeRecord(
        client_order_id="cid_1",
        cycle_id="cycle_1",
        symbol="AAPL",
        side="sell",
        fill_ts=finished_at,
        fill_qty=1.0,
        raw_fill_price=110.0,
        fill_price=109.9,
        fee_amount=0.1,
        slippage_amount=0.1,
        notional=109.9,
        realized_pnl=9.9,
    )
    performance = _empty_performance_summary()

    result = _build_completed_backtest_result(
        total_runs=3,
        failed_runs=1,
        started_at=started_at,
        finished_at=finished_at,
        asset_class="stocks",
        symbols=("AAPL",),
        timeframe="1Min",
        portfolio_summary=PortfolioSummary(
            position_count=1,
            long_positions=1,
            short_positions=0,
            net_qty=2.0,
            gross_qty=2.0,
            net_notional=220.0,
            gross_notional=220.0,
            positions=(position,),
        ),
        assumptions=BacktestAssumptions(),
        warnings=("warning",),
        trade_stats=_TradeStats(
            trade_count=1,
            hit_rate=1.0,
            profit_factor=None,
            expectancy=9.9,
            avg_win=9.9,
            avg_loss=None,
            turnover=0.2,
            realized_pnl=9.9,
            trades=(trade,),
            total_fees=0.1,
            total_slippage=0.1,
        ),
        strategy_performance=performance,
        benchmark_performance=performance,
        relative_metrics=_RelativeMetrics(
            tracking_error=0.1,
            information_ratio=0.2,
            alpha=0.3,
            beta=0.4,
        ),
        equity_curve=(EquityPoint(ts=started_at, equity=1000.0),),
        benchmark_curve=(EquityPoint(ts=started_at, equity=990.0),),
        run_id="run_1",
    )

    assert result.total_runs == 3
    assert result.success_runs == 2
    assert result.failed_runs == 1
    assert result.duration_seconds == 60.0
    assert result.positions == (position,)
    assert result.trades == (trade,)
    assert result.total_fees == 0.1
    assert result.total_slippage == 0.1
    assert result.tracking_error == 0.1
    assert result.information_ratio == 0.2
    assert result.alpha == 0.3
    assert result.beta == 0.4
    assert result.warnings == ("warning",)


def test_summarize_exposure_samples_handles_missing_invested_values() -> None:
    empty = _summarize_exposure_samples(())
    assert empty.avg_net_exposure is None
    assert empty.avg_gross_exposure is None
    assert empty.avg_invested_pct is None

    summary = _summarize_exposure_samples(
        (
            (100.0, 120.0, 0.60),
            (-50.0, 80.0, None),
            (25.0, 25.0, 0.25),
        )
    )

    assert summary.avg_net_exposure == pytest.approx(25.0)
    assert summary.avg_gross_exposure == pytest.approx(75.0)
    assert summary.avg_invested_pct == pytest.approx(0.425)


def test_build_relative_metrics_from_returns_aligns_and_scores_series() -> None:
    returns = (0.02, -0.01, 0.03, 0.99)
    benchmark_returns = (0.01, 0.0, 0.02)

    metrics = _build_relative_metrics_from_returns(
        returns=returns,
        benchmark_returns=benchmark_returns,
        periods_per_year=4.0,
    )

    aligned_returns = returns[:3]
    excess = [value - benchmark for value, benchmark in zip(aligned_returns, benchmark_returns)]
    excess_mean = sum(excess) / len(excess)
    excess_variance = sum((value - excess_mean) ** 2 for value in excess) / len(excess)
    excess_std = excess_variance ** 0.5
    benchmark_mean = sum(benchmark_returns) / len(benchmark_returns)
    return_mean = sum(aligned_returns) / len(aligned_returns)
    benchmark_variance = sum((value - benchmark_mean) ** 2 for value in benchmark_returns) / len(benchmark_returns)
    covariance = sum(
        (value - return_mean) * (benchmark - benchmark_mean)
        for value, benchmark in zip(aligned_returns, benchmark_returns)
    ) / len(aligned_returns)
    expected_beta = covariance / benchmark_variance

    assert metrics.tracking_error == pytest.approx(excess_std * 2.0)
    assert metrics.information_ratio == pytest.approx((excess_mean / excess_std) * 2.0)
    assert metrics.beta == pytest.approx(expected_beta)
    assert metrics.alpha == pytest.approx((return_mean - expected_beta * benchmark_mean) * 4.0)


def test_build_relative_metrics_from_returns_handles_missing_or_identical_series() -> None:
    empty = _build_relative_metrics_from_returns(
        returns=(),
        benchmark_returns=(0.01,),
        periods_per_year=4.0,
    )
    identical = _build_relative_metrics_from_returns(
        returns=(0.01, 0.02),
        benchmark_returns=(0.01, 0.02),
        periods_per_year=4.0,
    )

    assert empty.tracking_error is None
    assert empty.information_ratio is None
    assert empty.alpha is None
    assert empty.beta is None
    assert identical.tracking_error is None
    assert identical.information_ratio is None
    assert identical.alpha == pytest.approx(0.0)
    assert identical.beta == pytest.approx(1.0)


def test_summarize_return_performance_reports_curve_metrics() -> None:
    base_ts = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    metrics = _summarize_return_performance(
        (
            EquityPoint(ts=base_ts, equity=100.0),
            EquityPoint(ts=base_ts, equity=90.0),
            EquityPoint(ts=base_ts, equity=99.0),
        ),
        periods_per_year=4.0,
    )

    assert metrics.start_equity == 100.0
    assert metrics.end_equity == 99.0
    assert metrics.total_return == pytest.approx(-0.01)
    assert metrics.volatility is not None
    assert metrics.sharpe is not None
    assert metrics.sortino is None
    assert metrics.max_drawdown == pytest.approx(0.1)
    assert metrics.max_drawdown_duration == 2
    assert metrics.ulcer_index is not None


def test_summarize_return_performance_handles_zero_starting_equity() -> None:
    base_ts = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    metrics = _summarize_return_performance(
        (
            EquityPoint(ts=base_ts, equity=0.0),
            EquityPoint(ts=base_ts, equity=10.0),
        ),
        periods_per_year=4.0,
    )

    assert metrics.start_equity == 0.0
    assert metrics.end_equity == 10.0
    assert metrics.total_return is None
    assert metrics.cagr is None


def test_summarize_realized_trade_pnls_handles_empty_and_mixed_outcomes() -> None:
    empty = _summarize_realized_trade_pnls(())
    assert empty.trade_count == 0
    assert empty.hit_rate is None
    assert empty.realized_pnl is None

    summary = _summarize_realized_trade_pnls((10.0, -4.0, 0.0))

    assert summary.trade_count == 3
    assert summary.hit_rate == pytest.approx(1.0 / 3.0)
    assert summary.avg_win == pytest.approx(10.0)
    assert summary.avg_loss == pytest.approx(-4.0)
    assert summary.profit_factor == pytest.approx(2.5)
    assert summary.expectancy == pytest.approx((1.0 / 3.0 * 10.0) + (2.0 / 3.0 * -4.0))
    assert summary.realized_pnl == pytest.approx(6.0)


def test_summarize_realized_trade_pnls_leaves_profit_factor_empty_without_losses() -> None:
    summary = _summarize_realized_trade_pnls((2.0, 3.0))

    assert summary.trade_count == 2
    assert summary.hit_rate == 1.0
    assert summary.profit_factor is None
    assert summary.expectancy == pytest.approx(2.5)
    assert summary.realized_pnl == pytest.approx(5.0)


def test_trade_stats_partial_fill_keeps_open_position_without_realized_pnl(tmp_path) -> None:
    store = DuckDBEventStore(str(tmp_path / "events.duckdb"))
    base_ts = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)

    _record_order(store, "cid_partial", "cycle_partial", "AAPL", "buy", 2.0, base_ts)
    _record_fill(
        store,
        "cid_partial",
        "cycle_partial",
        fill_ts=base_ts,
        fill_qty=1.0,
        raw_fill_price=100.0,
        fill_price=100.0,
        fee_amount=0.0,
        slippage_amount=0.0,
    )

    stats = _compute_trade_stats(store, "run_1", [EquityPoint(ts=base_ts, equity=1000.0)])

    assert stats is not None
    assert stats.trade_count == 0
    assert stats.realized_pnl is None
    assert len(stats.trades) == 1
    assert stats.trades[0].fill_qty == 1.0


def test_performance_summary_uses_known_turnover_and_drawdown() -> None:
    base_ts = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    summary = _build_performance_summary(
        [
            EquityPoint(ts=base_ts, equity=1000.0),
            EquityPoint(ts=base_ts, equity=900.0),
            EquityPoint(ts=base_ts, equity=990.0),
        ],
        "1Min",
        exposure_samples=[
            (500.0, 500.0, 0.5),
            (200.0, 200.0, 200.0 / 900.0),
            (0.0, 0.0, 0.0),
        ],
        trade_stats=None,
    )

    assert summary.max_drawdown == pytest.approx(0.1)
    assert summary.max_drawdown_duration == 2
    assert summary.avg_net_exposure == pytest.approx((500.0 + 200.0 + 0.0) / 3.0)
    assert summary.avg_gross_exposure == pytest.approx((500.0 + 200.0 + 0.0) / 3.0)
    assert summary.avg_invested_pct == pytest.approx((0.5 + (200.0 / 900.0) + 0.0) / 3.0)


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


def _record_order(
    store: DuckDBEventStore,
    client_order_id: str,
    cycle_id: str,
    symbol: str,
    side: str,
    qty: float,
    created_at: datetime,
) -> None:
    store.record_event(
        "order_events",
        {
            "order_event_id": f"order_evt_{client_order_id}",
            "client_order_id": client_order_id,
            "run_id": "run_1",
            "session_id": "run_1",
            "cycle_id": cycle_id,
            "symbol": symbol,
            "side": side,
            "qty": qty,
            "order_type": "market",
            "status": "filled",
            "broker_order_id": None,
            "rejection_reason": None,
            "created_at": created_at,
        },
    )


def _record_fill(
    store: DuckDBEventStore,
    client_order_id: str,
    cycle_id: str,
    *,
    fill_ts: datetime,
    fill_qty: float,
    raw_fill_price: float,
    fill_price: float,
    fee_amount: float,
    slippage_amount: float,
) -> None:
    store.record_event(
        "fill_events",
        {
            "client_order_id": client_order_id,
            "run_id": "run_1",
            "session_id": "run_1",
            "cycle_id": cycle_id,
            "fill_ts": fill_ts,
            "fill_qty": fill_qty,
            "raw_fill_price": raw_fill_price,
            "fill_price": fill_price,
            "slippage_amount": slippage_amount,
            "fee_amount": fee_amount,
        },
    )
