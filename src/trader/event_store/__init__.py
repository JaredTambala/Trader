"""Event-store contracts, implementations, and factory helpers."""

from .adapters import FilteredEventStore, NoOpEventStore
from .base import EventStore
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
