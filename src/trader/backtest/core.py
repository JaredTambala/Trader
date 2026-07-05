"""Backtest execution, accounting, export, and persistence helpers.

The module replays historical bars through the same `run_cycle` path used by
live trading, but supplies deterministic market data, an internal paper broker,
and frozen execution assumptions so research runs can be reproduced and audited.
"""

from __future__ import annotations

import argparse
from bisect import bisect_left
from contextlib import contextmanager
import csv
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
import json
import logging
import math
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, Sequence

from ..broker import Broker, InternalPaperBroker
from ..config import Config
from ..cycle import run_cycle
from ..event_store import EventStore, build_event_store
from ..identifiers import deterministic_run_session_id
from ..market_data import CryptoBarEvent, MarketDataEvent, MarketDataSource, StockBarEvent
from ..portfolio import Portfolio, PortfolioSnapshot, Position
from ..signals import Bar
from ..strategies import Strategy
from ..risk import RiskManager
from ..strategy_metadata import resolve_strategy_id
from ..timeframes import normalize_timeframe


logger = logging.getLogger(__name__)


_EQUITY_CURVE_CSV_FIELDS = ("ts", "strategy_equity", "benchmark_equity")
_TRADES_CSV_FIELDS = (
    "client_order_id",
    "cycle_id",
    "symbol",
    "side",
    "fill_ts",
    "fill_qty",
    "raw_fill_price",
    "fill_price",
    "fee_amount",
    "slippage_amount",
    "notional",
    "realized_pnl",
)


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
    strategy_performance: "PerformanceSummary"
    benchmark_performance: "PerformanceSummary"
    tracking_error: float | None
    information_ratio: float | None
    alpha: float | None
    beta: float | None
    equity_curve: tuple["EquityPoint", ...]
    benchmark_curve: tuple["EquityPoint", ...]
    run_id: str | None = None
    experiment_id: str | None = None
    experiment_run_id: str | None = None
    provenance: Mapping[str, Any] | None = None


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
class _TradeStats:
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
class _OrderAccountingEvent:
    """Normalized order evidence needed to interpret fill direction and symbol."""

    client_order_id: str
    symbol: str
    side: str
    cycle_id: str | None


@dataclass(frozen=True)
class _FillAccountingEvent:
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


def _build_empty_backtest_result(
    *,
    asset_class: str,
    symbols: Sequence[str],
    timeframe: str,
    assumptions: BacktestAssumptions,
    run_id: str,
    timestamp: datetime,
    warning: str,
) -> BacktestResult:
    """Build a zero-run backtest result from explicit shell-provided values."""
    empty_summary = _empty_performance_summary()
    return BacktestResult(
        total_runs=0,
        success_runs=0,
        failed_runs=0,
        started_at=timestamp,
        finished_at=timestamp,
        duration_seconds=0.0,
        asset_class=asset_class,
        symbols=tuple(symbols),
        timeframe=timeframe,
        position_count=0,
        long_positions=0,
        short_positions=0,
        net_qty=0.0,
        gross_qty=0.0,
        net_notional=None,
        gross_notional=None,
        positions=tuple(),
        assumptions=assumptions,
        warnings=(warning,),
        trades=tuple(),
        realized_pnl=None,
        total_fees=0.0,
        total_slippage=0.0,
        strategy_performance=empty_summary,
        benchmark_performance=empty_summary,
        tracking_error=None,
        information_ratio=None,
        alpha=None,
        beta=None,
        equity_curve=tuple(),
        benchmark_curve=tuple(),
        run_id=run_id,
    )


@dataclass(frozen=True)
class _BacktestBarSelection:
    """Decision for serving one symbol at one backtest timestamp."""

    bar: Bar | None
    warning: str | None
    warning_kind: str | None
    latest_ts: datetime | None = None


class BacktestMarketDataSource(MarketDataSource):
    """Market data source that serves historical bars at a controlled timestamp.

    The runner calls `set_as_of()` before each cycle. Fetching then returns one
    bar per configured symbol for that decision timestamp, optionally falling
    back to the latest earlier bar and recording a warning when exact alignment
    is unavailable.
    """

    def __init__(
        self,
        *,
        bars_by_symbol: Mapping[str, Sequence[Bar]],
        asset_class: str,
        timeframe: str,
        source: str = "backtest",
        symbols: Sequence[str] | None = None,
        allow_latest_prior_bar: bool = True,
        warnings: list[str] | None = None,
    ) -> None:
        """Prepare symbol-indexed bars for deterministic timestamp lookups.

        Args:
            bars_by_symbol: Historical bars keyed by canonical symbol.
            asset_class: Asset class used to choose stock versus crypto events.
            timeframe: Timeframe attached to generated market-data events.
            source: Source label persisted with generated events.
            symbols: Optional ordered universe; missing symbols are represented
                by empty bar lists.
            allow_latest_prior_bar: Whether fetch may fall back to older bars.
            warnings: Mutable warning list shared with the runner result.
        """
        if symbols is not None:
            bars_by_symbol = {symbol: bars_by_symbol.get(symbol, []) for symbol in symbols}
        self._bars_by_symbol = {symbol: list(bars) for symbol, bars in bars_by_symbol.items()}
        self._timestamps_by_symbol = {
            symbol: [_normalize_timestamp(bar.ts) for bar in bars]
            for symbol, bars in bars_by_symbol.items()
        }
        self._asset_class = asset_class.lower()
        self._timeframe = timeframe
        self._source = source
        self._as_of_ts: datetime | None = None
        self._allow_latest_prior_bar = allow_latest_prior_bar
        self._warnings = warnings if warnings is not None else []

    def set_as_of(self, as_of_ts: datetime) -> None:
        """Set the normalized decision timestamp used by subsequent `fetch()` calls.

        Backtest cycles call this before ingestion so the market-data source emits
        bars for the current simulated decision time, or applies the configured
        latest-prior fallback when exact bars are unavailable.
        """
        self._as_of_ts = _normalize_timestamp(as_of_ts)

    def fetch(self) -> Sequence[MarketDataEvent]:
        """Return historical market-data events for the current decision time.

        Returns:
            Stock or crypto bar events built from the exact timestamp when
            available. If configured, the latest earlier bar is used with a
            warning; otherwise symbols with missing exact bars are skipped.
        """
        if self._as_of_ts is None:
            return []
        events: list[MarketDataEvent] = []
        for symbol, bars in self._bars_by_symbol.items():
            timestamps = self._timestamps_by_symbol.get(symbol, [])
            selection = _select_backtest_bar(
                symbol=symbol,
                bars=bars,
                timestamps=timestamps,
                target=self._as_of_ts,
                allow_latest_prior_bar=self._allow_latest_prior_bar,
            )
            if selection.warning:
                self._log_bar_selection_warning(symbol, selection)
                self._append_warning(selection.warning)
            if selection.bar is None:
                continue
            events.append(
                _build_market_event(
                    asset_class=self._asset_class,
                    symbol=symbol,
                    timeframe=self._timeframe,
                    bar=selection.bar,
                    source=self._source,
                    ingested_at=self._as_of_ts,
                )
            )
        return events

    def _append_warning(self, message: str) -> None:
        """Add a warning once while preserving insertion order."""
        if message not in self._warnings:
            self._warnings.append(message)

    def _log_bar_selection_warning(self, symbol: str, selection: _BacktestBarSelection) -> None:
        """Log a market-data alignment warning selected by the pure lookup helper."""
        if self._as_of_ts is None:
            return
        if selection.warning_kind == "missing_exact":
            logger.warning(
                "Backtest exact-bar requirement failed symbol=%s decision_ts=%s; skipping",
                symbol,
                self._as_of_ts.isoformat(),
            )
            return
        if selection.warning_kind == "no_prior":
            logger.warning(
                "Backtest price misalignment symbol=%s decision_ts=%s latest_ts=<none>; skipping",
                symbol,
                self._as_of_ts.isoformat(),
            )
            return
        if selection.warning_kind == "latest_prior":
            logger.warning(
                "Backtest price misalignment symbol=%s decision_ts=%s latest_ts=%s; using latest bar",
                symbol,
                self._as_of_ts.isoformat(),
                selection.latest_ts.isoformat() if selection.latest_ts else "<none>",
            )


def _select_backtest_bar(
    *,
    symbol: str,
    bars: Sequence[Bar],
    timestamps: Sequence[datetime],
    target: datetime,
    allow_latest_prior_bar: bool,
) -> _BacktestBarSelection:
    """Select the bar to serve for one symbol at one decision timestamp."""
    target_ts = _normalize_timestamp(target)
    if not timestamps:
        return _BacktestBarSelection(bar=None, warning=None, warning_kind=None)
    idx = bisect_left(timestamps, target_ts)
    if idx < len(timestamps) and timestamps[idx] == target_ts:
        return _BacktestBarSelection(bar=bars[idx], warning=None, warning_kind=None)
    if not allow_latest_prior_bar:
        return _BacktestBarSelection(
            bar=None,
            warning=f"Missing exact bar for {symbol} at {target_ts.isoformat()}; skipped symbol.",
            warning_kind="missing_exact",
        )
    latest_idx = idx - 1
    if latest_idx < 0:
        return _BacktestBarSelection(
            bar=None,
            warning=f"No prior bar available for {symbol} at {target_ts.isoformat()}; skipped symbol.",
            warning_kind="no_prior",
        )
    latest_ts = timestamps[latest_idx]
    return _BacktestBarSelection(
        bar=bars[latest_idx],
        warning=f"Used latest prior bar for {symbol} at {target_ts.isoformat()} from {latest_ts.isoformat()}.",
        warning_kind="latest_prior",
        latest_ts=latest_ts,
    )


class BacktestRunner:
    """Replay historical bars through the production cycle orchestration.

    The runner loads bars, seeds initial portfolio state, creates an internal
    broker from assumptions, invokes `run_cycle` for each replay timestamp, and
    aggregates persisted events into performance, trade, and portfolio summaries.
    Strategy and risk dependencies are injected so backtests exercise the same
    contracts as live trading without constructing hidden defaults.
    """

    def __init__(
        self,
        config: Config,
        spec: BacktestSpec,
        *,
        strategy: Strategy,
        risk_manager: RiskManager,
        symbols: Sequence[str] | None = None,
        asset_class: str | None = None,
        event_store: EventStore | None = None,
        initial_positions: Sequence[Position] | None = None,
        initial_cash: float | None = None,
        config_snapshot: Mapping[str, object] | None = None,
        assumptions: BacktestAssumptions | None = None,
        run_id: str | None = None,
        started_at: datetime | None = None,
    ) -> None:
        """Configure a reproducible backtest run.

        Args:
            config: Runtime config used as the base for event store, symbols,
                asset class, and timeframe settings.
            spec: Replay window and timeframe.
            strategy: Injected strategy instance to execute.
            risk_manager: Injected risk manager or pipeline for candidate orders.
            symbols: Optional symbol override; defaults to config symbols.
            asset_class: Optional asset-class override.
            event_store: Optional store, typically a test or research store.
            initial_positions: Positions to seed before the first cycle.
            initial_cash: Cash balance to seed before the first cycle.
            config_snapshot: Optional config payload recorded with run metadata.
            assumptions: Execution/data assumptions for broker and pricing.
            run_id: Optional deterministic run ID supplied by a caller.
            started_at: Optional start timestamp for reproducible metadata.

        Raises:
            ValueError: If strategy or risk manager dependencies are missing.
        """
        self._spec = spec
        raw_symbols = list(symbols) if symbols else list(config.market_data_symbols)
        self._symbols = [symbol.strip().upper() for symbol in raw_symbols if str(symbol).strip()]
        self._asset_class = (asset_class or config.market_data_asset_class).lower()
        self._event_store = event_store or build_event_store(config)
        self._owns_event_store = event_store is None
        self._initial_positions = list(initial_positions) if initial_positions else []
        self._initial_cash = float(initial_cash) if initial_cash is not None else 0.0
        self._config_snapshot = config_snapshot
        self._assumptions = assumptions or BacktestAssumptions()
        self._run_id = run_id
        self._started_at = started_at
        if strategy is None:
            raise ValueError("BacktestRunner requires an injected strategy instance.")
        if risk_manager is None:
            raise ValueError("BacktestRunner requires an injected risk manager instance.")
        self._strategy = strategy
        self._risk_manager = risk_manager
        self._config = _build_backtest_runtime_config(
            config,
            symbols=self._symbols,
            asset_class=self._asset_class,
            timeframe=spec.timeframe,
        )

    def run(
        self,
        *,
        log_cycle_details: bool = False,
        progress_callback: Callable[[int, int, datetime | None], None] | None = None,
    ) -> BacktestResult:
        """Execute the replay and aggregate persisted accounting evidence.

        The method loads historical bars, derives replay timestamps, records a
        run session, seeds initial portfolio state, and executes one production
        cycle per timestamp. It then reads order/fill/portfolio events back from
        the event store to compute trade statistics, equity curves, benchmark
        comparisons, warnings, and final position summaries.

        Args:
            log_cycle_details: Whether to emit per-cycle detail logs.
            progress_callback: Optional callback receiving completed count, total
                count, and current replay timestamp.

        Returns:
            Serializable `BacktestResult` containing performance, accounting,
            provenance, warnings, and final portfolio state.
        """
        warnings: list[str] = []
        if not self._symbols:
            logger.warning("No symbols configured for backtest")
            started_at = self._started_at or datetime.now(timezone.utc)
            run_id = self._run_id or deterministic_run_session_id("backtest", started_at)
            now = datetime.now(timezone.utc)
            return _build_empty_backtest_result(
                asset_class=self._asset_class,
                symbols=self._symbols,
                timeframe=self._spec.timeframe,
                assumptions=self._assumptions,
                run_id=run_id,
                timestamp=now,
                warning="No symbols configured for backtest.",
            )
        if self._spec.start > self._spec.end:
            raise ValueError("Backtest start must be <= end")

        lookback = _signal_lookback_window(self._strategy)
        bars_by_symbol = _load_bars(
            self._event_store,
            self._asset_class,
            self._symbols,
            self._spec.timeframe,
            self._spec.start,
            self._spec.end,
            lookback_bars=lookback,
        )
        symbol_schedule = _build_symbol_schedule(bars_by_symbol, self._spec.start, self._spec.end)
        timestamps = sorted(symbol_schedule.keys())
        if not timestamps:
            logger.warning("No bars found for backtest window")
            started_at = self._started_at or datetime.now(timezone.utc)
            run_id = self._run_id or deterministic_run_session_id("backtest", started_at)
            now = datetime.now(timezone.utc)
            return _build_empty_backtest_result(
                asset_class=self._asset_class,
                symbols=self._symbols,
                timeframe=self._spec.timeframe,
                assumptions=self._assumptions,
                run_id=run_id,
                timestamp=now,
                warning="No bars found for backtest window.",
            )

        count = 0
        limit = self._spec.max_runs
        failed = 0
        equity_curve: list[EquityPoint] = []
        benchmark_curve: list[EquityPoint] = []
        exposure_samples: list[tuple[float, float, float | None]] = []
        price_state = _PriceState(
            bars_by_symbol,
            allow_price_carry_forward=self._assumptions.data.allow_price_carry_forward,
        )
        logger.info(
            "Backtest start asset_class=%s symbols=%s timeframe=%s start=%s end=%s runs=%s",
            self._asset_class,
            ",".join(self._symbols),
            self._spec.timeframe,
            self._spec.start.isoformat(),
            self._spec.end.isoformat(),
            limit or len(timestamps),
        )
        logger.info(
            "Backtest assumptions fill_model=%s latency_ms=%.2f fee_fixed=%s fee_bps=%s fee_min=%s slippage_bps=%s allow_latest_prior_bar=%s allow_price_carry_forward=%s",
            self._assumptions.fill_model,
            self._assumptions.latency_ms,
            self._assumptions.fees.fixed_per_order,
            self._assumptions.fees.bps,
            self._assumptions.fees.minimum_fee,
            self._assumptions.slippage.bps,
            self._assumptions.data.allow_latest_prior_bar,
            self._assumptions.data.allow_price_carry_forward,
        )
        started_at = self._started_at or datetime.now(timezone.utc)
        run_id = self._run_id or deterministic_run_session_id("backtest", started_at)
        strategy = self._strategy
        risk_manager = self._risk_manager
        broker = _build_backtest_broker(self._assumptions)
        strategy_id = resolve_strategy_id(strategy, self._config.strategy_id)
        run_status = "success"
        run_error: str | None = None
        self._event_store.record_run_session_start(
            run_id=run_id,
            run_type="backtest",
            started_at=started_at,
            strategy_id=strategy_id,
            config_snapshot=self._config_snapshot,
            mode=self._config.mode,
            symbols=self._symbols,
            timeframe=self._spec.timeframe,
            start_ts=self._spec.start,
            end_ts=self._spec.end,
        )
        seeded_positions = _filter_positions(self._initial_positions, set(self._symbols))
        seeded_positions = _fill_initial_avg_prices(
            self._event_store,
            self._asset_class,
            self._spec.timeframe,
            self._spec.start,
            seeded_positions,
            bars_by_symbol=bars_by_symbol,
        )
        benchmark_holdings = _build_buy_hold_baseline(
            symbols=self._symbols,
            initial_cash=self._initial_cash,
            initial_positions=seeded_positions,
            bars_by_symbol=bars_by_symbol,
            start=self._spec.start,
        )
        if seeded_positions or self._initial_cash:
            _seed_positions(
                self._event_store,
                seeded_positions,
                asof_ts=self._spec.start,
                cash_balance=self._initial_cash,
                run_id=run_id,
            )
            logger.info(
                "Backtest seeded positions count=%s cash_balance=%.2f",
                len(seeded_positions),
                self._initial_cash,
            )
        total_bars = _count_scheduled_symbol_runs(symbol_schedule, timestamps)
        effective_limit = _resolve_effective_replay_limit(total_bars=total_bars, max_runs=limit)

        data_sources_by_symbol = _build_data_sources(
            bars_by_symbol=bars_by_symbol,
            asset_class=self._asset_class,
            timeframe=self._spec.timeframe,
            symbols=self._symbols,
            allow_latest_prior_bar=self._assumptions.data.allow_latest_prior_bar,
            warnings=warnings,
        )
        configs_by_symbol = _build_symbol_runtime_configs(self._config, self._symbols)
        portfolio = _build_initial_portfolio(seeded_positions, cash_balance=self._initial_cash)
        trade_stats: _TradeStats | None = None
        try:
            with _cycle_log_suppression(enabled=not log_cycle_details):
                for ts in timestamps:
                    stop = False
                    for symbol in sorted(symbol_schedule.get(ts, [])):
                        data_source = data_sources_by_symbol.get(symbol)
                        config = configs_by_symbol.get(symbol)
                        if data_source is None or config is None:
                            continue
                        data_source.set_as_of(ts)
                        run_cycle(
                            event_store=self._event_store,
                            config=config,
                            decision_ts=ts,
                            market_data_source=data_source,
                            strategy=strategy,
                            risk_manager=risk_manager,
                            broker=broker,
                            portfolio=portfolio,
                            ingest_market_data=False,
                            run_id=run_id,
                            run_type="backtest",
                        )
                        count += 1
                        if progress_callback:
                            progress_callback(count, effective_limit or total_bars, ts if symbol_schedule else ts)
                        if limit is not None and count >= limit:
                            stop = True
                            break
                    prices = price_state.advance(ts)
                    valuation = _compute_equity(portfolio, prices)
                    equity_curve.append(EquityPoint(ts=ts, equity=valuation.equity))
                    exposure_samples.append(
                        (
                            valuation.net_notional,
                            valuation.gross_notional,
                            valuation.invested_pct,
                        )
                    )
                    benchmark_equity = _compute_holdings_equity(benchmark_holdings, prices)
                    benchmark_curve.append(EquityPoint(ts=ts, equity=benchmark_equity))
                    if stop:
                        break
        except Exception as exc:
            failed += 1
            run_status = "failed"
            run_error = str(exc)
            raise
        finally:
            self._event_store.record_run_session_finish(
                run_id=run_id,
                run_type="backtest",
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
                status=run_status,
                error_message=run_error,
                strategy_id=strategy_id,
                mode=self._config.mode,
                symbols=self._symbols,
                timeframe=self._spec.timeframe,
                start_ts=self._spec.start,
                end_ts=self._spec.end,
            )
            summary = _build_portfolio_summary(
                self._event_store,
                self._asset_class,
                self._spec.timeframe,
                portfolio=portfolio,
                bars_by_symbol=bars_by_symbol,
            )
            trade_stats = _compute_trade_stats(self._event_store, run_id, equity_curve)
            if self._owns_event_store:
                self._event_store.close()

        trade_stats = trade_stats or _empty_trade_stats()

        finished_at = datetime.now(timezone.utc)
        strategy_summary = _build_performance_summary(
            equity_curve,
            self._spec.timeframe,
            exposure_samples=exposure_samples,
            trade_stats=trade_stats,
        )
        benchmark_summary = _build_performance_summary(
            benchmark_curve,
            self._spec.timeframe,
            exposure_samples=None,
            trade_stats=None,
        )
        comparison = _build_relative_metrics(
            strategy_curve=equity_curve,
            benchmark_curve=benchmark_curve,
            timeframe=self._spec.timeframe,
        )
        result = _build_completed_backtest_result(
            total_runs=count,
            failed_runs=failed,
            started_at=started_at,
            finished_at=finished_at,
            asset_class=self._asset_class,
            symbols=self._symbols,
            timeframe=self._spec.timeframe,
            portfolio_summary=summary,
            assumptions=self._assumptions,
            warnings=warnings,
            trade_stats=trade_stats,
            strategy_performance=strategy_summary,
            benchmark_performance=benchmark_summary,
            relative_metrics=comparison,
            equity_curve=equity_curve,
            benchmark_curve=benchmark_curve,
            run_id=run_id,
        )
        _log_backtest_result(result)
        return result


def _build_backtest_runtime_config(
    config: Config,
    *,
    symbols: Sequence[str],
    asset_class: str,
    timeframe: str,
) -> Config:
    """Return the production config transformed for deterministic backtest execution."""
    return replace(
        config,
        mode="backtest",
        market_data_source="noop",
        market_data_symbols=tuple(symbols),
        market_data_asset_class=asset_class,
        strategy_timeframe=timeframe,
        broker_type="internal",
    )


def _build_symbol_runtime_configs(config: Config, symbols: Sequence[str]) -> dict[str, Config]:
    """Return one runtime config per symbol for single-symbol cycle execution."""
    return {symbol: replace(config, market_data_symbols=(symbol,)) for symbol in symbols}


def _count_scheduled_symbol_runs(
    symbol_schedule: Mapping[datetime, Sequence[str]],
    timestamps: Sequence[datetime],
) -> int:
    """Count symbol-level cycle executions in a timestamp schedule."""
    return sum(len(symbol_schedule[ts]) for ts in timestamps)


def _resolve_effective_replay_limit(*, total_bars: int, max_runs: int | None) -> int:
    """Resolve the progress denominator after applying an optional max-runs cap."""
    if max_runs is None:
        return total_bars
    return min(total_bars, max_runs)


def _build_completed_backtest_result(
    *,
    total_runs: int,
    failed_runs: int,
    started_at: datetime,
    finished_at: datetime,
    asset_class: str,
    symbols: Sequence[str],
    timeframe: str,
    portfolio_summary: "PortfolioSummary",
    assumptions: BacktestAssumptions,
    warnings: Sequence[str],
    trade_stats: _TradeStats,
    strategy_performance: PerformanceSummary,
    benchmark_performance: PerformanceSummary,
    relative_metrics: _RelativeMetrics,
    equity_curve: Sequence[EquityPoint],
    benchmark_curve: Sequence[EquityPoint],
    run_id: str,
) -> BacktestResult:
    """Assemble a completed backtest result from explicit summary values."""
    return BacktestResult(
        total_runs=total_runs,
        success_runs=total_runs - failed_runs,
        failed_runs=failed_runs,
        started_at=started_at,
        finished_at=finished_at,
        duration_seconds=(finished_at - started_at).total_seconds(),
        asset_class=asset_class,
        symbols=tuple(symbols),
        timeframe=timeframe,
        position_count=portfolio_summary.position_count,
        long_positions=portfolio_summary.long_positions,
        short_positions=portfolio_summary.short_positions,
        net_qty=portfolio_summary.net_qty,
        gross_qty=portfolio_summary.gross_qty,
        net_notional=portfolio_summary.net_notional,
        gross_notional=portfolio_summary.gross_notional,
        positions=portfolio_summary.positions,
        assumptions=assumptions,
        warnings=tuple(warnings),
        trades=trade_stats.trades,
        realized_pnl=trade_stats.realized_pnl,
        total_fees=trade_stats.total_fees,
        total_slippage=trade_stats.total_slippage,
        strategy_performance=strategy_performance,
        benchmark_performance=benchmark_performance,
        tracking_error=relative_metrics.tracking_error,
        information_ratio=relative_metrics.information_ratio,
        alpha=relative_metrics.alpha,
        beta=relative_metrics.beta,
        equity_curve=tuple(equity_curve),
        benchmark_curve=tuple(benchmark_curve),
        run_id=run_id,
    )


def _log_backtest_result(result: BacktestResult) -> None:
    """Emit human-readable summary logs for a completed backtest result."""
    logger.info(
        "Backtest complete total=%s success=%s failed=%s duration_seconds=%.2f",
        result.total_runs,
        result.success_runs,
        result.failed_runs,
        result.duration_seconds,
    )
    logger.info(
        "Backtest portfolio positions=%s long=%s short=%s net_qty=%.4f gross_qty=%.4f net_notional=%s gross_notional=%s",
        result.position_count,
        result.long_positions,
        result.short_positions,
        result.net_qty,
        result.gross_qty,
        _format_optional_float(result.net_notional),
        _format_optional_float(result.gross_notional),
    )
    logger.info(
        "Backtest performance total_return=%s cagr=%s volatility=%s sharpe=%s sortino=%s max_drawdown=%s",
        _format_optional_pct(result.strategy_performance.total_return),
        _format_optional_pct(result.strategy_performance.cagr),
        _format_optional_pct(result.strategy_performance.volatility),
        _format_optional_float(result.strategy_performance.sharpe),
        _format_optional_float(result.strategy_performance.sortino),
        _format_optional_pct(result.strategy_performance.max_drawdown),
    )
    logger.info(
        "Backtest benchmark total_return=%s cagr=%s volatility=%s sharpe=%s sortino=%s max_drawdown=%s",
        _format_optional_pct(result.benchmark_performance.total_return),
        _format_optional_pct(result.benchmark_performance.cagr),
        _format_optional_pct(result.benchmark_performance.volatility),
        _format_optional_float(result.benchmark_performance.sharpe),
        _format_optional_float(result.benchmark_performance.sortino),
        _format_optional_pct(result.benchmark_performance.max_drawdown),
    )
    logger.info(
        "Backtest relative tracking_error=%s information_ratio=%s alpha=%s beta=%s",
        _format_optional_pct(result.tracking_error),
        _format_optional_float(result.information_ratio),
        _format_optional_pct(result.alpha),
        _format_optional_float(result.beta),
    )
    for position in result.positions:
        logger.info(
            "Backtest position symbol=%s qty=%.4f avg_price=%s last_price=%s last_ts=%s market_value=%s pnl=%s",
            position.symbol,
            position.qty,
            _format_optional_float(position.avg_price),
            _format_optional_float(position.last_price),
            position.last_ts.isoformat() if position.last_ts else "<unset>",
            _format_optional_float(position.market_value),
            _format_optional_float(position.unrealized_pnl),
        )


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


def _fetch_latest_prices(
    event_store: EventStore,
    asset_class: str,
    symbols: Sequence[str],
    timeframe: str,
) -> dict[str, tuple[datetime, float]]:
    """Fetch the latest persisted close price per symbol for final valuation."""
    table = _bar_event_table_name(asset_class)
    connection = getattr(event_store, "connection", lambda: None)()
    if connection is None:
        return {}

    latest: dict[str, tuple[datetime, float]] = {}
    for symbol in symbols:
        if not hasattr(connection, "cursor"):
            continue
        with connection.cursor() as cursor:
            placeholder = _param_placeholder(connection)
            cursor.execute(
                f"""
                SELECT ts, close
                FROM {table}
                WHERE symbol = {placeholder} AND COALESCE(timeframe, '1Min') = {placeholder}
                ORDER BY ts DESC
                LIMIT 1
                """,
                [symbol.upper(), timeframe],
            )
            row = cursor.fetchone()
            if row:
                latest[symbol] = (row[0], float(row[1]))
    return latest


def _latest_prices_from_bars(bars_by_symbol: Mapping[str, Sequence[Bar]]) -> dict[str, tuple[datetime, float]]:
    """Return the last in-memory bar timestamp/close for each populated symbol."""
    latest: dict[str, tuple[datetime, float]] = {}
    for symbol, bars in bars_by_symbol.items():
        price = _latest_price_from_bars(bars)
        if price is not None:
            latest[symbol] = price
    return latest


def _latest_price_from_bars(bars: Sequence[Bar]) -> tuple[datetime, float] | None:
    """Return the last bar timestamp/close pair from one symbol's in-memory bars."""
    if not bars:
        return None
    bar = bars[-1]
    return _normalize_timestamp(bar.ts), float(bar.close)


@dataclass
class _PriceState:
    bars_by_symbol: Mapping[str, Sequence[Bar]]
    allow_price_carry_forward: bool = True

    def __post_init__(self) -> None:
        """Normalize derived fields after initialization."""
        self._indices: dict[str, int] = {symbol: 0 for symbol in self.bars_by_symbol}
        self._last_prices: dict[str, float] = {}

    def advance(self, ts: datetime) -> Mapping[str, float]:
        """Advance internal price cursors to a replay timestamp.

        With carry-forward enabled, last known prices remain available until a
        newer bar is seen. Without carry-forward, only exact-timestamp prices
        are returned so valuation gaps stay visible.
        """
        advanced = _advance_price_cursors(
            self.bars_by_symbol,
            indices=self._indices,
            previous_prices=self._last_prices,
            target=ts,
            allow_price_carry_forward=self.allow_price_carry_forward,
        )
        self._indices = dict(advanced.indices)
        self._last_prices = dict(advanced.prices)
        return dict(self._last_prices)


@dataclass(frozen=True)
class _PriceAdvanceResult:
    """Updated price cursor state for one replay timestamp."""

    indices: Mapping[str, int]
    prices: Mapping[str, float]


def _advance_price_cursors(
    bars_by_symbol: Mapping[str, Sequence[Bar]],
    *,
    indices: Mapping[str, int],
    previous_prices: Mapping[str, float],
    target: datetime,
    allow_price_carry_forward: bool,
) -> _PriceAdvanceResult:
    """Advance price cursors without mutating caller-owned state."""
    target_ts = _normalize_timestamp(target)
    if allow_price_carry_forward:
        return _advance_price_cursors_with_carry_forward(
            bars_by_symbol,
            indices=indices,
            previous_prices=previous_prices,
            target=target_ts,
        )
    return _advance_price_cursors_exact(
        bars_by_symbol,
        indices=indices,
        target=target_ts,
    )


def _advance_price_cursors_exact(
    bars_by_symbol: Mapping[str, Sequence[Bar]],
    *,
    indices: Mapping[str, int],
    target: datetime,
) -> _PriceAdvanceResult:
    """Advance cursors and return only exact-timestamp prices."""
    next_indices: dict[str, int] = {}
    current_prices: dict[str, float] = {}
    for symbol, bars in bars_by_symbol.items():
        idx = indices.get(symbol, 0)
        while idx < len(bars) and _normalize_timestamp(bars[idx].ts) < target:
            idx += 1
        if idx < len(bars) and _normalize_timestamp(bars[idx].ts) == target:
            current_prices[symbol] = float(bars[idx].close)
            idx += 1
        next_indices[symbol] = idx
    return _PriceAdvanceResult(indices=next_indices, prices=current_prices)


def _advance_price_cursors_with_carry_forward(
    bars_by_symbol: Mapping[str, Sequence[Bar]],
    *,
    indices: Mapping[str, int],
    previous_prices: Mapping[str, float],
    target: datetime,
) -> _PriceAdvanceResult:
    """Advance cursors while keeping latest known prices available."""
    next_indices: dict[str, int] = {}
    current_prices = dict(previous_prices)
    for symbol, bars in bars_by_symbol.items():
        idx = indices.get(symbol, 0)
        while idx < len(bars) and _normalize_timestamp(bars[idx].ts) <= target:
            current_prices[symbol] = float(bars[idx].close)
            idx += 1
        next_indices[symbol] = idx
    return _PriceAdvanceResult(indices=next_indices, prices=current_prices)


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
class _PositionSelection:
    """Selected and ignored initial positions for a backtest symbol universe."""

    selected: tuple[Position, ...]
    ignored_symbols: tuple[str, ...]


@dataclass(frozen=True)
class _InitialAvgPriceFill:
    """Initial positions after avg-price filling plus unresolved symbols."""

    positions: tuple[Position, ...]
    missing_price_symbols: tuple[str, ...]


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


def _compute_trade_stats(
    event_store: EventStore,
    run_id: str,
    equity_curve: Sequence[EquityPoint],
) -> _TradeStats | None:
    """Load fill evidence and compute trade-level statistics."""
    connection = getattr(event_store, "connection", lambda: None)()
    if connection is None or not hasattr(connection, "cursor"):
        return None

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT client_order_id, symbol, side, cycle_id
            FROM order_events
            WHERE run_id = %s AND client_order_id IS NOT NULL AND side IS NOT NULL
            """,
            [run_id],
        )
        order_rows = cursor.fetchall()

        cursor.execute(
            """
            SELECT client_order_id, fill_ts, fill_qty, fill_price, raw_fill_price, fee_amount, slippage_amount
            FROM fill_events
            WHERE run_id = %s
            ORDER BY fill_ts ASC
            """,
            [run_id],
        )
        fill_rows = cursor.fetchall()

    return _compute_trade_stats_from_events(
        order_events=_normalize_order_accounting_events(order_rows),
        fill_events=_normalize_fill_accounting_events(fill_rows),
        equity_curve=equity_curve,
    )


def _normalize_order_accounting_events(rows: Sequence[Sequence[object]]) -> tuple[_OrderAccountingEvent, ...]:
    """Normalize raw order-event SQL rows for deterministic trade accounting."""
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
    """Normalize raw fill-event SQL rows for deterministic trade accounting."""
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
    trade_stats: "_TradeStats | None" = None,
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


@dataclass(frozen=True)
class _DrawdownSummary:
    max_drawdown: float | None
    max_drawdown_duration: int | None
    ulcer_index: float | None


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
            amount = int(tf[:-len(unit)])
            return amount, unit.lower()
    raise ValueError(f"Unsupported timeframe: {timeframe}")


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


def _load_bars(
    event_store: EventStore,
    asset_class: str,
    symbols: Sequence[str],
    timeframe: str,
    start: datetime,
    end: datetime,
    *,
    lookback_bars: int = 0,
) -> dict[str, list[Bar]]:
    """Load historical bars for each symbol with optional pre-window lookback.

    Bars inside `[start, end]` drive replay timestamps. `lookback_bars` prepends
    earlier bars for indicators that need warmup history without allowing those
    pre-window bars to create decision cycles.
    """
    table = _bar_event_table_name(asset_class)
    connection = getattr(event_store, "connection", lambda: None)()
    if connection is None:
        logger.warning("Backtest bar load skipped; event store has no connection")
        return {}
    start_ts = _normalize_timestamp(start)
    end_ts = _normalize_timestamp(end)
    bars_by_symbol: dict[str, list[Bar]] = {symbol: [] for symbol in symbols}
    if not hasattr(connection, "cursor"):
        logger.warning("Backtest bar load skipped; unsupported connection type")
        return bars_by_symbol
    placeholder = _param_placeholder(connection)
    with connection.cursor() as cursor:
        for symbol in symbols:
            cursor.execute(
                f"""
                SELECT ts, open, high, low, close, volume, vwap, trade_count
                FROM {table}
                WHERE symbol = {placeholder}
                  AND COALESCE(timeframe, '1Min') = {placeholder}
                  AND ts >= {placeholder}
                  AND ts <= {placeholder}
                ORDER BY ts ASC
                """,
                [symbol.upper(), timeframe, start_ts, end_ts],
            )
            rows = cursor.fetchall()
            bars = [_row_to_bar(row) for row in rows]
            if lookback_bars > 0:
                cursor.execute(
                    f"""
                    SELECT ts, open, high, low, close, volume, vwap, trade_count
                    FROM {table}
                    WHERE symbol = {placeholder}
                      AND COALESCE(timeframe, '1Min') = {placeholder}
                      AND ts < {placeholder}
                    ORDER BY ts DESC
                    LIMIT {placeholder}
                    """,
                    [symbol.upper(), timeframe, start_ts, lookback_bars],
                )
                pre_rows = cursor.fetchall()
                pre_bars = [_row_to_bar(row) for row in reversed(pre_rows)]
                bars = pre_bars + bars
            bars_by_symbol[symbol] = bars
            logger.debug("Loaded backtest bars symbol=%s count=%s", symbol, len(bars))
    return bars_by_symbol


def _build_symbol_schedule(
    bars_by_symbol: Mapping[str, Sequence[Bar]],
    start: datetime,
    end: datetime,
) -> dict[datetime, list[str]]:
    """Build replay timestamps from loaded bars inside the requested window."""
    start_ts = _normalize_timestamp(start)
    end_ts = _normalize_timestamp(end)
    schedule: dict[datetime, list[str]] = {}
    for symbol, bars in bars_by_symbol.items():
        for bar in bars:
            bar_ts = _normalize_timestamp(bar.ts)
            if bar_ts < start_ts or bar_ts > end_ts:
                continue
            schedule.setdefault(bar_ts, []).append(symbol)
    return schedule


def _signal_lookback_window(strategy: Strategy) -> int:
    """Infer bar lookback needs from the injected strategy object."""
    signal_generator = getattr(strategy, "signal_generator", None)
    signals = getattr(signal_generator, "signals", ())
    windows: list[int] = []
    for signal in signals or ():
        window = getattr(signal, "window", None)
        if isinstance(window, int) and window > 0:
            windows.append(window)
    return max(windows, default=0)


def _build_initial_portfolio(positions: Sequence[Position], *, cash_balance: float) -> Portfolio:
    """Create a portfolio seeded with supplied positions and cash balance."""
    portfolio = Portfolio.empty(cash_balance=cash_balance)
    for position in positions:
        portfolio.positions[position.symbol] = position
    return portfolio


def _build_market_event(
    *,
    asset_class: str,
    symbol: str,
    timeframe: str,
    bar: Bar,
    source: str,
    ingested_at: datetime,
) -> MarketDataEvent:
    """Convert a normalized bar into the stock or crypto event-store shape."""
    common = dict(
        symbol=symbol,
        timeframe=timeframe,
        ts=_normalize_timestamp(bar.ts),
        ingested_at=_normalize_timestamp(ingested_at),
        open=float(bar.open),
        high=float(bar.high),
        low=float(bar.low),
        close=float(bar.close),
        volume=float(bar.volume),
        trade_count=float(bar.trade_count) if bar.trade_count is not None else None,
        vwap=float(bar.vwap) if bar.vwap is not None else None,
        source=source,
    )
    if asset_class in {"crypto", "cryptocurrency"}:
        return CryptoBarEvent(**common)
    return StockBarEvent(**common)


def _row_to_bar(row: Sequence[object]) -> Bar:
    """Convert a SQL bar row into the internal latest-first Bar primitive."""
    return Bar(
        ts=_normalize_timestamp(row[0]),  # type: ignore[arg-type]
        open=float(row[1]),
        high=float(row[2]),
        low=float(row[3]),
        close=float(row[4]),
        volume=float(row[5]),
        vwap=float(row[6]) if row[6] is not None else None,
        trade_count=float(row[7]) if row[7] is not None else None,
    )


def _build_data_sources(
    *,
    bars_by_symbol: Mapping[str, Sequence[Bar]],
    asset_class: str,
    timeframe: str,
    symbols: Sequence[str],
    allow_latest_prior_bar: bool,
    warnings: list[str],
) -> dict[str, BacktestMarketDataSource]:
    """Build per-symbol market-data sources sharing the same historical bars."""
    sources: dict[str, BacktestMarketDataSource] = {}
    for symbol in symbols:
        sources[symbol] = BacktestMarketDataSource(
            bars_by_symbol=bars_by_symbol,
            asset_class=asset_class,
            timeframe=timeframe,
            symbols=(symbol,),
            allow_latest_prior_bar=allow_latest_prior_bar,
            warnings=warnings,
        )
    return sources


def _build_backtest_broker(assumptions: BacktestAssumptions) -> Broker:
    """Create a deterministic internal broker for backtest execution."""
    return InternalPaperBroker(
        reject_probability=0.0,
        fill_delay_ms_mean=max(0.0, assumptions.latency_ms),
        fill_delay_ms_stddev=0.0,
        fill_qty_fraction_mean=1.0,
        fill_qty_fraction_stddev=0.0,
        slippage_bps=max(0.0, assumptions.slippage.bps),
        fee_fixed_per_order=max(0.0, assumptions.fees.fixed_per_order),
        fee_bps=max(0.0, assumptions.fees.bps),
        fee_minimum=max(0.0, assumptions.fees.minimum_fee),
        sleep_on_fill_delay=False,
    )


def _fetch_first_prices(
    event_store: EventStore,
    asset_class: str,
    symbols: Sequence[str],
    timeframe: str,
    start: datetime,
) -> dict[str, float]:
    """Fetch the first persisted close at or after the backtest start."""
    table = _bar_event_table_name(asset_class)
    connection = getattr(event_store, "connection", lambda: None)()
    if connection is None:
        return {}

    first: dict[str, float] = {}
    for symbol in symbols:
        if not hasattr(connection, "cursor"):
            continue
        with connection.cursor() as cursor:
            placeholder = _param_placeholder(connection)
            cursor.execute(
                f"""
                SELECT close
                FROM {table}
                WHERE symbol = {placeholder}
                  AND COALESCE(timeframe, '1Min') = {placeholder}
                  AND ts >= {placeholder}
                ORDER BY ts ASC
                LIMIT 1
                """,
                [symbol.upper(), timeframe, start],
            )
            row = cursor.fetchone()
            if row:
                first[symbol] = float(row[0])
    return first


def _first_prices_from_bars(
    bars_by_symbol: Mapping[str, Sequence[Bar]],
    start: datetime,
) -> dict[str, float]:
    """Return first in-memory close at or after the backtest start per symbol."""
    first: dict[str, float] = {}
    for symbol, bars in bars_by_symbol.items():
        price = _first_price_from_bars(bars, start)
        if price is not None:
            first[symbol] = price
    return first


def _first_price_from_bars(bars: Sequence[Bar], start: datetime) -> float | None:
    """Return the first close at or after the requested start for one symbol."""
    start_ts = _normalize_timestamp(start)
    for bar in bars:
        if _normalize_timestamp(bar.ts) >= start_ts:
            return float(bar.close)
    return None


def _format_optional_float(value: float | None) -> str:
    """Format an optional float for logs, using `<unset>` for missing values."""
    if value is None:
        return "<unset>"
    return f"{value:.4f}"


def _format_optional_pct(value: float | None) -> str:
    """Format an optional ratio as a percentage for logs."""
    if value is None:
        return "<unset>"
    return f"{value:.2%}"


def _fetch_timestamps(
    event_store: EventStore,
    asset_class: str,
    symbols: Sequence[str],
    timeframe: str,
    start: datetime,
    end: datetime,
) -> list[datetime]:
    """Fetch unique replay timestamps across symbols within the backtest window."""
    table = _bar_event_table_name(asset_class)
    connection = getattr(event_store, "connection", lambda: None)()
    if connection is None:
        logger.warning("Backtest lookup skipped; event store has no connection")
        return []

    timestamps: set[datetime] = set()
    for symbol in symbols:
        if hasattr(connection, "cursor"):
            with connection.cursor() as cursor:
                placeholder = _param_placeholder(connection)
                cursor.execute(
                    f"""
                    SELECT ts
                    FROM {table}
                    WHERE symbol = {placeholder}
                      AND COALESCE(timeframe, '1Min') = {placeholder}
                      AND ts >= {placeholder}
                      AND ts <= {placeholder}
                    ORDER BY ts ASC
                    """,
                    [symbol.upper(), timeframe, start, end],
                )
                rows = cursor.fetchall()
        else:
            rows = []
        timestamps.update(row[0] for row in rows)

    normalized = [_normalize_timestamp(ts) for ts in timestamps]
    return sorted(normalized)


def _normalize_timestamp(value: datetime) -> datetime:
    """Normalize timestamp values to UTC-aware datetimes."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _param_placeholder(connection: object) -> str:
    """Return the SQL parameter placeholder for the active backend."""
    module = connection.__class__.__module__
    if module.startswith("duckdb"):
        return "?"
    return "%s"


def _bar_event_table_name(asset_class: str) -> str:
    """Return the persisted bar-event table name for an asset class."""
    if asset_class in {"crypto", "cryptocurrency"}:
        return "crypto_bar_events"
    return "stock_bar_events"


def _parse_datetime(value: str) -> datetime:
    """Parse ISO datetime config values, accepting a trailing `Z` UTC suffix."""
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


def _parse_symbols_value(value: object | None) -> Sequence[str] | None:
    """Parse optional backtest symbols from a comma string or sequence."""
    if value is None:
        return None
    if isinstance(value, str):
        symbols = [symbol.strip().upper() for symbol in value.split(",") if symbol.strip()]
        return symbols or None
    if isinstance(value, (list, tuple)):
        symbols = [str(symbol).strip().upper() for symbol in value if str(symbol).strip()]
        return symbols or None
    raise ValueError("backtest.symbols must be a string or list")


def _configure_logging(level_name: str | None = None) -> None:
    """Configure console logging for standalone backtest helper commands."""
    level_name = (level_name or "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logger.info("Logging configured level=%s", level_name)


def _parse_args() -> argparse.Namespace:
    """Parse CLI arguments for this module."""
    parser = argparse.ArgumentParser(description="Run a backtest over stored bars.")
    parser.add_argument("config", help="Path to the YAML configuration file.")
    return parser.parse_args()


def main() -> None:
    """Reject direct module execution in favor of injected wrapper scripts.

    The backtest module requires caller-supplied strategy and risk-manager
    instances, so direct CLI execution would hide dependencies that should be
    explicit in a wrapper.
    """
    raise SystemExit(
        "trader.backtest is a library module. "
        "Construct a Strategy and RiskManager in your own wrapper script and call BacktestRunner(...)."
    )


@contextmanager
def _cycle_log_suppression(enabled: bool = True) -> Iterator[None]:
    """Temporarily suppress per-cycle logging noise."""
    if not enabled:
        yield
        return
    targets = [
        "trader.cycle",
        "trader.market_data",
        "trader.portfolio",
        "trader.signals",
        "trader.signal_generators",
        "trader.strategies",
    ]
    previous: list[tuple[logging.Logger, int]] = []
    for name in targets:
        target = logging.getLogger(name)
        previous.append((target, target.level))
        target.setLevel(logging.WARNING)
    try:
        yield
    finally:
        for target, level in previous:
            target.setLevel(level)


def _as_bool(value: object | None, default: bool) -> bool:
    """Coerce common YAML/env boolean spellings into a bool."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    raise ValueError(f"Invalid boolean value: {value}")


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


def _filter_positions(positions: Sequence[Position], symbols: set[str]) -> list[Position]:
    """Drop initial positions outside the selected backtest symbol universe."""
    selection = _select_positions_for_symbols(positions, symbols)
    for symbol in selection.ignored_symbols:
        logger.warning("Initial position ignored; symbol not in backtest symbols: %s", symbol)
    return list(selection.selected)


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
    snapshot.persist(event_store)


def _sanitize_value(value: Any) -> Any:
    """Recursively normalize values for JSON serialization."""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _sanitize_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize_value(v) for v in value]
    if isinstance(value, tuple):
        return [_sanitize_value(v) for v in value]
    return value


def serialize_backtest_result(result: BacktestResult) -> dict[str, Any]:
    """Convert a backtest result into JSON-compatible primitive values.

    Dataclasses become dictionaries and datetimes become ISO-8601 strings so
    the payload can be persisted to metrics snapshots or returned by the API.
    """
    raw = asdict(result)
    return _sanitize_value(raw)


def export_backtest_result_json(result: BacktestResult, path: str | Path) -> Path:
    """Write the complete serialized backtest result to a JSON file.

    Returns:
        The normalized output path after writing.
    """
    output_path = Path(path)
    output_path.write_text(json.dumps(serialize_backtest_result(result), indent=2), encoding="utf-8")
    return output_path


def export_backtest_equity_curve_csv(result: BacktestResult, path: str | Path) -> Path:
    """Write aligned strategy and benchmark equity curves to CSV.

    The CSV uses stable column names and leaves benchmark equity blank when the
    benchmark curve is shorter than the strategy curve.
    """
    output_path = Path(path)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(_EQUITY_CURVE_CSV_FIELDS),
        )
        writer.writeheader()
        writer.writerows(_build_equity_curve_csv_rows(result))
    return output_path


def _build_equity_curve_csv_rows(result: BacktestResult) -> tuple[dict[str, object], ...]:
    """Build stable CSV rows for aligned strategy and benchmark equity curves."""
    rows: list[dict[str, object]] = []
    for index, point in enumerate(result.equity_curve):
        benchmark_point = result.benchmark_curve[index] if index < len(result.benchmark_curve) else None
        rows.append(
            {
                "ts": point.ts.isoformat(),
                "strategy_equity": point.equity,
                "benchmark_equity": benchmark_point.equity if benchmark_point is not None else None,
            }
        )
    return tuple(rows)


def export_backtest_trades_csv(result: BacktestResult, path: str | Path) -> Path:
    """Write executed trade records to CSV using stable accounting columns.

    The export preserves raw price, adjusted fill price, fees, slippage, and
    realized PnL so downstream analysis can reproduce trade-level accounting.
    """
    output_path = Path(path)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(_TRADES_CSV_FIELDS),
        )
        writer.writeheader()
        writer.writerows(_build_trade_csv_rows(result.trades))
    return output_path


def _build_trade_csv_rows(trades: Sequence[TradeRecord]) -> tuple[dict[str, object], ...]:
    """Build stable CSV rows for executed trade accounting records."""
    return tuple(
        {
            "client_order_id": trade.client_order_id,
            "cycle_id": trade.cycle_id,
            "symbol": trade.symbol,
            "side": trade.side,
            "fill_ts": trade.fill_ts.isoformat(),
            "fill_qty": trade.fill_qty,
            "raw_fill_price": trade.raw_fill_price,
            "fill_price": trade.fill_price,
            "fee_amount": trade.fee_amount,
            "slippage_amount": trade.slippage_amount,
            "notional": trade.notional,
            "realized_pnl": trade.realized_pnl,
        }
        for trade in trades
    )


def _build_backtest_metrics_snapshot_payload(
    *,
    run_id: str,
    result: BacktestResult,
    ts: datetime,
) -> dict[str, object]:
    """Build the aggregate metrics-snapshot event payload for a backtest result."""
    return {
        "ts": _normalize_timestamp(ts),
        "run_id": run_id,
        "session_id": run_id,
        "cycle_id": None,
        "payload": json.dumps(serialize_backtest_result(result)),
    }


def persist_backtest_result(run_id: str, result: BacktestResult, config: Config) -> None:
    """Persist a serialized backtest result as a metrics snapshot.

    A fresh event store is built from config for the write and always closed
    afterward. The snapshot is keyed by `run_id`/`session_id` with no cycle ID
    because it represents the aggregate run outcome rather than one decision.
    """
    event_store = build_event_store(config)
    try:
        event_store.record_event(
            "metrics_snapshots",
            _build_backtest_metrics_snapshot_payload(
                run_id=run_id,
                result=result,
                ts=datetime.now(timezone.utc),
            ),
        )
    finally:
        event_store.close()


if __name__ == "__main__":
    main()
