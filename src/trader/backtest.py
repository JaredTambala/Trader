"""Backtest runner for historical cycle execution."""

from __future__ import annotations

import argparse
from bisect import bisect_left
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import datetime, timezone
import logging
from typing import Iterator, Mapping, Sequence

from dotenv import load_dotenv

from .config import Config, build_config, load_yaml_config, resolve_log_level
from .cycle import run_cycle
from .data import EventStore, build_event_store
from .identifiers import deterministic_run_session_id
from .indicators import SmaIndicator
from .market_data import CryptoBarEvent, MarketDataEvent, MarketDataSource, StockBarEvent
from .portfolio import Portfolio, PortfolioSnapshot, Position
from .signal_generators import InMemoryBarsSignalGenerator
from .signals import Bar, SmaCrossoverSignal
from .strategies import NoOpStrategy, SimpleStrategy, Strategy
from .timeframes import normalize_timeframe


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BacktestSpec:
    """Backtest configuration parameters."""

    start: datetime
    end: datetime
    timeframe: str
    max_runs: int | None = None


@dataclass(frozen=True)
class PositionSummary:
    """Aggregated position data for backtest summaries."""

    symbol: str
    qty: float
    avg_price: float | None
    last_price: float | None
    last_ts: datetime | None
    market_value: float | None
    unrealized_pnl: float | None


@dataclass(frozen=True)
class BacktestResult:
    """Aggregated backtest outcome summary."""

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
    strategy_performance: "PerformanceSummary"
    benchmark_performance: "PerformanceSummary"
    tracking_error: float | None
    information_ratio: float | None
    alpha: float | None
    beta: float | None
    equity_curve: tuple["EquityPoint", ...]
    benchmark_curve: tuple["EquityPoint", ...]


@dataclass(frozen=True)
class EquityPoint:
    """Single point on an equity curve."""

    ts: datetime
    equity: float


@dataclass(frozen=True)
class PerformanceSummary:
    """Performance metrics derived from an equity curve."""

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


class BacktestMarketDataSource(MarketDataSource):
    """Market data source backed by in-memory bars for backtests."""

    def __init__(
        self,
        *,
        bars_by_symbol: Mapping[str, Sequence[Bar]],
        asset_class: str,
        timeframe: str,
        source: str = "backtest",
        symbols: Sequence[str] | None = None,
    ) -> None:
        """Initialize the instance."""
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

    def set_as_of(self, as_of_ts: datetime) -> None:
        """Set the current timestamp for fetch calls."""
        self._as_of_ts = _normalize_timestamp(as_of_ts)

    def fetch(self) -> Sequence[MarketDataEvent]:
        """Fetch market data events for the configured window."""
        if self._as_of_ts is None:
            return []
        events: list[MarketDataEvent] = []
        for symbol, bars in self._bars_by_symbol.items():
            timestamps = self._timestamps_by_symbol.get(symbol, [])
            if not timestamps:
                continue
            idx = bisect_left(timestamps, self._as_of_ts)
            if idx >= len(timestamps) or timestamps[idx] != self._as_of_ts:
                idx = idx - 1
                if idx < 0:
                    logger.warning(
                        "Backtest price misalignment symbol=%s decision_ts=%s latest_ts=<none>; skipping",
                        symbol,
                        self._as_of_ts.isoformat(),
                    )
                    continue
                logger.warning(
                    "Backtest price misalignment symbol=%s decision_ts=%s latest_ts=%s; using latest bar",
                    symbol,
                    self._as_of_ts.isoformat(),
                    timestamps[idx].isoformat(),
                )
            bar = bars[idx]
            events.append(
                _build_market_event(
                    asset_class=self._asset_class,
                    symbol=symbol,
                    timeframe=self._timeframe,
                    bar=bar,
                    source=self._source,
                    ingested_at=self._as_of_ts,
                )
            )
        return events


class BacktestRunner:
    """Run the trading cycle over a historical window."""

    def __init__(
        self,
        config: Config,
        spec: BacktestSpec,
        *,
        symbols: Sequence[str] | None = None,
        asset_class: str | None = None,
        event_store: EventStore | None = None,
        initial_positions: Sequence[Position] | None = None,
        initial_cash: float | None = None,
        config_snapshot: Mapping[str, object] | None = None,
    ) -> None:
        """Initialize the instance."""
        self._spec = spec
        raw_symbols = list(symbols) if symbols else list(config.market_data_symbols)
        self._symbols = [symbol.strip().upper() for symbol in raw_symbols if str(symbol).strip()]
        self._asset_class = (asset_class or config.market_data_asset_class).lower()
        self._event_store = event_store or build_event_store(config)
        self._owns_event_store = event_store is None
        self._initial_positions = list(initial_positions) if initial_positions else []
        self._initial_cash = float(initial_cash) if initial_cash is not None else 0.0
        self._config_snapshot = config_snapshot
        self._config = replace(
            config,
            mode="backtest",
            market_data_source="noop",
            market_data_symbols=tuple(self._symbols),
            market_data_asset_class=self._asset_class,
            strategy_timeframe=spec.timeframe,
        )

    def run(self, *, log_cycle_details: bool = False) -> BacktestResult:
        """Run the backtest and return an aggregated summary."""
        if not self._symbols:
            logger.warning("No symbols configured for backtest")
            now = datetime.now(timezone.utc)
            empty_summary = PerformanceSummary(
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
            )
            return BacktestResult(
                total_runs=0,
                success_runs=0,
                failed_runs=0,
                started_at=now,
                finished_at=now,
                duration_seconds=0.0,
                asset_class=self._asset_class,
                symbols=tuple(self._symbols),
                timeframe=self._spec.timeframe,
                position_count=0,
                long_positions=0,
                short_positions=0,
                net_qty=0.0,
                gross_qty=0.0,
                net_notional=None,
                gross_notional=None,
                positions=tuple(),
                strategy_performance=empty_summary,
                benchmark_performance=empty_summary,
                tracking_error=None,
                information_ratio=None,
                alpha=None,
                beta=None,
                equity_curve=tuple(),
                benchmark_curve=tuple(),
            )
        if self._spec.start > self._spec.end:
            raise ValueError("Backtest start must be <= end")

        lookback = _signal_lookback_window(self._config)
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
            now = datetime.now(timezone.utc)
            empty_summary = PerformanceSummary(
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
            )
            return BacktestResult(
                total_runs=0,
                success_runs=0,
                failed_runs=0,
                started_at=now,
                finished_at=now,
                duration_seconds=0.0,
                asset_class=self._asset_class,
                symbols=tuple(self._symbols),
                timeframe=self._spec.timeframe,
                position_count=0,
                long_positions=0,
                short_positions=0,
                net_qty=0.0,
                gross_qty=0.0,
                net_notional=None,
                gross_notional=None,
                positions=tuple(),
                strategy_performance=empty_summary,
                benchmark_performance=empty_summary,
                tracking_error=None,
                information_ratio=None,
                alpha=None,
                beta=None,
                equity_curve=tuple(),
                benchmark_curve=tuple(),
            )

        count = 0
        limit = self._spec.max_runs
        failed = 0
        equity_curve: list[EquityPoint] = []
        benchmark_curve: list[EquityPoint] = []
        exposure_samples: list[tuple[float, float, float | None]] = []
        price_state = _PriceState(bars_by_symbol)
        logger.info(
            "Backtest start asset_class=%s symbols=%s timeframe=%s start=%s end=%s runs=%s",
            self._asset_class,
            ",".join(self._symbols),
            self._spec.timeframe,
            self._spec.start.isoformat(),
            self._spec.end.isoformat(),
            limit or len(timestamps),
        )
        started_at = datetime.now(timezone.utc)
        run_id = deterministic_run_session_id("backtest", started_at)
        run_status = "success"
        run_error: str | None = None
        self._event_store.record_run_session_start(
            run_id=run_id,
            run_type="backtest",
            started_at=started_at,
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
        data_sources_by_symbol = _build_data_sources(
            bars_by_symbol=bars_by_symbol,
            asset_class=self._asset_class,
            timeframe=self._spec.timeframe,
            symbols=self._symbols,
        )
        strategies_by_symbol = _build_backtest_strategies(
            self._config,
            bars_by_symbol,
            self._symbols,
            event_store=self._event_store,
        )
        configs_by_symbol = {
            symbol: replace(self._config, market_data_symbols=(symbol,))
            for symbol in self._symbols
        }
        portfolio = _build_initial_portfolio(seeded_positions, cash_balance=self._initial_cash)
        try:
            with _cycle_log_suppression(enabled=not log_cycle_details):
                for ts in timestamps:
                    stop = False
                    for symbol in sorted(symbol_schedule.get(ts, [])):
                        data_source = data_sources_by_symbol.get(symbol)
                        strategy = strategies_by_symbol.get(symbol)
                        config = configs_by_symbol.get(symbol)
                        if data_source is None or strategy is None or config is None:
                            continue
                        data_source.set_as_of(ts)
                        run_cycle(
                            event_store=self._event_store,
                            config=config,
                            decision_ts=ts,
                            market_data_source=data_source,
                            strategy=strategy,
                            portfolio=portfolio,
                            ingest_market_data=False,
                            run_id=run_id,
                            run_type="backtest",
                        )
                        count += 1
                        if limit is not None and count >= limit:
                            stop = True
                            break
                    prices = price_state.advance(ts)
                    equity, net_notional, gross_notional, invested_pct = _compute_equity(portfolio, prices)
                    equity_curve.append(EquityPoint(ts=ts, equity=equity))
                    exposure_samples.append((net_notional, gross_notional, invested_pct))
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
            if self._owns_event_store:
                self._event_store.close()

        finished_at = datetime.now(timezone.utc)
        strategy_summary = _build_performance_summary(
            equity_curve,
            self._spec.timeframe,
            exposure_samples=exposure_samples,
        )
        benchmark_summary = _build_performance_summary(
            benchmark_curve,
            self._spec.timeframe,
            exposure_samples=None,
        )
        comparison = _build_relative_metrics(
            strategy_curve=equity_curve,
            benchmark_curve=benchmark_curve,
            timeframe=self._spec.timeframe,
        )
        result = BacktestResult(
            total_runs=count,
            success_runs=count - failed,
            failed_runs=failed,
            started_at=started_at,
            finished_at=finished_at,
            duration_seconds=(finished_at - started_at).total_seconds(),
            asset_class=self._asset_class,
            symbols=tuple(self._symbols),
            timeframe=self._spec.timeframe,
            position_count=summary.position_count,
            long_positions=summary.long_positions,
            short_positions=summary.short_positions,
            net_qty=summary.net_qty,
            gross_qty=summary.gross_qty,
            net_notional=summary.net_notional,
            gross_notional=summary.gross_notional,
            positions=summary.positions,
            strategy_performance=strategy_summary,
            benchmark_performance=benchmark_summary,
            tracking_error=comparison.tracking_error,
            information_ratio=comparison.information_ratio,
            alpha=comparison.alpha,
            beta=comparison.beta,
            equity_curve=tuple(equity_curve),
            benchmark_curve=tuple(benchmark_curve),
        )
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
        return result


@dataclass(frozen=True)
class PortfolioSummary:
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
    """Build portfolio summary."""
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
    """demo"""


def _fetch_latest_prices(
    event_store: EventStore,
    asset_class: str,
    symbols: Sequence[str],
    timeframe: str,
) -> dict[str, tuple[datetime, float]]:
    """Fetch latest prices."""
    table = "crypto_bar_events" if asset_class in {"crypto", "cryptocurrency"} else "stock_bar_events"
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
    """Handle latest prices from bars."""
    latest: dict[str, tuple[datetime, float]] = {}
    for symbol, bars in bars_by_symbol.items():
        if not bars:
            continue
        bar = bars[-1]
        latest[symbol] = (_normalize_timestamp(bar.ts), float(bar.close))
    return latest


@dataclass
class _PriceState:
    bars_by_symbol: Mapping[str, Sequence[Bar]]

    def __post_init__(self) -> None:
        """Normalize derived fields after initialization."""
        self._indices: dict[str, int] = {symbol: 0 for symbol in self.bars_by_symbol}
        self._last_prices: dict[str, float] = {}

    def advance(self, ts: datetime) -> Mapping[str, float]:
        """Advance to the next timestamp in the schedule."""
        target = _normalize_timestamp(ts)
        for symbol, bars in self.bars_by_symbol.items():
            idx = self._indices.get(symbol, 0)
            while idx < len(bars) and _normalize_timestamp(bars[idx].ts) <= target:
                self._last_prices[symbol] = float(bars[idx].close)
                idx += 1
            self._indices[symbol] = idx
        return dict(self._last_prices)


@dataclass(frozen=True)
class _Holdings:
    cash_balance: float
    positions: Mapping[str, float]


@dataclass(frozen=True)
class _RelativeMetrics:
    tracking_error: float | None
    information_ratio: float | None
    alpha: float | None
    beta: float | None


def _build_buy_hold_baseline(
    *,
    symbols: Sequence[str],
    initial_cash: float,
    initial_positions: Sequence[Position],
    bars_by_symbol: Mapping[str, Sequence[Bar]],
    start: datetime,
) -> _Holdings:
    """Build buy hold baseline."""
    holdings: dict[str, float] = {position.symbol: position.qty for position in initial_positions}
    cash_balance = float(initial_cash)
    if cash_balance <= 0:
        return _Holdings(cash_balance=cash_balance, positions=holdings)
    first_prices = _first_prices_from_bars(bars_by_symbol, start)
    alloc_symbols = [symbol for symbol in symbols if symbol in first_prices]
    if not alloc_symbols:
        return _Holdings(cash_balance=cash_balance, positions=holdings)
    allocation = cash_balance / len(alloc_symbols)
    for symbol in alloc_symbols:
        price = first_prices[symbol]
        if price <= 0:
            continue
        qty = allocation / price
        holdings[symbol] = holdings.get(symbol, 0.0) + qty
    return _Holdings(cash_balance=0.0, positions=holdings)


def _compute_equity(
    portfolio: Portfolio,
    prices: Mapping[str, float],
) -> tuple[float, float, float, float | None]:
    """Compute equity."""
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
    return equity, net_notional, gross_notional, invested_pct


def _compute_holdings_equity(holdings: _Holdings, prices: Mapping[str, float]) -> float:
    """Compute holdings equity."""
    equity = holdings.cash_balance
    for symbol, qty in holdings.positions.items():
        price = prices.get(symbol)
        if price is None:
            continue
        equity += qty * price
    return equity


def _build_performance_summary(
    equity_curve: Sequence[EquityPoint],
    timeframe: str,
    *,
    exposure_samples: Sequence[tuple[float, float, float | None]] | None,
) -> PerformanceSummary:
    """Build performance summary."""
    if len(equity_curve) < 2:
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
        )
    start_equity = equity_curve[0].equity
    end_equity = equity_curve[-1].equity
    returns = _returns_from_curve(equity_curve)
    periods_per_year = _annualization_factor(timeframe)
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
    avg_net = avg_gross = avg_invested = None
    if exposure_samples:
        net_sum = sum(sample[0] for sample in exposure_samples)
        gross_sum = sum(sample[1] for sample in exposure_samples)
        invested_vals = [sample[2] for sample in exposure_samples if sample[2] is not None]
        count = len(exposure_samples)
        if count:
            avg_net = net_sum / count
            avg_gross = gross_sum / count
        if invested_vals:
            avg_invested = sum(invested_vals) / len(invested_vals)
    return PerformanceSummary(
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
        avg_net_exposure=avg_net,
        avg_gross_exposure=avg_gross,
        avg_invested_pct=avg_invested,
    )


def _build_relative_metrics(
    *,
    strategy_curve: Sequence[EquityPoint],
    benchmark_curve: Sequence[EquityPoint],
    timeframe: str,
) -> _RelativeMetrics:
    """Build relative metrics."""
    returns = _returns_from_curve(strategy_curve)
    benchmark_returns = _returns_from_curve(benchmark_curve)
    length = min(len(returns), len(benchmark_returns))
    if length == 0:
        return _RelativeMetrics(None, None, None, None)
    returns = returns[:length]
    benchmark_returns = benchmark_returns[:length]
    excess = [r - b for r, b in zip(returns, benchmark_returns)]
    periods_per_year = _annualization_factor(timeframe)
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
    """Parse timeframe parts."""
    tf = normalize_timeframe(timeframe)
    for unit in ("Min", "Hour", "Day", "Week", "Month"):
        if tf.endswith(unit):
            amount = int(tf[:-len(unit)])
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
    return (end_equity / start_equity) ** (1 / years) - 1.0


def _compute_sharpe(returns: Sequence[float], periods_per_year: float) -> float | None:
    """Compute the Sharpe ratio."""
    if not returns:
        return None
    std = _variance(returns) ** 0.5
    if std == 0.0:
        return None
    return _mean(returns) / std * (periods_per_year ** 0.5)


def _compute_sortino(returns: Sequence[float], periods_per_year: float) -> float | None:
    """Compute the Sortino ratio."""
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
    """Load bars."""
    table = "crypto_bar_events" if asset_class in {"crypto", "cryptocurrency"} else "stock_bar_events"
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
    """Build symbol schedule."""
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


def _build_backtest_strategies(
    config: Config,
    bars_by_symbol: Mapping[str, Sequence[Bar]],
    symbols: Sequence[str],
    *,
    event_store: EventStore,
) -> dict[str, Strategy]:
    """Build backtest strategies."""
    strategies: dict[str, Strategy] = {}
    strategy_type = (getattr(config, "strategy_type", "noop") or "noop").lower()
    for symbol in symbols:
        if strategy_type == "sma":
            generator = InMemoryBarsSignalGenerator(
                bars_by_symbol=bars_by_symbol,
                symbols=(symbol,),
                timeframe=config.strategy_timeframe,
                event_store=event_store,
                signals=[
                    SmaCrossoverSignal(
                        short=SmaIndicator(period=config.sma_short_window),
                        long=SmaIndicator(period=config.sma_long_window),
                    )
                ],
            )
            strategies[symbol] = SimpleStrategy(signal_generator=generator, primary_signal="sma_crossover")
        elif strategy_type == "noop":
            strategies[symbol] = NoOpStrategy()
        else:
            logger.warning("Unknown backtest strategy_type=%s; falling back to noop", strategy_type)
            strategies[symbol] = NoOpStrategy()
    return strategies


def _signal_lookback_window(config: Config) -> int:
    """Handle signal lookback window."""
    strategy_type = (getattr(config, "strategy_type", "noop") or "noop").lower()
    if strategy_type == "sma":
        return max(int(config.sma_short_window), int(config.sma_long_window)) + 1
    return 0


def _build_initial_portfolio(positions: Sequence[Position], *, cash_balance: float) -> Portfolio:
    """Build initial portfolio."""
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
    """Build market event."""
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
    """Handle row to bar."""
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
) -> dict[str, BacktestMarketDataSource]:
    """Build data sources."""
    sources: dict[str, BacktestMarketDataSource] = {}
    for symbol in symbols:
        sources[symbol] = BacktestMarketDataSource(
            bars_by_symbol=bars_by_symbol,
            asset_class=asset_class,
            timeframe=timeframe,
            symbols=(symbol,),
        )
    return sources


def _fetch_first_prices(
    event_store: EventStore,
    asset_class: str,
    symbols: Sequence[str],
    timeframe: str,
    start: datetime,
) -> dict[str, float]:
    """Fetch first prices."""
    table = "crypto_bar_events" if asset_class in {"crypto", "cryptocurrency"} else "stock_bar_events"
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
    """Handle first prices from bars."""
    first: dict[str, float] = {}
    start_ts = _normalize_timestamp(start)
    for symbol, bars in bars_by_symbol.items():
        for bar in bars:
            if _normalize_timestamp(bar.ts) >= start_ts:
                first[symbol] = float(bar.close)
                break
    return first


def _format_optional_float(value: float | None) -> str:
    """Format optional float."""
    if value is None:
        return "<unset>"
    return f"{value:.4f}"


def _format_optional_pct(value: float | None) -> str:
    """Format optional pct."""
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
    """Fetch timestamps."""
    table = "crypto_bar_events" if asset_class in {"crypto", "cryptocurrency"} else "stock_bar_events"
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


def _parse_datetime(value: str) -> datetime:
    """Parse datetime."""
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


def _parse_symbols_value(value: object | None) -> Sequence[str] | None:
    """Parse symbols value."""
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
    """Configure module logging defaults."""
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
    """Module entry point for backtests."""
    load_dotenv(".env")
    args = _parse_args()
    config_data = load_yaml_config(args.config)
    _configure_logging(resolve_log_level(config_data))
    config = build_config(config_data)

    backtest = config_data.get("backtest", {})
    if backtest is None:
        backtest = {}
    if not isinstance(backtest, Mapping):
        raise ValueError("backtest section must be a mapping")

    start_value = backtest.get("start")
    end_value = backtest.get("end")
    if not start_value or not end_value:
        raise ValueError("backtest.start and backtest.end are required")
    spec = BacktestSpec(
        start=_parse_datetime(str(start_value)),
        end=_parse_datetime(str(end_value)),
        timeframe=normalize_timeframe(str(backtest.get("timeframe", config.strategy_timeframe))),
        max_runs=int(backtest.get("max_runs")) if backtest.get("max_runs") is not None else None,
    )
    log_cycle_details = _as_bool(backtest.get("log_cycle_details"), False)
    initial_positions = _parse_initial_positions(backtest.get("initial_positions"))
    initial_cash = _parse_initial_cash(backtest.get("initial_cash"))
    runner = BacktestRunner(
        config,
        spec,
        symbols=_parse_symbols_value(backtest.get("symbols")),
        asset_class=str(backtest.get("asset_class")) if backtest.get("asset_class") else None,
        initial_positions=initial_positions,
        initial_cash=initial_cash,
        config_snapshot=config_data,
    )
    runner.run(log_cycle_details=log_cycle_details)


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
    """Coerce a value into a boolean."""
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
    """Parse initial positions."""
    if value is None:
        return None
    if not isinstance(value, (list, tuple)):
        raise ValueError("backtest.initial_positions must be a list")
    positions: list[Position] = []
    for item in value:
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
        positions.append(Position(symbol=symbol, qty=qty, avg_price=avg_value))
    return positions


def _parse_initial_cash(value: object | None) -> float:
    """Parse initial cash."""
    if value is None or value == "":
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid initial_cash value: {value}") from exc


def _filter_positions(positions: Sequence[Position], symbols: set[str]) -> list[Position]:
    """Filter positions."""
    if not positions or not symbols:
        return list(positions)
    filtered: list[Position] = []
    for position in positions:
        if position.symbol in symbols:
            filtered.append(position)
        else:
            logger.warning("Initial position ignored; symbol not in backtest symbols: %s", position.symbol)
    return filtered


def _fill_initial_avg_prices(
    event_store: EventStore,
    asset_class: str,
    timeframe: str,
    start: datetime,
    positions: Sequence[Position],
    *,
    bars_by_symbol: Mapping[str, Sequence[Bar]] | None = None,
) -> list[Position]:
    """Handle fill initial avg prices."""
    if not positions:
        return []
    missing = [position.symbol for position in positions if position.avg_price is None]
    if not missing:
        return list(positions)
    if bars_by_symbol is not None:
        first_prices = _first_prices_from_bars(bars_by_symbol, start)
    else:
        first_prices = _fetch_first_prices(event_store, asset_class, missing, timeframe, start)
    filled: list[Position] = []
    for position in positions:
        avg_price = position.avg_price
        if avg_price is None:
            avg_price = first_prices.get(position.symbol)
            if avg_price is None:
                logger.warning(
                    "Initial position avg_price missing and no first bar found symbol=%s",
                    position.symbol,
                )
        filled.append(Position(symbol=position.symbol, qty=position.qty, avg_price=avg_price))
    return filled


def _seed_positions(
    event_store: EventStore,
    positions: Sequence[Position],
    *,
    asof_ts: datetime,
    cash_balance: float,
    run_id: str | None,
) -> None:
    """Seed positions."""
    snapshot = PortfolioSnapshot(
        asof_ts=asof_ts,
        positions=tuple(positions),
        cash_balance=cash_balance,
        run_id=run_id,
    )
    snapshot.persist(event_store)


if __name__ == "__main__":
    main()
