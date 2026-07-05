"""Pure trade accounting helpers for backtest fill evidence.

The functions in this module operate on normalized order/fill events and an
equity curve. They do not query the event store, mutate portfolios, or log, so
they can be tested as deterministic accounting transformations.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping, Sequence

from .models import (
    EquityPoint,
    FillAccountingEvent as _FillAccountingEvent,
    OrderAccountingEvent as _OrderAccountingEvent,
    TradeRecord,
    TradeStats as _TradeStats,
)


@dataclass(frozen=True)
class _RealizedTradeSummary:
    """Win/loss metrics derived from realized trade PnL values."""

    trade_count: int
    hit_rate: float | None
    profit_factor: float | None
    expectancy: float | None
    avg_win: float | None
    avg_loss: float | None
    realized_pnl: float | None


@dataclass(frozen=True)
class _PositionAccountingState:
    """Open position quantity and average effective price during fill accounting."""

    qty: float
    avg_price: float | None


@dataclass(frozen=True)
class _PositionAccountingTransition:
    """Result of applying one fill to one symbol position state."""

    state: _PositionAccountingState | None
    realized_pnl: float | None


def _normalize_order_accounting_events(rows: Sequence[Sequence[object]]) -> tuple[_OrderAccountingEvent, ...]:
    """Normalize raw order-event rows for deterministic trade accounting."""
    events: list[_OrderAccountingEvent] = []
    for client_order_id, symbol, side, cycle_id in rows:
        if client_order_id is None:
            continue
        events.append(
            _OrderAccountingEvent(
                client_order_id=str(client_order_id),
                symbol=str(symbol),
                side=str(side).lower(),
                cycle_id=str(cycle_id) if cycle_id is not None else None,
            )
        )
    return tuple(events)


def _normalize_fill_accounting_events(rows: Sequence[Sequence[object]]) -> tuple[_FillAccountingEvent, ...]:
    """Normalize raw fill-event rows for deterministic trade accounting."""
    events: list[_FillAccountingEvent] = []
    for client_order_id, fill_ts, fill_qty, fill_price, raw_fill_price, fee_amount, slippage_amount in rows:
        events.append(
            _FillAccountingEvent(
                client_order_id=str(client_order_id) if client_order_id is not None else None,
                fill_ts=_normalize_timestamp(fill_ts),  # type: ignore[arg-type]
                fill_qty=float(fill_qty or 0.0),
                fill_price=float(fill_price or 0.0),
                raw_fill_price=float(raw_fill_price) if raw_fill_price is not None else None,
                fee_amount=float(fee_amount or 0.0),
                slippage_amount=float(slippage_amount or 0.0),
            )
        )
    return tuple(events)


def _empty_trade_stats() -> _TradeStats:
    """Return a zero-valued trade-stat summary for runs without valid fills."""
    return _TradeStats(
        trade_count=0,
        hit_rate=None,
        profit_factor=None,
        expectancy=None,
        avg_win=None,
        avg_loss=None,
        turnover=None,
        realized_pnl=None,
        trades=tuple(),
        total_fees=0.0,
        total_slippage=0.0,
    )


def _compute_trade_stats_from_events(
    *,
    order_events: Sequence[_OrderAccountingEvent],
    fill_events: Sequence[_FillAccountingEvent],
    equity_curve: Sequence[EquityPoint],
) -> _TradeStats:
    """Compute trade-level statistics from normalized order and fill events."""
    if not fill_events:
        return _empty_trade_stats()

    order_lookup: dict[str, _OrderAccountingEvent] = {}
    for order_event in order_events:
        if order_event.client_order_id not in order_lookup:
            order_lookup[order_event.client_order_id] = order_event

    if not order_lookup:
        return _empty_trade_stats()

    return _compute_trade_accounting(
        order_lookup=order_lookup,
        fill_events=fill_events,
        equity_curve=equity_curve,
    )


def _compute_trade_accounting(
    *,
    order_lookup: Mapping[str, _OrderAccountingEvent],
    fill_events: Sequence[_FillAccountingEvent],
    equity_curve: Sequence[EquityPoint],
) -> _TradeStats:
    """Apply deterministic position accounting over normalized fills."""
    if not fill_events:
        return _empty_trade_stats()

    positions: dict[str, _PositionAccountingState] = {}
    trades: list[TradeRecord] = []
    realized_pnls: list[float] = []
    traded_notional = 0.0
    total_fees = 0.0
    total_slippage = 0.0

    for fill_event in fill_events:
        if fill_event.client_order_id is None:
            continue
        order = order_lookup.get(fill_event.client_order_id)
        if order is None:
            continue
        symbol = order.symbol
        side = order.side
        cycle_id = order.cycle_id
        qty = fill_event.fill_qty
        price = fill_event.fill_price
        fee = fill_event.fee_amount
        slippage = fill_event.slippage_amount
        if qty <= 0 or price <= 0:
            continue
        total_fees += fee
        total_slippage += slippage
        notional = abs(qty * price)
        traded_notional += notional
        fee_per_unit = fee / qty if qty else 0.0
        effective_unit_price = price + fee_per_unit if side == "buy" else price - fee_per_unit
        transition = _apply_fill_to_position_state(
            positions.get(symbol),
            side=side,
            qty=qty,
            effective_unit_price=effective_unit_price,
        )
        if transition.state is None:
            positions.pop(symbol, None)
        else:
            positions[symbol] = transition.state
        if transition.realized_pnl is not None:
            realized_pnls.append(transition.realized_pnl)

        trades.append(
            TradeRecord(
                client_order_id=fill_event.client_order_id,
                cycle_id=cycle_id,
                symbol=symbol,
                side=side,
                fill_ts=fill_event.fill_ts,
                fill_qty=qty,
                raw_fill_price=fill_event.raw_fill_price,
                fill_price=price,
                fee_amount=fee,
                slippage_amount=slippage,
                notional=notional,
                realized_pnl=transition.realized_pnl,
            )
        )

    realized_summary = _summarize_realized_trade_pnls(realized_pnls)

    turnover = _compute_turnover(
        traded_notional=traded_notional,
        equity_curve=equity_curve,
    )

    return _TradeStats(
        trade_count=realized_summary.trade_count,
        hit_rate=realized_summary.hit_rate,
        profit_factor=realized_summary.profit_factor,
        expectancy=realized_summary.expectancy,
        avg_win=realized_summary.avg_win,
        avg_loss=realized_summary.avg_loss,
        turnover=turnover,
        realized_pnl=realized_summary.realized_pnl,
        trades=tuple(trades),
        total_fees=total_fees,
        total_slippage=total_slippage,
    )


def _compute_turnover(*, traded_notional: float, equity_curve: Sequence[EquityPoint]) -> float | None:
    """Compute traded notional divided by average equity when defined."""
    avg_equity = _mean([point.equity for point in equity_curve]) if equity_curve else 0.0
    if not avg_equity:
        return None
    return traded_notional / avg_equity


def _apply_fill_to_position_state(
    current: _PositionAccountingState | None,
    *,
    side: str,
    qty: float,
    effective_unit_price: float,
) -> _PositionAccountingTransition:
    """Return the next open position state and any realized PnL for one fill."""
    sign = 1.0 if side == "buy" else -1.0
    delta = sign * qty
    current_qty = current.qty if current is not None else 0.0
    avg_price = current.avg_price if current is not None else None

    if current_qty == 0 or avg_price is None:
        return _open_position_from_delta(
            qty=delta,
            avg_price=effective_unit_price,
            realized_pnl=None,
        )

    if current_qty > 0 and delta < 0:
        close_qty = min(current_qty, qty)
        realized_pnl = (effective_unit_price - avg_price) * close_qty
        remaining = current_qty - close_qty
        if qty > close_qty:
            return _PositionAccountingTransition(
                state=_PositionAccountingState(
                    qty=-(qty - close_qty),
                    avg_price=effective_unit_price,
                ),
                realized_pnl=realized_pnl,
            )
        return _open_position_from_delta(
            qty=remaining,
            avg_price=avg_price,
            realized_pnl=realized_pnl,
        )

    if current_qty < 0 and delta > 0:
        close_qty = min(abs(current_qty), qty)
        realized_pnl = (avg_price - effective_unit_price) * close_qty
        remaining = abs(current_qty) - close_qty
        if qty > close_qty:
            return _PositionAccountingTransition(
                state=_PositionAccountingState(
                    qty=qty - close_qty,
                    avg_price=effective_unit_price,
                ),
                realized_pnl=realized_pnl,
            )
        return _open_position_from_delta(
            qty=-remaining,
            avg_price=avg_price,
            realized_pnl=realized_pnl,
        )

    new_qty = current_qty + delta
    avg_price_new = ((current_qty * avg_price) + (delta * effective_unit_price)) / new_qty
    return _open_position_from_delta(
        qty=new_qty,
        avg_price=avg_price_new,
        realized_pnl=None,
    )


def _open_position_from_delta(
    *,
    qty: float,
    avg_price: float,
    realized_pnl: float | None,
) -> _PositionAccountingTransition:
    """Represent a remaining position, treating near-zero quantity as closed."""
    if abs(qty) < 1e-12:
        return _PositionAccountingTransition(state=None, realized_pnl=realized_pnl)
    return _PositionAccountingTransition(
        state=_PositionAccountingState(qty=qty, avg_price=avg_price),
        realized_pnl=realized_pnl,
    )


def _summarize_realized_trade_pnls(realized_pnls: Sequence[float]) -> _RealizedTradeSummary:
    """Compute win/loss statistics from realized PnL values."""
    trade_count = len(realized_pnls)
    if trade_count == 0:
        return _RealizedTradeSummary(
            trade_count=0,
            hit_rate=None,
            profit_factor=None,
            expectancy=None,
            avg_win=None,
            avg_loss=None,
            realized_pnl=None,
        )

    wins = [pnl for pnl in realized_pnls if pnl > 0]
    losses = [pnl for pnl in realized_pnls if pnl < 0]
    hit_rate = len(wins) / trade_count
    avg_win = _mean(wins) if wins else None
    avg_loss = _mean(losses) if losses else None
    gross_loss = abs(sum(losses)) if losses else 0.0
    profit_factor = None
    if gross_loss > 0:
        profit_factor = sum(wins) / gross_loss if wins else 0.0
    win_rate = hit_rate or 0.0
    loss_rate = 1.0 - win_rate
    expectancy = (win_rate * (avg_win or 0.0)) + (loss_rate * (avg_loss or 0.0))
    return _RealizedTradeSummary(
        trade_count=trade_count,
        hit_rate=hit_rate,
        profit_factor=profit_factor,
        expectancy=expectancy,
        avg_win=avg_win,
        avg_loss=avg_loss,
        realized_pnl=sum(realized_pnls),
    )


def _mean(values: Sequence[float]) -> float:
    """Compute the arithmetic mean of values."""
    return sum(values) / len(values) if values else 0.0


def _normalize_timestamp(value: datetime) -> datetime:
    """Normalize a timestamp to timezone-aware UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
