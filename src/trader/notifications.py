"""Notification helpers for event-driven trading."""

from __future__ import annotations

import json
import logging
import re
from typing import Mapping

from .data import EventStore


logger = logging.getLogger(__name__)

_CHANNEL_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def notify_market_data(
    event_store: EventStore,
    payload: Mapping[str, object],
    channel: str | None = None,
) -> bool:
    """Send a market-data notification for event-driven trading.

    Args:
        event_store: Event store instance (Postgres required).
        payload: JSON-serializable payload to attach to the notification.
        channel: Optional Postgres notify channel override.

    Returns:
        True if a notification was sent, False otherwise.
    """
    connection = getattr(event_store, "connection", lambda: None)()
    if connection is None or not hasattr(connection, "execute") or not hasattr(connection, "notifies"):
        return False

    channel = _resolve_channel(channel)
    message = json.dumps(payload, default=str)
    try:
        connection.execute("SELECT pg_notify(%s, %s)", [channel, message])
    except Exception as exc:  # pragma: no cover - relies on Postgres availability
        logger.warning("Market data notify failed: %s", exc)
        return False
    return True


def _resolve_channel(channel: str | None) -> str:
    """Handle resolve channel."""
    if not channel:
        channel = "market_data"
    if not _CHANNEL_RE.match(channel):
        logger.warning("Invalid notify channel; falling back to market_data")
        return "market_data"
    return channel
