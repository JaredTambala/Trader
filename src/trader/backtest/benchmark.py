"""Pure benchmark and valuation helpers for backtest replay."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping, Sequence

from ..portfolio import Portfolio, PortfolioState, Position
from ..signals import Bar


@dataclass(frozen=True)
class _Holdings:
    """Cash and symbol quantities for a passive benchmark portfolio."""

    cash_balance: float
    positions: Mapping[str, float]


@dataclass(frozen=True)
class _PortfolioValuation:
    """Portfolio equity and exposure at one replay timestamp."""

    equity: float
    net_notional: float
    gross_notional: float
    invested_pct: float | None


def _build_buy_hold_baseline(
    *,
    symbols: Sequence[str],
    initial_cash: float,
    initial_positions: Sequence[Position],
    bars_by_symbol: Mapping[str, Sequence[Bar]],
    start: datetime,
) -> _Holdings:
    """Create a simple equal-weight buy-and-hold benchmark at replay start.

    Existing initial positions are preserved. Any positive initial cash is split
    equally across symbols with available first prices and converted to
    quantities; unavailable symbols receive no benchmark allocation.
    """
    holdings: dict[str, float] = {position.symbol: position.qty for position in initial_positions}
    cash_balance = float(initial_cash)
    first_prices = _first_prices_from_bars(bars_by_symbol, start)
    return _allocate_buy_hold_cash(
        holdings=holdings,
        cash_balance=cash_balance,
        symbols=symbols,
        first_prices=first_prices,
    )


def _allocate_buy_hold_cash(
    *,
    holdings: Mapping[str, float],
    cash_balance: float,
    symbols: Sequence[str],
    first_prices: Mapping[str, float],
) -> _Holdings:
    """Allocate positive cash equally across symbols with valid first prices."""
    allocated_holdings = dict(holdings)
    if cash_balance <= 0:
        return _Holdings(cash_balance=cash_balance, positions=allocated_holdings)
    alloc_symbols = [symbol for symbol in symbols if symbol in first_prices]
    if not alloc_symbols:
        return _Holdings(cash_balance=cash_balance, positions=allocated_holdings)
    allocation = cash_balance / len(alloc_symbols)
    for symbol in alloc_symbols:
        price = first_prices[symbol]
        if price <= 0:
            continue
        qty = allocation / price
        allocated_holdings[symbol] = allocated_holdings.get(symbol, 0.0) + qty
    return _Holdings(cash_balance=0.0, positions=allocated_holdings)


def _compute_equity(
    portfolio: Portfolio,
    prices: Mapping[str, float],
) -> _PortfolioValuation:
    """Compute equity, net exposure, gross exposure, and invested fraction.

    Positions without a current price are excluded from notional exposure rather
    than valued with stale or invented prices.
    """
    return _compute_portfolio_state_equity(
        PortfolioState(
            positions=portfolio.positions,
            cash_balance=portfolio.cash_balance,
        ),
        prices,
    )


def _compute_portfolio_state_equity(
    state: PortfolioState,
    prices: Mapping[str, float],
) -> _PortfolioValuation:
    """Compute valuation metrics from immutable portfolio state."""
    net_notional = 0.0
    gross_notional = 0.0
    for symbol, position in state.positions.items():
        price = prices.get(symbol)
        if price is None:
            continue
        notional = position.qty * price
        net_notional += notional
        gross_notional += abs(notional)
    equity = state.cash_balance + net_notional
    invested_pct = None
    if equity != 0:
        invested_pct = gross_notional / equity
    return _PortfolioValuation(
        equity=equity,
        net_notional=net_notional,
        gross_notional=gross_notional,
        invested_pct=invested_pct,
    )


def _compute_holdings_equity(holdings: _Holdings, prices: Mapping[str, float]) -> float:
    """Value benchmark holdings from cash plus priced symbol quantities."""
    equity = holdings.cash_balance
    for symbol, qty in holdings.positions.items():
        price = prices.get(symbol)
        if price is None:
            continue
        equity += qty * price
    return equity


def _first_prices_from_bars(
    bars_by_symbol: Mapping[str, Sequence[Bar]],
    start: datetime,
) -> dict[str, float]:
    """Return first available symbol prices from in-memory bars."""
    prices: dict[str, float] = {}
    for symbol, bars in bars_by_symbol.items():
        first = _first_price_from_bars(bars, start)
        if first is not None:
            prices[symbol] = first
    return prices


def _first_price_from_bars(bars: Sequence[Bar], start: datetime) -> float | None:
    """Return the first close price at or after start from in-memory bars."""
    start_ts = _normalize_timestamp(start)
    for bar in bars:
        if _normalize_timestamp(bar.ts) >= start_ts:
            return float(bar.close)
    return None


def _normalize_timestamp(value: datetime) -> datetime:
    """Normalize a timestamp to timezone-aware UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
