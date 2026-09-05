"""Backtest value objects and boundary normalization helpers.

This module contains the plain data structures that describe backtest inputs,
outputs, assumptions, and accounting evidence. They are intentionally free of
event-store, broker, filesystem, and runtime orchestration dependencies so they
can be reused by pure calculations and serialization helpers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping


@dataclass(frozen=True)
class FeeAssumptions:
    """Fee model applied by the internal broker during backtests.

    Attributes:
        fixed_per_order: Flat fee applied to each filled order.
        bps: Notional fee in basis points.
        minimum_fee: Minimum fee used when the configured fee model is non-zero.
    """

    fixed_per_order: float = 0.0
    bps: float = 0.0
    minimum_fee: float = 0.0


@dataclass(frozen=True)
class SlippageAssumptions:
    """Price-impact model applied to simulated fills.

    Attributes:
        bps: Basis points added to buy fills and subtracted from sell fills.
            This keeps the model deterministic while making execution worse
            than the raw bar price.
    """

    bps: float = 0.0


@dataclass(frozen=True)
class DataAssumptions:
    """Rules for handling missing or misaligned historical bars.

    Attributes:
        allow_latest_prior_bar: Whether a decision timestamp may use the latest
            earlier bar when the exact timestamp is missing.
        allow_price_carry_forward: Whether portfolio valuation may reuse the
            most recent known price when the current timestamp has no bar.
    """

    allow_latest_prior_bar: bool = True
    allow_price_carry_forward: bool = True


@dataclass(frozen=True)
class BacktestAssumptions:
    """Complete execution model recorded with every backtest result.

    Attributes:
        fill_model: Human-readable label for the simulated fill model.
        latency_ms: Intended broker latency assumption for provenance.
        fees: Fee model passed to the internal paper broker.
        slippage: Slippage model passed to the internal paper broker.
        data: Missing-data and price-carry-forward rules.
    """

    fill_model: str = "full_fill"
    latency_ms: float = 0.0
    fees: FeeAssumptions = field(default_factory=FeeAssumptions)
    slippage: SlippageAssumptions = field(default_factory=SlippageAssumptions)
    data: DataAssumptions = field(default_factory=DataAssumptions)


@dataclass(frozen=True)
class TradeRecord:
    """Executed fill with accounting fields derived from event-store history.

    Each record ties a fill back to the local client order and cycle, preserves
    raw and adjusted prices, and carries fee/slippage/realized-PnL values used
    by performance summaries and CSV exports.
    """

    client_order_id: str
    cycle_id: str | None
    symbol: str
    side: str
    fill_ts: datetime
    fill_qty: float
    raw_fill_price: float | None
    fill_price: float
    fee_amount: float
    slippage_amount: float
    notional: float
    realized_pnl: float | None


@dataclass(frozen=True)
class BacktestSpec:
    """Historical replay window and cadence.

    Attributes:
        start: Inclusive UTC start timestamp for replayed decisions.
        end: Inclusive UTC end timestamp for replayed decisions.
        timeframe: Bar timeframe passed through to historical data loading.
        max_runs: Optional cap used by tests and exploratory runs to stop early.
    """

    start: datetime
    end: datetime
    timeframe: str
    max_runs: int | None = None


@dataclass(frozen=True)
class PositionSummary:
    """Final per-symbol position valuation included in a backtest result.

    The summary combines position quantity/average price from portfolio state
    with the latest known historical price so operators can inspect open risk
    and unrealized PnL at the end of the replay.
    """

    symbol: str
    qty: float
    avg_price: float | None
    last_price: float | None
    last_ts: datetime | None
    market_value: float | None
    unrealized_pnl: float | None


@dataclass(frozen=True)
class PortfolioSummary:
    """Final portfolio rollup derived from positions and latest prices.

    Attributes:
        position_count: Number of open position records at the summary point.
        long_positions: Count of positive-quantity positions.
        short_positions: Count of negative-quantity positions.
        net_qty: Signed sum of quantities.
        gross_qty: Absolute sum of quantities.
        net_notional: Signed market value when prices are available.
        gross_notional: Absolute market value when prices are available.
        positions: Per-symbol position summaries sorted by symbol.
    """

    position_count: int
    long_positions: int
    short_positions: int
    net_qty: float
    gross_qty: float
    net_notional: float | None
    gross_notional: float | None
    positions: tuple[PositionSummary, ...]


@dataclass(frozen=True)
class PerformanceSummary:
    """Risk, return, exposure, and trade statistics for one equity curve.

    The fields are nullable because short or degenerate backtests may not have
    enough observations to calculate annualized or distribution-based metrics.
    """

    start_equity: float | None
    end_equity: float | None
    total_return: float | None
    cagr: float | None
    volatility: float | None
    sharpe: float | None
    sortino: float | None
    max_drawdown: float | None
    max_drawdown_duration: int | None
    calmar: float | None
    ulcer_index: float | None
    avg_net_exposure: float | None
    avg_gross_exposure: float | None
    avg_invested_pct: float | None
    trade_count: int | None
    hit_rate: float | None
    profit_factor: float | None
    expectancy: float | None
    avg_win: float | None
    avg_loss: float | None
    turnover: float | None


@dataclass(frozen=True)
class EquityPoint:
    """Timestamped equity value for strategy or benchmark performance curves.

    Attributes:
        ts: Replay timestamp represented by the equity point.
        equity: Portfolio or benchmark value at that timestamp.
    """

    ts: datetime
    equity: float


@dataclass(frozen=True)
class BacktestResult:
    """Serializable outcome of a completed historical replay.

    The result combines run counts, final positions, execution assumptions,
    trade accounting, strategy/benchmark equity curves, relative metrics, and
    optional research provenance. It is intentionally plain data so it can be
    converted to JSON or CSV without reaching back into the event store.
    """

    total_runs: int
    success_runs: int
    failed_runs: int
    started_at: datetime
    finished_at: datetime
    duration_seconds: float
    asset_class: str
    symbols: tuple[str, ...]
    timeframe: str
    position_count: int
    long_positions: int
    short_positions: int
    net_qty: float
    gross_qty: float
    net_notional: float | None
    gross_notional: float | None
    positions: tuple[PositionSummary, ...]
    assumptions: BacktestAssumptions
    warnings: tuple[str, ...]
    trades: tuple[TradeRecord, ...]
    realized_pnl: float | None
    total_fees: float
    total_slippage: float
    strategy_performance: PerformanceSummary
    benchmark_performance: PerformanceSummary
    tracking_error: float | None
    information_ratio: float | None
    alpha: float | None
    beta: float | None
    equity_curve: tuple[EquityPoint, ...]
    benchmark_curve: tuple[EquityPoint, ...]
    run_id: str | None = None
    experiment_id: str | None = None
    experiment_run_id: str | None = None
    provenance: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class TradeStats:
    """Aggregate trade accounting calculated from normalized fills."""

    trade_count: int
    hit_rate: float | None
    profit_factor: float | None
    expectancy: float | None
    avg_win: float | None
    avg_loss: float | None
    turnover: float | None
    realized_pnl: float | None
    trades: tuple[TradeRecord, ...]
    total_fees: float
    total_slippage: float


@dataclass(frozen=True)
class OrderAccountingEvent:
    """Normalized order evidence needed to interpret fill direction and symbol."""

    client_order_id: str
    symbol: str
    side: str
    cycle_id: str | None


@dataclass(frozen=True)
class FillAccountingEvent:
    """Normalized fill evidence used by pure trade-stat accounting."""

    client_order_id: str | None
    fill_ts: datetime
    fill_qty: float
    fill_price: float
    raw_fill_price: float | None
    fee_amount: float
    slippage_amount: float


def build_backtest_assumptions(data: Mapping[str, object] | None = None) -> BacktestAssumptions:
    """Normalize user/config mapping data into typed backtest assumptions.

    Missing sections fall back to deterministic zero-fee, zero-slippage, and
    permissive data-availability defaults. Values are coerced at the boundary so
    the runner and broker can operate on typed dataclasses instead of partially
    trusted dictionaries.
    """
    data = data or {}
    fee_cfg = _mapping_value(data.get("fees"))
    slippage_cfg = _mapping_value(data.get("slippage"))
    data_cfg = _mapping_value(data.get("data"))
    return BacktestAssumptions(
        fill_model=str(data.get("fill_model", "full_fill")),
        latency_ms=_float_value(data.get("latency_ms"), 0.0),
        fees=FeeAssumptions(
            fixed_per_order=_float_value(fee_cfg.get("fixed_per_order"), 0.0),
            bps=_float_value(fee_cfg.get("bps"), 0.0),
            minimum_fee=_float_value(fee_cfg.get("minimum_fee"), 0.0),
        ),
        slippage=SlippageAssumptions(
            bps=_float_value(slippage_cfg.get("bps"), 0.0),
        ),
        data=DataAssumptions(
            allow_latest_prior_bar=_bool_value(data_cfg.get("allow_latest_prior_bar"), True),
            allow_price_carry_forward=_bool_value(data_cfg.get("allow_price_carry_forward"), True),
        ),
    )


def _mapping_value(value: object | None) -> Mapping[str, object]:
    """Return a mapping value or an empty mapping."""
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError("Backtest assumptions sections must be mappings")
    return value


def _float_value(value: object | None, default: float) -> float:
    """Coerce a float config value with a default."""
    if value is None:
        return default
    return float(value)


def _bool_value(value: object | None, default: bool) -> bool:
    """Coerce a bool-like config value with a default."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


__all__ = [
    "BacktestAssumptions",
    "BacktestResult",
    "BacktestSpec",
    "DataAssumptions",
    "EquityPoint",
    "FeeAssumptions",
    "FillAccountingEvent",
    "OrderAccountingEvent",
    "PerformanceSummary",
    "PortfolioSummary",
    "PositionSummary",
    "SlippageAssumptions",
    "TradeRecord",
    "TradeStats",
    "build_backtest_assumptions",
]
