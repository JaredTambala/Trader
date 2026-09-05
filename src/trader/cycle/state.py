"""Event-store read helpers for decision-cycle state."""

from __future__ import annotations

from datetime import datetime
import logging
from typing import Mapping, Sequence

from ..config import Config
from ..event_store import EventStore
from ..market_data import MarketDataEvent
from .market_data import (
    _build_recent_market_data_query,
    _market_data_event_table_name,
    _row_to_market_event,
)
from .order_state import _dedupe_latest_order_event_rows, _latest_order_events_query
from .readiness import _normalize_timestamp


logger = logging.getLogger(__name__)


def _load_latest_order_events(event_store: EventStore) -> Sequence[Mapping[str, object]]:
    """Load the latest local order state for risk-context open-order checks."""
    connection = getattr(event_store, "connection", lambda: None)()
    if connection is None:
        return []
    query = _latest_order_events_query()
    try:
        if hasattr(connection, "cursor"):
            with connection.cursor() as cursor:
                cursor.execute(query)
                rows = cursor.fetchall()
        else:
            rows = connection.execute(query).fetchall()
    except Exception as exc:
        logger.warning("Risk context order query failed: %s", exc)
        return []
    return _dedupe_latest_order_event_rows(rows or [])


def _load_halt_flag(event_store: EventStore) -> bool:
    """Read the operator halt flag used to block non-backtest trading."""
    connection = getattr(event_store, "connection", lambda: None)()
    if connection is None:
        return False
    query = "SELECT value FROM config_kv WHERE key = 'halt' LIMIT 1"
    try:
        if hasattr(connection, "cursor"):
            with connection.cursor() as cursor:
                cursor.execute(query)
                row = cursor.fetchone()
        else:
            row = connection.execute(query).fetchone()
    except Exception as exc:
        logger.warning("Risk context halt query failed: %s", exc)
        return False
    if not row:
        return False
    value = str(row[0]).strip().lower()
    return value in {"1", "true", "yes", "y", "on"}


def _load_recent_market_data(
    event_store: EventStore,
    config: Config,
    as_of_ts: datetime | None = None,
) -> Sequence[MarketDataEvent]:
    """Load the most recent stored bar for each configured symbol."""
    if not config.market_data_symbols:
        logger.warning("No symbols configured for market data lookup")
        return []

    asset_class = config.market_data_asset_class.lower()
    table = _market_data_event_table_name(asset_class)
    timeframe = config.strategy_timeframe
    connection = getattr(event_store, "connection", lambda: None)()
    if connection is None:
        logger.warning("Market data lookup skipped; event store has no connection")
        return []

    if as_of_ts is not None:
        as_of_ts = _normalize_timestamp(as_of_ts)

    events: list[MarketDataEvent] = []
    if hasattr(connection, "cursor"):
        with connection.cursor() as cursor:
            for symbol in config.market_data_symbols:
                lookup = _build_recent_market_data_query(
                    table=table,
                    symbol=symbol,
                    timeframe=timeframe,
                    as_of_ts=as_of_ts,
                )
                cursor.execute(lookup.sql, list(lookup.params))
                row = cursor.fetchone()
                if row is None:
                    continue
                events.append(_row_to_market_event(asset_class, symbol.upper(), timeframe, row))
    else:
        logger.warning("Market data lookup skipped; unsupported connection type")
    logger.info("Loaded recent market data from event store count=%s", len(events))
    return events


__all__ = []
