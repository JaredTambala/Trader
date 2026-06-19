"""Compatibility wrapper for event-store implementations.

Canonical implementations live in `trader.event_store`.
"""

from .event_store import (
    BufferedEventStore,
    BufferedEventStoreSettings,
    EventStore,
    FilteredEventStore,
    NoOpEventStore,
    PostgresEventStore,
    build_event_store,
)

__all__ = [
    "BufferedEventStore",
    "BufferedEventStoreSettings",
    "EventStore",
    "FilteredEventStore",
    "NoOpEventStore",
    "PostgresEventStore",
    "build_event_store",
]
