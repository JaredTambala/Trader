"""Pure backtest portfolio parsing, selection, and summary helpers."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime

from ..portfolio import Portfolio, Position
from .models import PortfolioSummary, PositionSummary


@dataclass(frozen=True)
class _PositionSelection:
    """Selected and ignored initial positions for a backtest symbol universe."""

    selected: tuple[Position, ...]
    ignored_symbols: tuple[str, ...]


@dataclass(frozen=True)
class _InitialAvgPriceFill:
    """Initial positions after avg-price filling plus unresolved symbols."""

    positions: tuple[Position, ...]
    missing_price_symbols: tuple[str, ...]


def _summarize_portfolio_positions(
    positions: Sequence[Position],
    latest_prices: Mapping[str, tuple[datetime, float]],
) -> PortfolioSummary:
    """Compute final position, notional, and unrealized-PnL summary values."""
    summaries: list[PositionSummary] = []
    net_qty = 0.0
    gross_qty = 0.0
    net_notional = 0.0
    gross_notional = 0.0
    net_notional_set = False
    gross_notional_set = False
    long_positions = 0
    short_positions = 0

    for position in sorted(positions, key=lambda item: item.symbol):
        price_info = latest_prices.get(position.symbol)
        last_ts = price_info[0] if price_info else None
        last_price = price_info[1] if price_info else None
        market_value = last_price * position.qty if last_price is not None else None

        unrealized_pnl = None
        if last_price is not None and position.avg_price is not None:
            if position.qty >= 0:
                unrealized_pnl = (last_price - position.avg_price) * position.qty
            else:
                unrealized_pnl = (position.avg_price - last_price) * abs(position.qty)

        summaries.append(
            PositionSummary(
                symbol=position.symbol,
                qty=position.qty,
                avg_price=position.avg_price,
                last_price=last_price,
                last_ts=last_ts,
                market_value=market_value,
                unrealized_pnl=unrealized_pnl,
            )
        )

        net_qty += position.qty
        gross_qty += abs(position.qty)
        if position.qty > 0:
            long_positions += 1
        elif position.qty < 0:
            short_positions += 1

        price_basis = last_price if last_price is not None else position.avg_price
        if price_basis is not None:
            net_notional += position.qty * price_basis
            gross_notional += abs(position.qty * price_basis)
            net_notional_set = True
            gross_notional_set = True

    return PortfolioSummary(
        position_count=len(positions),
        long_positions=long_positions,
        short_positions=short_positions,
        net_qty=net_qty,
        gross_qty=gross_qty,
        net_notional=net_notional if net_notional_set else None,
        gross_notional=gross_notional if gross_notional_set else None,
        positions=tuple(summaries),
    )


def _build_initial_portfolio(positions: Sequence[Position], *, cash_balance: float) -> Portfolio:
    """Create a portfolio seeded with supplied positions and cash balance."""
    portfolio = Portfolio.empty(cash_balance=cash_balance)
    for position in positions:
        portfolio.positions[position.symbol] = position
    return portfolio


def _parse_initial_positions(value: object | None) -> Sequence[Position] | None:
    """Parse optional initial backtest positions from config mappings.

    Each entry must include a symbol and quantity. Average price is optional and
    may later be filled from first available market data.
    """
    if value is None:
        return None
    if not isinstance(value, (list, tuple)):
        raise ValueError("backtest.initial_positions must be a list")
    return [_parse_initial_position(item) for item in value]


def _parse_initial_position(item: object) -> Position:
    """Parse one initial-position config entry into a typed position."""
    if not isinstance(item, Mapping):
        raise ValueError("backtest.initial_positions entries must be mappings")
    symbol = str(item.get("symbol", "")).strip().upper()
    if not symbol:
        raise ValueError("backtest.initial_positions requires symbol")
    qty_raw = item.get("qty")
    if qty_raw is None:
        raise ValueError("backtest.initial_positions requires qty")
    try:
        qty = float(qty_raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid qty for initial position: {item}") from exc
    avg_price = item.get("avg_price")
    if avg_price is None:
        avg_value = None
    else:
        try:
            avg_value = float(avg_price)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid avg_price for initial position: {item}") from exc
    return Position(symbol=symbol, qty=qty, avg_price=avg_value)


def _parse_initial_cash(value: object | None) -> float:
    """Parse optional initial cash, treating missing/empty as zero."""
    if value is None or value == "":
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid initial_cash value: {value}") from exc


def _select_positions_for_symbols(positions: Sequence[Position], symbols: set[str]) -> _PositionSelection:
    """Select initial positions that belong to the configured symbol universe."""
    if not positions or not symbols:
        return _PositionSelection(selected=tuple(positions), ignored_symbols=tuple())
    selected: list[Position] = []
    ignored_symbols: list[str] = []
    for position in positions:
        if position.symbol in symbols:
            selected.append(position)
        else:
            ignored_symbols.append(position.symbol)
    return _PositionSelection(selected=tuple(selected), ignored_symbols=tuple(ignored_symbols))


def _fill_missing_initial_avg_prices(
    positions: Sequence[Position],
    first_prices: Mapping[str, float],
) -> _InitialAvgPriceFill:
    """Fill missing initial avg prices from explicit first-price evidence."""
    filled: list[Position] = []
    missing_price_symbols: list[str] = []
    for position in positions:
        avg_price = position.avg_price
        if avg_price is None:
            avg_price = first_prices.get(position.symbol)
            if avg_price is None:
                missing_price_symbols.append(position.symbol)
        filled.append(Position(symbol=position.symbol, qty=position.qty, avg_price=avg_price))
    return _InitialAvgPriceFill(
        positions=tuple(filled),
        missing_price_symbols=tuple(missing_price_symbols),
    )


__all__ = [
    "_InitialAvgPriceFill",
    "_PositionSelection",
    "_build_initial_portfolio",
    "_fill_missing_initial_avg_prices",
    "_parse_initial_cash",
    "_parse_initial_position",
    "_parse_initial_positions",
    "_select_positions_for_symbols",
    "_summarize_portfolio_positions",
]
