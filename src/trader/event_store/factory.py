"""Event-store factory helpers."""

from __future__ import annotations

from .base import EventStore, NoOpEventStore
from .buffered import BufferedEventStore
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
    event_store = getattr(config, "event_store", "postgres").lower()
    if event_store in {"noop", "none"}:
        return NoOpEventStore()
    if event_store == "postgres":
        store = PostgresEventStore(
            dsn=getattr(config, "pg_dsn", None) or None,
            host=getattr(config, "pg_host", None) or None,
            port=getattr(config, "pg_port", None) or None,
            dbname=getattr(config, "pg_db", None) or None,
            user=getattr(config, "pg_user", None) or None,
            password=getattr(config, "pg_password", None) or None,
        )
        if getattr(config, "buffered_event_store", False):
            write_store = PostgresEventStore(
                dsn=getattr(config, "pg_dsn", None) or None,
                host=getattr(config, "pg_host", None) or None,
                port=getattr(config, "pg_port", None) or None,
                dbname=getattr(config, "pg_db", None) or None,
                user=getattr(config, "pg_user", None) or None,
                password=getattr(config, "pg_password", None) or None,
            )
            store = BufferedEventStore(
                store,
                write_store=write_store,
                flush_interval_ms=getattr(config, "buffer_flush_interval_ms", 250),
                max_batch_size=getattr(config, "buffer_max_batch_size", 500),
                max_queue_size=getattr(config, "buffer_max_queue_size", 10000),
                block_on_full=getattr(config, "buffer_block_on_full", True),
            )
        return store
    raise ValueError(f"Unsupported event store: {event_store}")
