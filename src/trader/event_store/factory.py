"""Event-store factory helpers."""

from __future__ import annotations

from .adapters import NoOpEventStore
from .base import EventStore
from .buffered import BufferedEventStore
from .factory_config import resolve_event_store_factory_config
from .postgres import PostgresEventStore


def build_event_store(config: object) -> EventStore:
    """Build the event-store implementation described by runtime config.

    The factory supports `noop`/`none` for dry runs and `postgres` for durable
    runtime state. When buffering is enabled, it creates a read-side Postgres
    store plus a separate write-side store for the background flusher so reads
    and asynchronous writes do not contend on the same connection object.

    Args:
        config: Configuration object with `event_store`, Postgres connection
            fields, and optional buffer settings.

    Returns:
        EventStore implementation ready for runtime use.

    Raises:
        ValueError: If `config.event_store` names an unsupported backend.
        ImportError: If Postgres is requested without the psycopg dependency.
    """
    settings = resolve_event_store_factory_config(config)
    if settings.backend in {"noop", "none"}:
        return NoOpEventStore()
    if settings.backend == "postgres":
        store = PostgresEventStore(**settings.postgres.kwargs())
        if settings.buffer.enabled:
            write_store = PostgresEventStore(**settings.postgres.kwargs())
            store = BufferedEventStore(
                store,
                write_store=write_store,
                flush_interval_ms=settings.buffer.flush_interval_ms,
                max_batch_size=settings.buffer.max_batch_size,
                max_queue_size=settings.buffer.max_queue_size,
                block_on_full=settings.buffer.block_on_full,
            )
        return store
    raise ValueError(f"Unsupported event store: {settings.backend}")
