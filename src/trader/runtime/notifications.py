"""Runtime notification helpers for event-driven trading.

This module contains the Postgres NOTIFY boundary used by market-data ingestion
paths to wake realtime trading loops. It validates channel names and degrades to
no-op behavior when the supplied event store is not backed by Postgres.
"""

from __future__ import annotations

import json
import logging
from typing import Mapping

from ..event_store import EventStore
from .service_config import resolve_notify_channel


logger = logging.getLogger(__name__)


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

    channel_resolution = resolve_notify_channel(channel)
    if not channel_resolution.valid:
        logger.warning("Invalid notify channel; falling back to market_data")
    message = json.dumps(payload, default=str)
    try:
        connection.execute("SELECT pg_notify(%s, %s)", [channel_resolution.channel, message])
    except Exception as exc:  # pragma: no cover - relies on Postgres availability
        logger.warning("Market data notify failed: %s", exc)
        return False
    return True
