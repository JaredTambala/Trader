"""Pure event-filter policy helpers for decision cycles."""

from __future__ import annotations

from ..config import Config


def _allowed_cycle_event_types(config: Config) -> set[str]:
    """Return event types allowed by cycle observability configuration."""
    allowed = {
        "runs",
        "run_events",
        "stock_bar_events",
        "crypto_bar_events",
        "config_kv",
    }
    if config.log_signal_events:
        allowed.add("signal_events")
    if config.log_indicator_events:
        allowed.add("indicator_events")
    if config.log_order_events:
        allowed.add("order_events")
    if config.log_fill_events:
        allowed.add("fill_events")
    if config.log_position_snapshots:
        allowed.add("position_snapshots")
    return allowed


__all__ = ["_allowed_cycle_event_types"]
