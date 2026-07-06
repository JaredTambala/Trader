"""Pure runtime service configuration and notification parsing helpers."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timezone
import json
import re

from ..config import Config
from ..portfolio import Position

__all__ = [
    "MarketDataNotifyDecision",
    "MetricsWorkerSettings",
    "NotifyChannelResolution",
    "OrderReconciliationDecision",
    "PendingRealtimeCycleDecision",
    "build_notify_cycle_config",
    "decide_pending_realtime_cycle",
    "decide_order_reconciliation",
    "deduplicate_market_data_notify",
    "parse_initial_cash",
    "parse_initial_positions",
    "parse_market_data_notify",
    "resolve_runtime_execution_mode",
    "resolve_metrics_worker_settings",
    "resolve_notify_channel",
    "resolve_portfolio_source",
    "validate_startup_recovery_mode",
]

_CHANNEL_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_REALTIME_MODES = {"realtime", "real_time", "real-time"}
_STARTUP_RECOVERY_MODES = {"resume", "fail_closed"}


@dataclass(frozen=True)
class NotifyChannelResolution:
    """Validated Postgres NOTIFY channel selection."""

    channel: str
    valid: bool


@dataclass(frozen=True)
class MarketDataNotifyDecision:
    """Decision for whether a parsed market-data notification should run a cycle."""

    should_run: bool
    last_seen: dict[tuple[str, str, str], datetime]
    duplicate_key: tuple[str, str, str] | None = None
    duplicate_ts: datetime | None = None


@dataclass(frozen=True)
class OrderReconciliationDecision:
    """Decision for whether periodic broker order reconciliation should run."""

    should_reconcile: bool
    reason: str
    interval_seconds: float | int | None


@dataclass(frozen=True)
class MetricsWorkerSettings:
    """Resolved settings for constructing the runtime metrics worker."""

    symbols: tuple[str, ...]
    asset_class: str
    interval_seconds: float
    window_seconds: float | None
    run_id: str
    persist_snapshots: bool


@dataclass(frozen=True)
class PendingRealtimeCycleDecision:
    """Decision for whether a pending generic realtime notification should run."""

    should_run: bool
    reason: str


def resolve_runtime_execution_mode(mode: str) -> str:
    """Return the canonical service execution branch for a configured mode."""
    normalized_mode = str(mode).lower()
    if normalized_mode == "once":
        return "once"
    if normalized_mode in _REALTIME_MODES:
        return "realtime"
    return "loop"


def validate_startup_recovery_mode(mode: str) -> str:
    """Validate the startup order-recovery policy used by `TraderService`.

    Returns:
        The validated mode unchanged, preserving the service's existing exact
        config matching.

    Raises:
        ValueError: If the mode is not one of the supported startup policies.
    """
    if mode not in _STARTUP_RECOVERY_MODES:
        raise ValueError(
            "TraderService startup recovery mode must be 'resume' or 'fail_closed'. "
            "Use run_order_recovery.py clean-start for local event-store cleanup."
        )
    return mode


def parse_market_data_notify(payload: str) -> Mapping[str, object] | None:
    """Parse and validate a market-data notification payload.

    Returns `None` for malformed JSON or missing fields so realtime mode can
    debounce a generic full-cycle trigger instead of crashing the listener.
    """
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, Mapping):
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


def deduplicate_market_data_notify(
    notify_data: Mapping[str, object],
    last_seen: Mapping[tuple[str, str, str], datetime],
) -> MarketDataNotifyDecision:
    """Return the realtime duplicate-filter decision and next seen-state.

    Notifications with symbol, timeframe, and timestamp are de-duplicated per
    `(symbol, timeframe, asset_class)` key. Payloads without those typed fields
    are treated as runnable generic notifications and leave state unchanged.
    """
    symbol = notify_data.get("symbol")
    timeframe = notify_data.get("timeframe")
    asset_class = notify_data.get("asset_class") or ""
    ts = notify_data.get("ts")
    if not symbol or not timeframe or not isinstance(ts, datetime):
        return MarketDataNotifyDecision(should_run=True, last_seen=dict(last_seen))
    key = (str(symbol), str(timeframe), str(asset_class))
    previous_ts = last_seen.get(key)
    if previous_ts is not None and ts <= previous_ts:
        return MarketDataNotifyDecision(
            should_run=False,
            last_seen=dict(last_seen),
            duplicate_key=key,
            duplicate_ts=ts,
        )
    updated = dict(last_seen)
    updated[key] = ts
    return MarketDataNotifyDecision(should_run=True, last_seen=updated)


def decide_order_reconciliation(
    *,
    interval_seconds: float | int | None,
    reconciler_available: bool,
    now_monotonic: float,
    last_reconciliation_at: float,
    force: bool,
) -> OrderReconciliationDecision:
    """Return the periodic order-reconciliation timing decision.

    Args:
        interval_seconds: Configured reconciliation interval. `None` and
            non-positive values disable reconciliation, including forced calls.
        reconciler_available: Whether the broker exposes a reconciliation
            capability.
        now_monotonic: Current monotonic clock value supplied by the caller.
        last_reconciliation_at: Last successful reconciliation monotonic time.
        force: Whether interval throttling should be bypassed.

    Returns:
        Immutable decision value with a diagnostic reason.
    """
    if interval_seconds is None or interval_seconds <= 0:
        return OrderReconciliationDecision(False, "disabled", interval_seconds)
    if not reconciler_available:
        return OrderReconciliationDecision(False, "reconciler_unavailable", interval_seconds)
    if force:
        return OrderReconciliationDecision(True, "forced", interval_seconds)
    if last_reconciliation_at and now_monotonic - last_reconciliation_at < interval_seconds:
        return OrderReconciliationDecision(False, "too_soon", interval_seconds)
    return OrderReconciliationDecision(True, "due", interval_seconds)


def decide_pending_realtime_cycle(
    *,
    pending: bool,
    now_monotonic: float,
    last_run_monotonic: float,
    min_trigger_interval_ms: int,
) -> PendingRealtimeCycleDecision:
    """Return whether pending generic realtime notifications should run a cycle."""
    if not pending:
        return PendingRealtimeCycleDecision(False, "not_pending")
    elapsed_ms = (now_monotonic - last_run_monotonic) * 1000
    if elapsed_ms < min_trigger_interval_ms:
        return PendingRealtimeCycleDecision(False, "debounced")
    return PendingRealtimeCycleDecision(True, "due")


def build_notify_cycle_config(config: Config, notify_data: Mapping[str, object]) -> Config:
    """Return a config narrowed to a parsed market-data notification.

    Args:
        config: Base runtime configuration.
        notify_data: Parsed notification payload from `parse_market_data_notify`.

    Returns:
        A replacement config scoped to the notified symbol/timeframe/asset class.

    Raises:
        ValueError: If the notification has no symbol.
    """
    symbol = notify_data.get("symbol")
    if not symbol:
        raise ValueError("notify payload missing symbol")
    timeframe = notify_data.get("timeframe")
    asset_class = notify_data.get("asset_class")
    return replace(
        config,
        market_data_symbols=(str(symbol),),
        market_data_asset_class=str(asset_class) if asset_class else config.market_data_asset_class,
        strategy_timeframe=str(timeframe) if timeframe else config.strategy_timeframe,
    )


def resolve_metrics_worker_settings(config: Config, *, run_id: str) -> MetricsWorkerSettings | None:
    """Return metrics worker settings when runtime metrics sampling is enabled."""
    interval = getattr(config, "metrics_interval_seconds", 0)
    if interval is None or interval <= 0:
        return None
    window = getattr(config, "metrics_window_seconds", None)
    return MetricsWorkerSettings(
        symbols=tuple(config.market_data_symbols or ()),
        asset_class=config.market_data_asset_class,
        interval_seconds=float(interval),
        window_seconds=float(window) if window else None,
        run_id=run_id,
        persist_snapshots=bool(getattr(config, "metrics_enable_snapshots", False)),
    )


def parse_initial_positions(value: object | None) -> list[Position]:
    """Parse configured initial positions into typed portfolio positions."""
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


def parse_initial_cash(value: object | None) -> float:
    """Parse configured initial cash, treating missing/empty as zero."""
    if value is None or value == "":
        return 0.0
    return float(value)


def resolve_portfolio_source(config: Config, config_snapshot: Mapping[str, object] | None) -> str:
    """Resolve whether live portfolio state should come from DB or broker."""
    typed_source = getattr(config, "trader_service_portfolio_source", "")
    if typed_source:
        return str(typed_source).strip().lower()
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


def resolve_notify_channel(channel: str | None) -> NotifyChannelResolution:
    """Validate a Postgres NOTIFY channel name with a safe fallback."""
    if not channel:
        return NotifyChannelResolution(channel="market_data", valid=True)
    if not _CHANNEL_RE.match(channel):
        return NotifyChannelResolution(channel="market_data", valid=False)
    return NotifyChannelResolution(channel=channel, valid=True)
