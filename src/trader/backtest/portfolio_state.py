"""Backtest portfolio seeding, normalization, and summary helpers."""

from __future__ import annotations

from datetime import datetime
import logging
from typing import Mapping, Sequence

from ..event_store import EventStore
from ..portfolio import Portfolio, PortfolioSnapshot, Position, persist_portfolio_snapshot
from ..signals import Bar
from .portfolio_core import (
    _InitialAvgPriceFill,
    _PositionSelection,
    _build_initial_portfolio,
    _fill_missing_initial_avg_prices,
    _parse_initial_cash,
    _parse_initial_position,
    _parse_initial_positions,
    _select_positions_for_symbols,
    _summarize_portfolio_positions,
)
from .data import (
    _fetch_first_prices,
    _fetch_latest_prices,
)
from .benchmark import _first_prices_from_bars
from .models import PortfolioSummary
from .replay import _latest_prices_from_bars


logger = logging.getLogger(__name__)


__all__ = [
    "_InitialAvgPriceFill",
    "_PositionSelection",
    "_build_initial_portfolio",
    "_build_portfolio_summary",
    "_fill_initial_avg_prices",
    "_fill_missing_initial_avg_prices",
    "_filter_positions",
    "_parse_initial_cash",
    "_parse_initial_position",
    "_parse_initial_positions",
    "_seed_positions",
    "_select_positions_for_symbols",
    "_summarize_portfolio_positions",
]


def _build_portfolio_summary(
    event_store: EventStore,
    asset_class: str,
    timeframe: str,
    *,
    portfolio: Portfolio | None = None,
    bars_by_symbol: Mapping[str, Sequence[Bar]] | None = None,
) -> PortfolioSummary:
    """Build final position and notional metrics for a backtest result.

    Prices come from the provided in-memory bars when available, otherwise the
    function queries the event store for the latest bar per open position. A
    missing price leaves notional and unrealized-PnL fields unset for that
    symbol rather than inventing a valuation.
    """
    portfolio = portfolio or Portfolio.from_event_store(event_store)
    positions = list(portfolio.positions.values())
    if bars_by_symbol is not None:
        latest_prices = _latest_prices_from_bars(bars_by_symbol)
    else:
        latest_prices = _fetch_latest_prices(
            event_store,
            asset_class,
            [position.symbol for position in positions],
            timeframe,
        )
    return _summarize_portfolio_positions(positions, latest_prices)


def _filter_positions(positions: Sequence[Position], symbols: set[str]) -> list[Position]:
    """Drop initial positions outside the selected backtest symbol universe."""
    selection = _select_positions_for_symbols(positions, symbols)
    for symbol in selection.ignored_symbols:
        logger.warning("Initial position ignored; symbol not in backtest symbols: %s", symbol)
    return list(selection.selected)


def _fill_initial_avg_prices(
    event_store: EventStore,
    asset_class: str,
    timeframe: str,
    start: datetime,
    positions: Sequence[Position],
    *,
    bars_by_symbol: Mapping[str, Sequence[Bar]] | None = None,
) -> list[Position]:
    """Fill missing initial average prices from first available market data."""
    if not positions:
        return []
    missing = [position.symbol for position in positions if position.avg_price is None]
    if not missing:
        return list(positions)
    if bars_by_symbol is not None:
        first_prices = _first_prices_from_bars(bars_by_symbol, start)
    else:
        first_prices = _fetch_first_prices(event_store, asset_class, missing, timeframe, start)
    fill_result = _fill_missing_initial_avg_prices(positions, first_prices)
    for symbol in fill_result.missing_price_symbols:
        logger.warning(
            "Initial position avg_price missing and no first bar found symbol=%s",
            symbol,
        )
    return list(fill_result.positions)


def _seed_positions(
    event_store: EventStore,
    positions: Sequence[Position],
    *,
    asof_ts: datetime,
    cash_balance: float,
    run_id: str | None,
) -> None:
    """Persist initial backtest portfolio state before the first replay cycle."""
    snapshot = PortfolioSnapshot(
        asof_ts=asof_ts,
        positions=tuple(positions),
        cash_balance=cash_balance,
        run_id=run_id,
        session_id=run_id,
    )
    persist_portfolio_snapshot(snapshot, event_store)
