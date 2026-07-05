"""Pure backtest performance, benchmark, and trade-accounting helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import math
from typing import Mapping, Sequence

from ..portfolio import Portfolio, Position
from ..signals import Bar
from ..timeframes import normalize_timeframe
from .models import (
    EquityPoint,
    FillAccountingEvent as _FillAccountingEvent,
    OrderAccountingEvent as _OrderAccountingEvent,
    PerformanceSummary,
    TradeRecord,
    TradeStats as _TradeStats,
)


@dataclass(frozen=True)
class _Holdings:
    cash_balance: float
    positions: Mapping[str, float]


@dataclass(frozen=True)
class _PortfolioValuation:
    """Portfolio equity and exposure at one replay timestamp."""

    equity: float
    net_notional: float
    gross_notional: float
    invested_pct: float | None


@dataclass(frozen=True)
class _RelativeMetrics:
    """Benchmark-relative return statistics for a backtest equity curve."""

    tracking_error: float | None
    information_ratio: float | None
    alpha: float | None
    beta: float | None


@dataclass(frozen=True)
class _ReturnPerformanceMetrics:
    """Risk and return metrics derived only from an equity curve."""

    start_equity: float
    end_equity: float
    total_return: float | None
    cagr: float | None
    volatility: float | None
    sharpe: float | None
    sortino: float | None
    max_drawdown: float | None
    max_drawdown_duration: int | None
    calmar: float | None
    ulcer_index: float | None


@dataclass(frozen=True)
class _ExposureSummary:
    """Average exposure metrics derived from timestamp-level samples."""

    avg_net_exposure: float | None
    avg_gross_exposure: float | None
    avg_invested_pct: float | None


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


@dataclass(frozen=True)
class _DrawdownSummary:
    max_drawdown: float | None
    max_drawdown_duration: int | None
    ulcer_index: float | None


def _empty_performance_summary() -> PerformanceSummary:
    """Return an empty performance summary for degenerate runs."""
    return PerformanceSummary(
        start_equity=None,
        end_equity=None,
        total_return=None,
        cagr=None,
        volatility=None,
        sharpe=None,
        sortino=None,
        max_drawdown=None,
        max_drawdown_duration=None,
        calmar=None,
        ulcer_index=None,
        avg_net_exposure=None,
        avg_gross_exposure=None,
        avg_invested_pct=None,
        trade_count=None,
        hit_rate=None,
        profit_factor=None,
        expectancy=None,
        avg_win=None,
        avg_loss=None,
        turnover=None,
    )


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
    net_notional = 0.0
    gross_notional = 0.0
    for symbol, position in portfolio.positions.items():
        price = prices.get(symbol)
        if price is None:
            continue
        notional = position.qty * price
        net_notional += notional
        gross_notional += abs(notional)
    equity = portfolio.cash_balance + net_notional
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


def _build_performance_summary(
    equity_curve: Sequence[EquityPoint],
    timeframe: str,
    *,
    exposure_samples: Sequence[tuple[float, float, float | None]] | None,
    trade_stats: _TradeStats | None = None,
) -> PerformanceSummary:
    """Compute risk/return/exposure metrics for an equity curve.

    Curves with fewer than two points return an empty summary. Trade statistics
    are merged when available so the result combines time-series performance and
    fill-derived accounting in one object.
    """
    if len(equity_curve) < 2:
        return _empty_performance_summary()
    return_metrics = _summarize_return_performance(
        equity_curve,
        periods_per_year=_annualization_factor(timeframe),
    )
    exposure = _summarize_exposure_samples(exposure_samples or ())
    return PerformanceSummary(
        start_equity=return_metrics.start_equity,
        end_equity=return_metrics.end_equity,
        total_return=return_metrics.total_return,
        cagr=return_metrics.cagr,
        volatility=return_metrics.volatility,
        sharpe=return_metrics.sharpe,
        sortino=return_metrics.sortino,
        max_drawdown=return_metrics.max_drawdown,
        max_drawdown_duration=return_metrics.max_drawdown_duration,
        calmar=return_metrics.calmar,
        ulcer_index=return_metrics.ulcer_index,
        avg_net_exposure=exposure.avg_net_exposure,
        avg_gross_exposure=exposure.avg_gross_exposure,
        avg_invested_pct=exposure.avg_invested_pct,
        trade_count=trade_stats.trade_count if trade_stats else None,
        hit_rate=trade_stats.hit_rate if trade_stats else None,
        profit_factor=trade_stats.profit_factor if trade_stats else None,
        expectancy=trade_stats.expectancy if trade_stats else None,
        avg_win=trade_stats.avg_win if trade_stats else None,
        avg_loss=trade_stats.avg_loss if trade_stats else None,
        turnover=trade_stats.turnover if trade_stats else None,
    )


def _summarize_return_performance(
    equity_curve: Sequence[EquityPoint],
    *,
    periods_per_year: float,
) -> _ReturnPerformanceMetrics:
    """Compute return, volatility, and drawdown metrics from an equity curve."""
    start_equity = equity_curve[0].equity
    end_equity = equity_curve[-1].equity
    returns = _returns_from_curve(equity_curve)
    total_return = None
    if start_equity != 0:
        total_return = (end_equity / start_equity) - 1.0
    cagr = _compute_cagr(start_equity, end_equity, len(returns), periods_per_year)
    volatility = _annualize_volatility(returns, periods_per_year)
    sharpe = _compute_sharpe(returns, periods_per_year)
    sortino = _compute_sortino(returns, periods_per_year)
    drawdown = _compute_drawdowns(equity_curve)
    calmar = None
    if cagr is not None and drawdown.max_drawdown not in {None, 0.0}:
        calmar = cagr / drawdown.max_drawdown
    return _ReturnPerformanceMetrics(
        start_equity=start_equity,
        end_equity=end_equity,
        total_return=total_return,
        cagr=cagr,
        volatility=volatility,
        sharpe=sharpe,
        sortino=sortino,
        max_drawdown=drawdown.max_drawdown,
        max_drawdown_duration=drawdown.max_drawdown_duration,
        calmar=calmar,
        ulcer_index=drawdown.ulcer_index,
    )


def _summarize_exposure_samples(
    exposure_samples: Sequence[tuple[float, float, float | None]],
) -> _ExposureSummary:
    """Average net, gross, and invested exposure samples."""
    if not exposure_samples:
        return _ExposureSummary(
            avg_net_exposure=None,
            avg_gross_exposure=None,
            avg_invested_pct=None,
        )
    sample_count = len(exposure_samples)
    invested_values = [sample[2] for sample in exposure_samples if sample[2] is not None]
    avg_invested = None
    if invested_values:
        avg_invested = sum(invested_values) / len(invested_values)
    return _ExposureSummary(
        avg_net_exposure=sum(sample[0] for sample in exposure_samples) / sample_count,
        avg_gross_exposure=sum(sample[1] for sample in exposure_samples) / sample_count,
        avg_invested_pct=avg_invested,
    )


def _build_relative_metrics(
    *,
    strategy_curve: Sequence[EquityPoint],
    benchmark_curve: Sequence[EquityPoint],
    timeframe: str,
) -> _RelativeMetrics:
    """Compute tracking, information-ratio, alpha, and beta versus benchmark."""
    returns = _returns_from_curve(strategy_curve)
    benchmark_returns = _returns_from_curve(benchmark_curve)
    return _build_relative_metrics_from_returns(
        returns=returns,
        benchmark_returns=benchmark_returns,
        periods_per_year=_annualization_factor(timeframe),
    )


def _build_relative_metrics_from_returns(
    *,
    returns: Sequence[float],
    benchmark_returns: Sequence[float],
    periods_per_year: float,
) -> _RelativeMetrics:
    """Compute benchmark-relative metrics from aligned period return inputs."""
    length = min(len(returns), len(benchmark_returns))
    if length == 0:
        return _RelativeMetrics(None, None, None, None)
    returns = returns[:length]
    benchmark_returns = benchmark_returns[:length]
    excess = [r - b for r, b in zip(returns, benchmark_returns)]
    excess_std = _variance(excess) ** 0.5 if excess else 0.0
    tracking_error = None if excess_std == 0.0 else excess_std * (periods_per_year ** 0.5)
    info_ratio = None
    if excess_std != 0.0:
        info_ratio = _mean(excess) / excess_std * (periods_per_year ** 0.5)
    beta = _compute_beta(returns, benchmark_returns)
    alpha = None
    if beta is not None:
        alpha = _mean(returns) - beta * _mean(benchmark_returns)
        alpha = alpha * periods_per_year
    return _RelativeMetrics(tracking_error, info_ratio, alpha, beta)


def _compute_drawdowns(equity_curve: Sequence[EquityPoint]) -> _DrawdownSummary:
    """Compute drawdown metrics from an equity curve."""
    if not equity_curve:
        return _DrawdownSummary(None, None, None)
    peak = equity_curve[0].equity
    max_drawdown = 0.0
    max_duration = 0
    current_duration = 0
    drawdown_values: list[float] = []
    for point in equity_curve:
        equity = point.equity
        if equity >= peak:
            peak = equity
            current_duration = 0
            drawdown_values.append(0.0)
            continue
        drawdown = (peak - equity) / peak if peak != 0 else 0.0
        drawdown_values.append(drawdown)
        current_duration += 1
        if drawdown > max_drawdown:
            max_drawdown = drawdown
        if current_duration > max_duration:
            max_duration = current_duration
    ulcer_index = None
    if drawdown_values:
        ulcer_index = (_mean([value ** 2 for value in drawdown_values])) ** 0.5
    return _DrawdownSummary(max_drawdown, max_duration, ulcer_index)


def _returns_from_curve(curve: Sequence[EquityPoint]) -> list[float]:
    """Compute period returns from an equity curve."""
    returns: list[float] = []
    for prev, current in zip(curve, curve[1:]):
        if prev.equity == 0:
            continue
        returns.append((current.equity / prev.equity) - 1.0)
    return returns


def _annualization_factor(timeframe: str) -> float:
    """Return the annualization factor for the timeframe."""
    tf = normalize_timeframe(timeframe)
    amount, unit = _parse_timeframe_parts(tf)
    if unit == "month":
        return 12.0 / amount
    if unit == "week":
        return 52.0 / amount
    if unit == "day":
        return 365.0 / amount
    if unit == "hour":
        return (365.0 * 24.0) / amount
    return (365.0 * 24.0 * 60.0) / amount


def _parse_timeframe_parts(timeframe: str) -> tuple[int, str]:
    """Return numeric amount and lowercase unit from a normalized timeframe."""
    tf = normalize_timeframe(timeframe)
    for unit in ("Min", "Hour", "Day", "Week", "Month"):
        if tf.endswith(unit):
            amount = int(tf[: -len(unit)])
            return amount, unit.lower()
    raise ValueError(f"Unsupported timeframe: {timeframe}")


def _mean(values: Sequence[float]) -> float:
    """Compute the arithmetic mean of values."""
    return sum(values) / len(values) if values else 0.0


def _variance(values: Sequence[float]) -> float:
    """Compute the variance of values."""
    if not values:
        return 0.0
    avg = _mean(values)
    return _mean([(value - avg) ** 2 for value in values])


def _annualize_volatility(returns: Sequence[float], periods_per_year: float) -> float | None:
    """Annualize volatility using the timeframe factor."""
    if not returns:
        return None
    return (_variance(returns) ** 0.5) * (periods_per_year ** 0.5)


def _compute_cagr(
    start_equity: float,
    end_equity: float,
    periods: int,
    periods_per_year: float,
) -> float | None:
    """Compute the compound annual growth rate."""
    if start_equity <= 0 or periods <= 0:
        return None
    years = periods / periods_per_year
    if years <= 0:
        return None
    ratio = end_equity / start_equity
    if ratio <= 0:
        return None
    exponent = 1.0 / years
    try:
        return math.exp(math.log(ratio) * exponent) - 1.0
    except OverflowError:
        return float("inf")


def _compute_sharpe(returns: Sequence[float], periods_per_year: float) -> float | None:
    """Compute annualized Sharpe ratio when returns have non-zero variance."""
    if not returns:
        return None
    std = _variance(returns) ** 0.5
    if std == 0.0:
        return None
    return _mean(returns) / std * (periods_per_year ** 0.5)


def _compute_sortino(returns: Sequence[float], periods_per_year: float) -> float | None:
    """Compute annualized Sortino ratio from downside return variance."""
    downside = [value for value in returns if value < 0]
    if not downside:
        return None
    downside_std = _variance(downside) ** 0.5
    if downside_std == 0.0:
        return None
    return _mean(returns) / downside_std * (periods_per_year ** 0.5)


def _compute_beta(returns: Sequence[float], benchmark_returns: Sequence[float]) -> float | None:
    """Compute beta against the benchmark series."""
    if not returns or not benchmark_returns:
        return None
    length = min(len(returns), len(benchmark_returns))
    returns = returns[:length]
    benchmark_returns = benchmark_returns[:length]
    var_bench = _variance(benchmark_returns)
    if var_bench == 0:
        return None
    avg_returns = _mean(returns)
    avg_bench = _mean(benchmark_returns)
    cov = _mean([(r - avg_returns) * (b - avg_bench) for r, b in zip(returns, benchmark_returns)])
    return cov / var_bench


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
