"""Compatibility aggregator for event-store implementations.

Canonical implementations live in sibling modules under `trader.event_store`.
"""

from .base import EventStore, FilteredEventStore, NoOpEventStore
from .buffered import BufferedEventStore, BufferedEventStoreSettings
from .factory import build_event_store
from .postgres import PostgresEventStore

__all__ = [
    "BufferedEventStore",
    "BufferedEventStoreSettings",
    "EventStore",
    "FilteredEventStore",
    "NoOpEventStore",
    "PostgresEventStore",
    "build_event_store",
]
