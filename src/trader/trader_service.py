"""Long-running trader service for loop/realtime execution."""

from __future__ import annotations

import argparse
import json
import logging
import signal
import time
import threading
from datetime import datetime, timezone
from dataclasses import replace
from typing import Iterable, Mapping
import re

from dotenv import load_dotenv

from .config import Config, build_config, load_yaml_config, resolve_log_level
from .cycle import _build_strategy, run_cycle
from .data import EventStore, build_event_store
from .identifiers import deterministic_run_session_id
from .market_data import NoOpMarketDataSource
from .portfolio import Portfolio, Position
from .broker import AlpacaPaperBroker
from .strategies.base import Strategy
from .portfolio import load_latest_positions, load_latest_cash
from .metrics import MetricsWorker


logger = logging.getLogger(__name__)

_CHANNEL_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class TraderService:
    """Execute trading cycles in loop or realtime mode."""

    def __init__(
        self,
        config: Config,
        *,
        event_store: EventStore | None = None,
        cadence_seconds: float | None = None,
        min_trigger_interval_ms: int | None = None,
        notify_channel: str | None = None,
        max_iterations: int | None = None,
        config_snapshot: Mapping[str, object] | None = None,
    ) -> None:
        """Initialize the instance."""
        self._config = config
        self._event_store = event_store or build_event_store(config)
        self._owns_event_store = event_store is None
        self._cadence_seconds = cadence_seconds if cadence_seconds is not None else 1.0
        self._min_trigger_interval_ms = min_trigger_interval_ms if min_trigger_interval_ms is not None else 200
        self._notify_channel = _resolve_channel(notify_channel or "market_data")
        self._max_iterations = max_iterations
        self._config_snapshot = config_snapshot
        self._strategy_cache: dict[tuple[str, str, str], Strategy] = {}
        self._stop = False
        self._metrics_worker: MetricsWorker | None = None

    def run(self) -> None:
        """Run the trading service based on the configured mode."""
        _install_signal_handlers(self)
        mode = self._config.mode.lower()
        started_at = datetime.now(timezone.utc)
        run_id = deterministic_run_session_id("trading", started_at)
        run_status = "success"
        run_error: str | None = None
        self._event_store.record_run_session_start(
            run_id=run_id,
            run_type="trading",
            started_at=started_at,
            strategy_id=self._config.strategy_id,
            config_snapshot=self._config_snapshot,
            mode=self._config.mode,
            symbols=self._config.market_data_symbols,
            timeframe=self._config.strategy_timeframe,
        )
        _maybe_sync_portfolio_from_alpaca(
            self._event_store,
            self._config,
            self._config_snapshot,
            run_id=run_id,
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
        try:
            if mode == "once":
                self._run_once(run_id=run_id)
            elif mode in {"realtime", "real_time", "real-time"}:
                self._run_realtime(run_id=run_id)
            else:
                self._run_loop(run_id=run_id)
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
                strategy_id=self._config.strategy_id,
                mode=self._config.mode,
                symbols=self._config.market_data_symbols,
                timeframe=self._config.strategy_timeframe,
            )
            if self._owns_event_store:
                self._event_store.close()
            self._stop_metrics_worker()

    def stop(self) -> None:
        """Request the service to stop."""
        self._stop = True
        self._stop_metrics_worker()

    def _run_once(self, *, run_id: str) -> None:
        """Handle run once."""
        logger.info("Trader service executing single cycle")
        strategy = self._get_strategy()
        _safe_run_cycle(
            self._event_store,
            self._config,
            run_id=run_id,
            run_type="trading",
            strategy=strategy,
        )

    def _run_loop(self, *, run_id: str) -> None:
        """Handle run loop."""
        strategy = self._get_strategy()
        iterations = 0
        while not self._stop:
            _safe_run_cycle(
                self._event_store,
                self._config,
                run_id=run_id,
                run_type="trading",
                strategy=strategy,
            )
            iterations += 1
            if self._max_iterations is not None and iterations >= self._max_iterations:
                logger.info("Trader service reached max iterations=%s", self._max_iterations)
                break
            time.sleep(self._cadence_seconds)

    def _run_realtime(self, *, run_id: str) -> None:
        """Handle run realtime."""
        connection = getattr(self._event_store, "connection", lambda: None)()
        if connection is None or not hasattr(connection, "notifies"):
            logger.warning("Realtime mode requires Postgres LISTEN/NOTIFY; falling back to loop")
            self._run_loop(run_id=run_id)
            return

        try:
            connection.execute(f"LISTEN {self._notify_channel}")
        except Exception as exc:  # pragma: no cover - depends on Postgres
            logger.warning("Failed to LISTEN on channel=%s: %s", self._notify_channel, exc)
            self._run_loop(run_id=run_id)
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
                        notify_data = _parse_market_data_notify(notify.payload)
                        if notify_data is not None:
                            symbol = notify_data.get("symbol")
                            timeframe = notify_data.get("timeframe")
                            asset_class = notify_data.get("asset_class") or ""
                            ts = notify_data.get("ts")
                            key = (symbol or "", timeframe or "", asset_class)
                            if symbol and timeframe and ts:
                                last_ts = last_seen.get(key)
                                if last_ts is not None and ts <= last_ts:
                                    logger.debug(
                                        "Skipping duplicate market data notify symbol=%s timeframe=%s ts=%s",
                                        symbol,
                                        timeframe,
                                        ts.isoformat(),
                                    )
                                    continue
                                last_seen[key] = ts
                            strategy = self._get_strategy(
                                symbol=notify_data.get("symbol"),
                                timeframe=notify_data.get("timeframe"),
                                asset_class=notify_data.get("asset_class"),
                            )
                            _safe_run_cycle_for_notify(
                                self._event_store,
                                self._config,
                                notify_data=notify_data,
                                run_id=run_id,
                                run_type="trading",
                                strategy=strategy,
                            )
                            iterations += 1
                            if self._max_iterations is not None and iterations >= self._max_iterations:
                                logger.info("Trader service reached max iterations=%s", self._max_iterations)
                                return
                        else:
                            pending = True

                now = time.monotonic()
                if pending and (now - last_run) * 1000 >= self._min_trigger_interval_ms:
                    _safe_run_cycle(
                        self._event_store,
                        self._config,
                        run_id=run_id,
                        run_type="trading",
                        strategy=self._get_strategy(),
                    )
                    last_run = time.monotonic()
                    pending = False
                    iterations += 1
                    if self._max_iterations is not None and iterations >= self._max_iterations:
                        logger.info("Trader service reached max iterations=%s", self._max_iterations)
                        break
        except KeyboardInterrupt:
            logger.info("Realtime loop interrupted; stopping service")
            self.stop()

    def _get_strategy(
        self,
        *,
        symbol: str | None = None,
        timeframe: str | None = None,
        asset_class: str | None = None,
    ) -> Strategy:
        """Return a cached strategy instance keyed by symbol/timeframe/asset class."""
        asset_class_value = (asset_class or self._config.market_data_asset_class).lower()
        symbol_value = (symbol or "__all__").upper()
        timeframe_value = timeframe or self._config.strategy_timeframe
        key = (symbol_value, timeframe_value, asset_class_value)
        cached = self._strategy_cache.get(key)
        if cached is not None:
            return cached
        config = self._config
        if symbol and timeframe:
            config = replace(
                config,
                market_data_symbols=(symbol,),
                market_data_asset_class=asset_class_value,
                strategy_timeframe=timeframe_value,
            )
        strategy = _build_strategy(config, self._event_store)
        self._strategy_cache[key] = strategy
        return strategy

    def _start_metrics_worker(self, *, run_id: str) -> None:
        """Start background metrics sampling if configured."""
        interval = getattr(self._config, "metrics_interval_seconds", 0)
        window = getattr(self._config, "metrics_window_seconds", None)
        enable_snapshots = getattr(self._config, "metrics_enable_snapshots", False)
        if interval is None or interval <= 0:
            return
        broker = None
        if self._config.broker_type.lower() == "alpaca":
            broker = AlpacaPaperBroker(
                api_key=self._config.alpaca_api_key,
                secret_key=self._config.alpaca_secret_key,
                base_url=self._config.alpaca_base_url,
            )
        self._metrics_worker = MetricsWorker(
            event_store=self._event_store,
            symbols=tuple(self._config.market_data_symbols or ()),
            asset_class=self._config.market_data_asset_class,
            interval_seconds=float(interval),
            window_seconds=float(window) if window else None,
            run_id=run_id,
            persist_snapshots=enable_snapshots,
            broker=broker,
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
) -> None:
    """Run a cycle and log failures without crashing the service."""
    try:
        portfolio = Portfolio.from_event_store(event_store)
        _log_portfolio_state(portfolio)
        run_cycle(
            event_store=event_store,
            config=config,
            run_id=run_id,
            run_type=run_type,
            strategy=strategy,
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
) -> None:
    """Handle safe run cycle for notify."""
    try:
        portfolio = Portfolio.from_event_store(event_store)
        _log_portfolio_state(portfolio)
        symbol = notify_data.get("symbol")
        timeframe = notify_data.get("timeframe")
        asset_class = notify_data.get("asset_class")
        if not symbol:
            raise ValueError("notify payload missing symbol")
        event_config = replace(
            config,
            market_data_symbols=(symbol,),
            market_data_asset_class=asset_class or config.market_data_asset_class,
            strategy_timeframe=timeframe or config.strategy_timeframe,
        )
        run_cycle(
            event_store=event_store,
            config=event_config,
            run_id=run_id,
            run_type=run_type,
            market_data_source=NoOpMarketDataSource(),
            ingest_market_data=False,
            portfolio=portfolio,
            strategy=strategy,
        )
    except Exception as exc:
        logger.exception("Trading cycle failed for market data notify: %s", exc)


def _parse_market_data_notify(payload: str) -> Mapping[str, object] | None:
    """Parse market data notify."""
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return None

    symbol = data.get("symbol")
    timeframe = data.get("timeframe")
    asset_class = data.get("asset_class")
    ts_value = data.get("ts")
    if not symbol or not timeframe or not ts_value:
        return None

    try:
        ts = datetime.fromisoformat(str(ts_value).replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        ts = ts.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None

    return {
        "symbol": str(symbol).upper(),
        "timeframe": str(timeframe),
        "asset_class": str(asset_class).lower() if asset_class else "",
        "ts": ts,
    }


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
    if _resolve_portfolio_source(config, config_snapshot) == "alpaca":
        logger.info("Portfolio seed skipped; portfolio_source=alpaca")
        return
    if not config_snapshot or not isinstance(config_snapshot, Mapping):
        return
    service_cfg = config_snapshot.get("trader_service", {})
    if service_cfg is None or not isinstance(service_cfg, Mapping):
        return
    positions_cfg = service_cfg.get("initial_positions")
    cash_cfg = service_cfg.get("initial_cash")
    if positions_cfg is None and cash_cfg is None:
        return
    existing = Portfolio.from_event_store(event_store)
    if existing.positions or abs(existing.cash_balance) > 1e-12:
        logger.info(
            "Portfolio seed skipped; existing state positions=%s cash=%s",
            len(existing.positions),
            existing.cash_balance,
        )
        return
    positions = _parse_initial_positions(positions_cfg)
    cash = _parse_initial_cash(cash_cfg)
    portfolio = Portfolio(
        positions={position.symbol: position for position in positions},
        cash_balance=cash,
    )
    snapshot = portfolio.snapshot(
        asof_ts=datetime.now(timezone.utc),
        run_id=run_id,
        session_id=run_id,
    )
    snapshot.persist(event_store)
    logger.info("Seeded initial portfolio positions=%s cash=%s", len(positions), cash)


def _maybe_sync_portfolio_from_alpaca(
    event_store: EventStore,
    config: Config,
    config_snapshot: Mapping[str, object] | None,
    *,
    run_id: str,
) -> None:
    """Sync portfolio state from Alpaca when configured."""
    source = _resolve_portfolio_source(config, config_snapshot)
    if source != "alpaca":
        return
    if config.broker_type.lower() != "alpaca":
        logger.warning("Portfolio source alpaca ignored; broker_type=%s", config.broker_type)
        return
    try:
        broker = AlpacaPaperBroker(
            api_key=config.alpaca_api_key,
            secret_key=config.alpaca_secret_key,
            base_url=config.alpaca_base_url,
        )
        account = broker.get_account()
        cash_raw = account.get("cash", 0.0)
        cash = float(cash_raw) if cash_raw is not None else 0.0
        positions_raw = broker.get_positions()
        _clear_position_snapshots(event_store)
        positions: list[Position] = []
        for position in positions_raw:
            symbol = str(position.get("symbol", "")).strip().upper()
            if not symbol:
                continue
            qty_raw = position.get("qty", 0.0)
            try:
                qty = float(qty_raw)
            except (TypeError, ValueError):
                qty = 0.0
            side = str(position.get("side", "")).lower().strip()
            if side == "short" and qty > 0:
                qty = -qty
            if abs(qty) < 1e-12:
                continue
            avg_price_raw = position.get("avg_entry_price")
            avg_price = float(avg_price_raw) if avg_price_raw is not None else None
            positions.append(Position(symbol=symbol, qty=qty, avg_price=avg_price))
        portfolio = Portfolio(
            positions={position.symbol: position for position in positions},
            cash_balance=cash,
        )
        snapshot = portfolio.snapshot(
            asof_ts=datetime.now(timezone.utc),
            run_id=run_id,
            session_id=run_id,
        )
        snapshot.persist(event_store)
        logger.info("Synced Alpaca portfolio positions=%s cash=%s", len(positions), cash)
    except Exception as exc:  # pragma: no cover - external dependency
        logger.exception("Failed to sync Alpaca portfolio: %s", exc)


def _resolve_portfolio_source(config: Config, config_snapshot: Mapping[str, object] | None) -> str:
    """Determine which source to use for realtime portfolio state."""
    source = None
    if config_snapshot and isinstance(config_snapshot, Mapping):
        service_cfg = config_snapshot.get("trader_service", {})
        if isinstance(service_cfg, Mapping):
            source = service_cfg.get("portfolio_source")
    if source:
        return str(source).strip().lower()
    if config.broker_type.lower() == "alpaca":
        return "alpaca"
    return "db"


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


def _parse_initial_positions(value: object | None) -> list[Position]:
    """Parse trader_service.initial_positions into Position objects."""
    if value is None:
        return []
    if not isinstance(value, Iterable) or isinstance(value, (str, bytes)):
        raise ValueError("trader_service.initial_positions must be a list of mappings")
    positions: list[Position] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise ValueError("initial_positions entries must be mappings")
        symbol = str(item.get("symbol", "")).strip().upper()
        if not symbol:
            continue
        qty = float(item.get("qty", 0.0))
        avg_price = item.get("avg_price")
        avg_price_value = float(avg_price) if avg_price is not None else None
        positions.append(Position(symbol=symbol, qty=qty, avg_price=avg_price_value))
    return positions


def _parse_initial_cash(value: object | None) -> float:
    """Parse trader_service.initial_cash into a float balance."""
    if value is None or value == "":
        return 0.0
    return float(value)


def _resolve_channel(channel: str) -> str:
    """Handle resolve channel."""
    if not _CHANNEL_RE.match(channel):
        logger.warning("Invalid notify channel; falling back to market_data")
        return "market_data"
    return channel


def _install_signal_handlers(service: TraderService) -> None:
    """Attach signal handlers to stop the service cleanly."""

    def _handle_signal(signum: int, _frame: object) -> None:
        """Handle shutdown signals and stop the service."""
        logger.info("Shutdown signal received (%s); stopping service", signum)
        service.stop()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)


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
    parser = argparse.ArgumentParser(description="Run the trader service.")
    parser.add_argument("config", help="Path to the YAML configuration file.")
    return parser.parse_args()


def main() -> None:
    """Module entry point for the trader service."""
    load_dotenv(".env")
    args = _parse_args()
    config_data = load_yaml_config(args.config)
    _configure_logging(resolve_log_level(config_data))
    config = build_config(config_data)

    service_cfg = config_data.get("trader_service", {})
    if service_cfg is None:
        service_cfg = {}
    if not isinstance(service_cfg, Mapping):
        raise ValueError("trader_service section must be a mapping")

    mode = service_cfg.get("mode", config.mode)
    config = replace(config, mode=str(mode))

    cadence_seconds = service_cfg.get("cadence_seconds")
    min_trigger_interval_ms = service_cfg.get("min_trigger_interval_ms")
    notify_channel = service_cfg.get("notify_channel")
    max_iterations = service_cfg.get("max_iterations")
    service = TraderService(
        config,
        cadence_seconds=float(cadence_seconds) if cadence_seconds is not None else None,
        min_trigger_interval_ms=int(min_trigger_interval_ms) if min_trigger_interval_ms is not None else None,
        notify_channel=str(notify_channel) if notify_channel else None,
        max_iterations=int(max_iterations) if max_iterations is not None else None,
        config_snapshot=config_data,
    )
    service.run()


if __name__ == "__main__":
    main()
