"""Runtime service orchestration for live and realtime trading.

This module coordinates the long-running trading process: startup recovery,
portfolio seeding/sync, metrics sampling, broker construction, and once/loop/
Postgres NOTIFY-driven cycle dispatch. It sits in the runtime package because
it wires domain services to operational process concerns.
"""

from __future__ import annotations

import logging
import signal
import time
from datetime import datetime, timezone
from typing import Mapping

from ..config import Config
from ..cycle import run_cycle
from ..event_store import EventStore, build_event_store
from ..identifiers import deterministic_run_session_id
from ..market_data import NoOpMarketDataSource
from ..portfolio import Portfolio
from ..broker import Broker
from ..strategies.base import Strategy
from ..risk import RiskManager
from .broker_factory import build_runtime_broker
from .metrics import MetricsWorker
from .orders import run_startup_recovery
from .portfolio_sync import (
    build_initial_portfolio_seed,
    build_broker_portfolio_sync_snapshot,
    format_broker_portfolio_mismatch,
    matched_position_log_records,
    mismatched_position_log_records,
    resolve_initial_portfolio_seed_config,
)
from .service_config import (
    build_notify_cycle_config,
    decide_order_reconciliation,
    decide_pending_realtime_cycle,
    deduplicate_market_data_notify,
    parse_market_data_notify,
    resolve_metrics_worker_settings,
    resolve_notify_channel,
    resolve_portfolio_source,
    resolve_runtime_execution_mode,
    validate_startup_recovery_mode,
)
from ..strategy_metadata import resolve_strategy_id


logger = logging.getLogger(__name__)


class TraderService:
    """Long-running coordinator for live trading cycle execution.

    The service owns one event store, one broker instance, startup recovery,
    optional portfolio seeding/sync, optional metrics sampling, and the selected
    runtime mode (`once`, fixed-cadence loop, or Postgres NOTIFY-driven realtime).
    """

    def __init__(
        self,
        config: Config,
        *,
        strategy: Strategy,
        risk_manager: RiskManager,
        event_store: EventStore | None = None,
        cadence_seconds: float | None = None,
        min_trigger_interval_ms: int | None = None,
        notify_channel: str | None = None,
        max_iterations: int | None = None,
        config_snapshot: Mapping[str, object] | None = None,
    ) -> None:
        """Create a trader service with injected strategy and risk dependencies.

        Args:
            config: Typed runtime configuration.
            strategy: Strategy instance used for every cycle.
            risk_manager: Risk manager or pipeline used for every cycle.
            event_store: Optional shared event store; otherwise built from config.
            cadence_seconds: Loop-mode sleep between cycles.
            min_trigger_interval_ms: Debounce interval for generic realtime
                notifications.
            notify_channel: Postgres channel used in realtime mode.
            max_iterations: Optional loop bound for tests and controlled runs.
            config_snapshot: Optional raw config persisted with run metadata.

        Raises:
            ValueError: If strategy or risk manager is missing.
        """
        self._config = config
        self._event_store = event_store or build_event_store(config)
        self._owns_event_store = event_store is None
        self._cadence_seconds = cadence_seconds if cadence_seconds is not None else 1.0
        self._min_trigger_interval_ms = min_trigger_interval_ms if min_trigger_interval_ms is not None else 200
        self._notify_channel = _resolve_channel(notify_channel or "market_data")
        self._max_iterations = max_iterations
        self._config_snapshot = config_snapshot
        if strategy is None:
            raise ValueError("TraderService requires an injected strategy instance.")
        if risk_manager is None:
            raise ValueError("TraderService requires an injected risk manager instance.")
        self._strategy = strategy
        self._risk_manager = risk_manager
        self._broker = build_runtime_broker(self._config, self._event_store)
        self._stop = False
        self._metrics_worker: MetricsWorker | None = None
        self._last_order_reconciliation_at = 0.0

    def run(self) -> None:
        """Start the trading service and record the enclosing run session.

        Startup records run metadata, reconciles open orders according to policy,
        synchronizes or seeds portfolio state, starts metrics sampling, and then
        dispatches to once/loop/realtime execution. The run session is always
        finished in the event store before owned resources are closed.
        """
        _install_signal_handlers(self)
        strategy = self._strategy
        risk_manager = self._risk_manager
        strategy_id = resolve_strategy_id(strategy, self._config.strategy_id)
        mode = self._config.mode.lower()
        execution_mode = resolve_runtime_execution_mode(self._config.mode)
        started_at = datetime.now(timezone.utc)
        run_id = deterministic_run_session_id("trading", started_at)
        run_status = "success"
        run_error: str | None = None
        logger.info(
            "Initializing trader service run_id=%s mode=%s broker=%s strategy=%s symbols=%s timeframe=%s",
            run_id,
            mode,
            self._broker.__class__.__name__,
            strategy.__class__.__name__,
            ",".join(self._config.market_data_symbols) if self._config.market_data_symbols else "<none>",
            self._config.strategy_timeframe,
        )
        startup_recovery_mode = validate_startup_recovery_mode(self._config.trader_service_startup_recovery_mode)
        try:
            self._event_store.record_run_session_start(
                run_id=run_id,
                run_type="trading",
                started_at=started_at,
                strategy_id=strategy_id,
                config_snapshot=self._config_snapshot,
                mode=self._config.mode,
                symbols=self._config.market_data_symbols,
                timeframe=self._config.strategy_timeframe,
            )
            recovery = run_startup_recovery(
                event_store=self._event_store,
                broker=self._broker,
                configured_symbols=self._config.market_data_symbols,
                configured_asset_class=self._config.market_data_asset_class,
                mode=startup_recovery_mode,
                run_id=run_id,
            )
            logger.info(
                "Startup recovery mode=%s local_open_before=%s local_closed_missing=%s local_updated_from_broker=%s adopted_broker_open=%s broker_open_in_scope=%s broker_open_out_of_scope=%s",
                recovery.mode,
                recovery.local_open_before,
                recovery.local_closed_missing,
                recovery.local_updated_from_broker,
                recovery.adopted_broker_open,
                recovery.broker_open_in_scope,
                recovery.broker_open_out_of_scope,
            )
            self._last_order_reconciliation_at = time.monotonic()
            _maybe_sync_portfolio_from_alpaca(
                self._event_store,
                self._config,
                self._config_snapshot,
                run_id=run_id,
                broker=self._broker,
            )
            _maybe_seed_portfolio(
                self._event_store,
                self._config,
                self._config_snapshot,
                run_id=run_id,
            )
            self._start_metrics_worker(run_id=run_id)
            logger.info(
                "Trader service start mode=%s cadence_seconds=%s min_trigger_interval_ms=%s",
                mode,
                self._cadence_seconds,
                self._min_trigger_interval_ms,
            )
            if execution_mode == "once":
                self._run_once(run_id=run_id, strategy=strategy, risk_manager=risk_manager)
            elif execution_mode == "realtime":
                self._run_realtime(run_id=run_id, strategy=strategy, risk_manager=risk_manager)
            else:
                self._run_loop(run_id=run_id, strategy=strategy, risk_manager=risk_manager)
        except Exception as exc:
            run_status = "failed"
            run_error = str(exc)
            raise
        finally:
            self._event_store.record_run_session_finish(
                run_id=run_id,
                run_type="trading",
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
                status=run_status,
                error_message=run_error,
                strategy_id=strategy_id,
                mode=self._config.mode,
                symbols=self._config.market_data_symbols,
                timeframe=self._config.strategy_timeframe,
            )
            if self._owns_event_store:
                self._event_store.close()
            self._stop_metrics_worker()

    def stop(self) -> None:
        """Request graceful shutdown and stop the metrics worker if it is active.

        The running loop observes the stop flag between cycles, while the metrics
        worker is stopped immediately so background sampling does not outlive the
        service shutdown request.
        """
        self._stop = True
        self._stop_metrics_worker()

    def _run_once(self, *, run_id: str, strategy: Strategy, risk_manager: RiskManager) -> None:
        """Execute exactly one trading cycle for the current service run."""
        logger.info("Trader service executing single cycle")
        _safe_run_cycle(
            self._event_store,
            self._config,
            run_id=run_id,
            run_type="trading",
            strategy=strategy,
            risk_manager=risk_manager,
            broker=self._broker,
        )

    def _run_loop(self, *, run_id: str, strategy: Strategy, risk_manager: RiskManager) -> None:
        """Execute cycles at fixed cadence until stopped or iteration limit hit."""
        iterations = 0
        while not self._stop:
            _safe_run_cycle(
                self._event_store,
                self._config,
                run_id=run_id,
                run_type="trading",
                strategy=strategy,
                risk_manager=risk_manager,
                broker=self._broker,
            )
            self._maybe_reconcile_orders(run_id=run_id)
            iterations += 1
            if self._max_iterations is not None and iterations >= self._max_iterations:
                logger.info("Trader service reached max iterations=%s", self._max_iterations)
                break
            time.sleep(self._cadence_seconds)

    def _run_realtime(self, *, run_id: str, strategy: Strategy, risk_manager: RiskManager) -> None:
        """Execute cycles in response to market-data notifications.

        Valid market-data payloads narrow the cycle to the notified symbol and
        timestamp. Invalid/generic notifications set a pending flag and are
        debounced through `min_trigger_interval_ms` before running a full cycle.
        If LISTEN/NOTIFY is unavailable the service falls back to loop mode.
        """
        connection = getattr(self._event_store, "connection", lambda: None)()
        if connection is None or not hasattr(connection, "notifies"):
            logger.warning("Realtime mode requires Postgres LISTEN/NOTIFY; falling back to loop")
            self._run_loop(run_id=run_id, strategy=strategy, risk_manager=risk_manager)
            return

        try:
            connection.execute(f"LISTEN {self._notify_channel}")
        except Exception as exc:  # pragma: no cover - depends on Postgres
            logger.warning("Failed to LISTEN on channel=%s: %s", self._notify_channel, exc)
            self._run_loop(run_id=run_id, strategy=strategy, risk_manager=risk_manager)
            return

        iterations = 0
        pending = False
        last_run = 0.0
        last_seen: dict[tuple[str, str, str], datetime] = {}
        logger.info("Listening for market data notifications channel=%s", self._notify_channel)
        try:
            while not self._stop:
                notifications = list(connection.notifies(timeout=1.0))
                if notifications:
                    for notify in notifications:
                        logger.debug("Notification received channel=%s payload=%s", notify.channel, notify.payload)
                        notify_data = parse_market_data_notify(notify.payload)
                        if notify_data is not None:
                            notify_decision = deduplicate_market_data_notify(notify_data, last_seen)
                            last_seen = notify_decision.last_seen
                            if not notify_decision.should_run:
                                duplicate_key = notify_decision.duplicate_key or ("", "", "")
                                duplicate_ts = notify_decision.duplicate_ts
                                logger.debug(
                                    "Skipping duplicate market data notify symbol=%s timeframe=%s ts=%s",
                                    duplicate_key[0],
                                    duplicate_key[1],
                                    duplicate_ts.isoformat() if duplicate_ts is not None else "<unknown>",
                                )
                                continue
                            _safe_run_cycle_for_notify(
                                self._event_store,
                                self._config,
                                notify_data=notify_data,
                                run_id=run_id,
                                run_type="trading",
                                strategy=strategy,
                                risk_manager=risk_manager,
                                broker=self._broker,
                            )
                            self._maybe_reconcile_orders(run_id=run_id)
                            iterations += 1
                            if self._max_iterations is not None and iterations >= self._max_iterations:
                                logger.info("Trader service reached max iterations=%s", self._max_iterations)
                                return
                        else:
                            pending = True

                now = time.monotonic()
                pending_decision = decide_pending_realtime_cycle(
                    pending=pending,
                    now_monotonic=now,
                    last_run_monotonic=last_run,
                    min_trigger_interval_ms=self._min_trigger_interval_ms,
                )
                if pending_decision.should_run:
                    _safe_run_cycle(
                        self._event_store,
                        self._config,
                        run_id=run_id,
                        run_type="trading",
                        strategy=strategy,
                        risk_manager=risk_manager,
                        broker=self._broker,
                    )
                    self._maybe_reconcile_orders(run_id=run_id)
                    last_run = time.monotonic()
                    pending = False
                    iterations += 1
                if self._max_iterations is not None and iterations >= self._max_iterations:
                    logger.info("Trader service reached max iterations=%s", self._max_iterations)
                    break
                self._maybe_reconcile_orders(run_id=run_id)
        except KeyboardInterrupt:
            logger.info("Realtime loop interrupted; stopping service")
            self.stop()

    def _maybe_reconcile_orders(self, *, run_id: str, force: bool = False) -> None:
        """Periodically reconcile local open orders with the broker when supported."""
        interval = getattr(self._config, "trader_service_order_reconciliation_interval_seconds", 0)
        reconciler = getattr(self._broker, "reconcile_orders", None)
        now = time.monotonic()
        decision = decide_order_reconciliation(
            interval_seconds=interval,
            reconciler_available=callable(reconciler),
            now_monotonic=now,
            last_reconciliation_at=self._last_order_reconciliation_at,
            force=force,
        )
        if not decision.should_reconcile:
            return
        logger.info(
            "Broker refresh reason=periodic_order_reconciliation run_id=%s interval_seconds=%s",
            run_id,
            decision.interval_seconds,
        )
        try:
            assert callable(reconciler)
            updates = reconciler()
        except Exception as exc:  # pragma: no cover - broker dependent
            logger.exception("Periodic order reconciliation failed: %s", exc)
            return
        self._last_order_reconciliation_at = now
        logger.info("Periodic order reconciliation complete updates=%s", len(updates or ()))

    def _start_metrics_worker(self, *, run_id: str) -> None:
        """Start background metrics sampling if configured."""
        settings = resolve_metrics_worker_settings(self._config, run_id=run_id)
        if settings is None:
            return
        logger.info("Metrics worker using event-store portfolio snapshots")
        self._metrics_worker = MetricsWorker(
            event_store=self._event_store,
            symbols=settings.symbols,
            asset_class=settings.asset_class,
            interval_seconds=settings.interval_seconds,
            window_seconds=settings.window_seconds,
            run_id=settings.run_id,
            persist_snapshots=settings.persist_snapshots,
            broker=None,
        )
        self._metrics_worker.start()

    def _stop_metrics_worker(self) -> None:
        """Stop the metrics worker if running."""
        if self._metrics_worker is not None:
            self._metrics_worker.stop()
            self._metrics_worker.join(timeout=2.0)
            self._metrics_worker = None


def _safe_run_cycle(
    event_store: EventStore,
    config: Config,
    *,
    run_id: str,
    run_type: str,
    strategy: Strategy | None = None,
    risk_manager: RiskManager | None = None,
    broker: Broker | None = None,
) -> None:
    """Run a full-symbol cycle and contain failures inside the service loop."""
    try:
        portfolio = Portfolio.from_event_store(event_store)
        if resolve_portfolio_source(config, None) == "alpaca":
            logger.info("Trader service cached portfolio state positions=%s cash=%s", len(portfolio.positions), portfolio.cash_balance)
        else:
            _log_portfolio_state(portfolio)
        run_cycle(
            event_store=event_store,
            config=config,
            run_id=run_id,
            run_type=run_type,
            strategy=strategy,
            risk_manager=risk_manager,
            broker=broker,
            portfolio=portfolio,
        )
    except Exception as exc:
        logger.exception("Trading cycle failed: %s", exc)


def _safe_run_cycle_for_notify(
    event_store: EventStore,
    config: Config,
    *,
    notify_data: Mapping[str, object],
    run_id: str,
    run_type: str,
    strategy: Strategy | None = None,
    risk_manager: RiskManager | None = None,
    broker: Broker | None = None,
) -> None:
    """Run a notification-scoped cycle and contain failures inside realtime mode."""
    try:
        portfolio = Portfolio.from_event_store(event_store)
        if resolve_portfolio_source(config, None) == "alpaca":
            logger.info("Trader service cached portfolio state positions=%s cash=%s", len(portfolio.positions), portfolio.cash_balance)
        else:
            _log_portfolio_state(portfolio)
        event_config = build_notify_cycle_config(config, notify_data)
        run_cycle(
            event_store=event_store,
            config=event_config,
            run_id=run_id,
            run_type=run_type,
            market_data_source=NoOpMarketDataSource(),
            ingest_market_data=False,
            portfolio=portfolio,
            strategy=strategy,
            risk_manager=risk_manager,
            broker=broker,
        )
    except Exception as exc:
        logger.exception("Trading cycle failed for market data notify: %s", exc)


def _log_portfolio_state(portfolio: Portfolio) -> None:
    """Log portfolio cash and per-symbol position details."""
    if not portfolio.positions:
        logger.info("Trader service portfolio cash=%s positions=0", portfolio.cash_balance)
        return
    positions = [
        {
            "symbol": position.symbol,
            "qty": position.qty,
            "avg_price": position.avg_price,
        }
        for position in portfolio.positions.values()
    ]
    logger.info(
        "Trader service portfolio cash=%s positions=%s detail=%s",
        portfolio.cash_balance,
        len(portfolio.positions),
        positions,
    )


def _maybe_seed_portfolio(
    event_store: EventStore,
    config: Config,
    config_snapshot: Mapping[str, object] | None,
    *,
    run_id: str,
) -> None:
    """Seed an initial portfolio for realtime trading when configured."""
    portfolio_source = resolve_portfolio_source(config, config_snapshot)
    seed_config = resolve_initial_portfolio_seed_config(
        portfolio_source=portfolio_source,
        config_snapshot=config_snapshot,
    )
    if seed_config.reason == "portfolio_source_alpaca":
        logger.info("Portfolio seed skipped; portfolio_source=alpaca")
        return
    if not seed_config.should_inspect_existing:
        return
    existing = Portfolio.from_event_store(event_store)
    seed_decision = build_initial_portfolio_seed(
        seed_config=seed_config,
        existing_positions_count=len(existing.positions),
        existing_cash_balance=existing.cash_balance,
    )
    if seed_decision.reason == "existing_state":
        logger.info(
            "Portfolio seed skipped; existing state positions=%s cash=%s",
            len(existing.positions),
            existing.cash_balance,
        )
        return
    if not seed_decision.should_seed:
        return
    portfolio = Portfolio(
        positions={position.symbol: position for position in seed_decision.positions},
        cash_balance=seed_decision.cash,
    )
    snapshot = portfolio.snapshot(
        asof_ts=datetime.now(timezone.utc),
        run_id=run_id,
        session_id=run_id,
    )
    snapshot.persist(event_store)
    logger.info("Seeded initial portfolio positions=%s cash=%s", len(seed_decision.positions), seed_decision.cash)


def _maybe_sync_portfolio_from_alpaca(
    event_store: EventStore,
    config: Config,
    config_snapshot: Mapping[str, object] | None,
    *,
    run_id: str,
    broker: Broker | None = None,
) -> None:
    """Replace local portfolio snapshots with broker state when configured.

    Alpaca-backed portfolio state is treated as authoritative at startup. The
    function logs matched/mismatched broker positions, clears old snapshots,
    writes the fresh snapshot, and fails closed if any broker position is outside
    the configured trading universe.
    """
    source = resolve_portfolio_source(config, config_snapshot)
    if source != "alpaca":
        return
    if config.broker_type.lower() != "alpaca":
        logger.warning("Portfolio source alpaca ignored; broker_type=%s", config.broker_type)
        return
    try:
        if broker is None:
            broker = build_runtime_broker(config, event_store)
        logger.info("Broker refresh reason=startup_portfolio_sync run_id=%s", run_id)
        account = broker.get_account()
        positions_raw = broker.get_positions()
        sync_snapshot = build_broker_portfolio_sync_snapshot(
            account=account,
            positions_raw=positions_raw,
            configured_symbols=config.market_data_symbols,
            configured_asset_class=config.market_data_asset_class,
        )
        logger.info(
            "Broker account summary cash=%s configured_symbols=%s matched_positions=%s mismatched_positions=%s",
            sync_snapshot.cash,
            ",".join(sorted(sync_snapshot.configured_symbols)) if sync_snapshot.configured_symbols else "<none>",
            matched_position_log_records(sync_snapshot),
            mismatched_position_log_records(sync_snapshot),
        )
        _clear_position_snapshots(event_store)
        portfolio = Portfolio(
            positions={position.symbol: position for position in sync_snapshot.positions},
            cash_balance=sync_snapshot.cash,
        )
        snapshot = portfolio.snapshot(
            asof_ts=datetime.now(timezone.utc),
            run_id=run_id,
            session_id=run_id,
        )
        snapshot.persist(event_store)
        logger.info(
            "Reset local portfolio snapshot from Alpaca positions=%s cash=%s",
            len(sync_snapshot.positions),
            sync_snapshot.cash,
        )
        if sync_snapshot.mismatches:
            raise ValueError(format_broker_portfolio_mismatch(sync_snapshot.mismatches))
        logger.info("Synced Alpaca portfolio positions=%s cash=%s", len(sync_snapshot.positions), sync_snapshot.cash)
    except Exception as exc:  # pragma: no cover - external dependency
        logger.exception("Failed to sync Alpaca portfolio: %s", exc)
        raise


def _clear_position_snapshots(event_store: EventStore) -> None:
    """Remove existing position snapshots before syncing external portfolio state."""
    connection = getattr(event_store, "connection", lambda: None)()
    if connection is None:
        logger.warning("Position snapshot reset skipped; event store has no connection")
        return
    try:
        if hasattr(connection, "cursor"):
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM position_snapshots")
        else:
            connection.execute("DELETE FROM position_snapshots")
    except Exception as exc:  # pragma: no cover - depends on storage
        logger.warning("Failed to clear position snapshots: %s", exc)


def _resolve_channel(channel: str) -> str:
    """Validate a Postgres NOTIFY channel name with a safe fallback."""
    resolution = resolve_notify_channel(channel)
    if not resolution.valid:
        logger.warning("Invalid notify channel; falling back to market_data")
    return resolution.channel


def _install_signal_handlers(service: TraderService) -> None:
    """Attach signal handlers to stop the service cleanly."""

    def _handle_signal(signum: int, _frame: object) -> None:
        """Translate process signals into a graceful service stop request."""
        logger.info("Shutdown signal received (%s); stopping service", signum)
        service.stop()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)


if __name__ == "__main__":
    raise SystemExit(
        "trader.runtime.service is a library module. "
        "Use run_trader_service.py (external entrypoint) to start the service."
    )
