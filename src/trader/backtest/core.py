"""Backtest execution, accounting, export, and persistence helpers.

The module replays historical bars through the same `run_cycle` path used by
live trading, but supplies deterministic market data, an internal paper broker,
and frozen execution assumptions so research runs can be reproduced and audited.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import logging
from typing import Callable, Mapping, Sequence

from ..config import Config
from ..cycle import run_cycle
from ..event_store import EventStore, build_event_store
from ..identifiers import deterministic_run_session_id
from ..portfolio import Position
from ..strategies import Strategy
from ..risk import RiskManager
from ..strategy_metadata import resolve_strategy_id
from .data import (
    BacktestMarketDataSource,
    _build_data_sources,
    _load_bars,
)
from .data_queries import _build_symbol_schedule
from .benchmark import (
    _build_buy_hold_baseline,
    _compute_equity,
    _compute_holdings_equity,
)
from .models import (
    BacktestAssumptions,
    BacktestResult,
    BacktestSpec,
    EquityPoint,
    TradeStats as _TradeStats,
)
from .performance import (
    _build_performance_summary,
    _build_relative_metrics,
)
from .persistence import _compute_trade_stats
from .portfolio_state import (
    _build_initial_portfolio,
    _build_portfolio_summary,
    _fill_initial_avg_prices,
    _filter_positions,
    _seed_positions,
)
from .result_builders import (
    _build_completed_backtest_result,
    _build_empty_backtest_result,
)
from .trade_accounting import _empty_trade_stats
from .results import (
    _log_backtest_result,
)
from .runtime_planning import (
    _build_backtest_runtime_config,
    _build_symbol_runtime_configs,
    _count_scheduled_symbol_runs,
    _normalize_backtest_symbols,
    _resolve_backtest_asset_class,
    _resolve_effective_replay_limit,
    _signal_lookback_window,
)
from .replay import _PriceState
from .runtime import (
    _build_backtest_broker,
    _cycle_log_suppression,
)


logger = logging.getLogger(__name__)


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
        self._symbols = _normalize_backtest_symbols(symbols, config_symbols=config.market_data_symbols)
        self._asset_class = _resolve_backtest_asset_class(
            asset_class,
            config_asset_class=config.market_data_asset_class,
        )
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
        decision_scope = self._strategy.decision_scope
        if decision_scope not in {"per_symbol", "universe_snapshot"}:
            raise ValueError(f"unsupported strategy decision scope: {decision_scope}")
        if decision_scope == "universe_snapshot":
            expected_symbols = set(self._symbols)
            incomplete = [
                ts for ts in timestamps if set(symbol_schedule.get(ts, ())) != expected_symbols
            ]
            if incomplete:
                warnings.append(
                    f"Skipped {len(incomplete)} incomplete universe timestamps; exact symbol alignment is required."
                )
            timestamps = [
                ts for ts in timestamps if set(symbol_schedule.get(ts, ())) == expected_symbols
            ]
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
        total_runs = (
            len(timestamps)
            if decision_scope == "universe_snapshot"
            else _count_scheduled_symbol_runs(symbol_schedule, timestamps)
        )
        effective_limit = _resolve_effective_replay_limit(total_bars=total_runs, max_runs=limit)

        data_sources_by_symbol = _build_data_sources(
            bars_by_symbol=bars_by_symbol,
            asset_class=self._asset_class,
            timeframe=self._spec.timeframe,
            symbols=self._symbols,
            allow_latest_prior_bar=self._assumptions.data.allow_latest_prior_bar,
            warnings=warnings,
        )
        configs_by_symbol = _build_symbol_runtime_configs(self._config, self._symbols)
        universe_data_source = BacktestMarketDataSource(
            bars_by_symbol=bars_by_symbol,
            asset_class=self._asset_class,
            timeframe=self._spec.timeframe,
            symbols=self._symbols,
            allow_latest_prior_bar=False,
            warnings=warnings,
        )
        portfolio = _build_initial_portfolio(seeded_positions, cash_balance=self._initial_cash)
        trade_stats: _TradeStats | None = None
        try:
            with _cycle_log_suppression(enabled=not log_cycle_details):
                for ts in timestamps:
                    stop = False
                    if decision_scope == "universe_snapshot":
                        universe_data_source.set_as_of(ts)
                        run_cycle(
                            event_store=self._event_store,
                            config=self._config,
                            decision_ts=ts,
                            market_data_source=universe_data_source,
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
                            progress_callback(count, effective_limit or total_runs, ts)
                        if limit is not None and count >= limit:
                            stop = True
                    else:
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
                                progress_callback(count, effective_limit or total_runs, ts)
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


if __name__ == "__main__":
    main()
