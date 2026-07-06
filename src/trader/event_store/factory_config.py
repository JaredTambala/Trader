"""Pure configuration normalization for event-store construction."""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "BufferedEventStoreConfig",
    "EventStoreFactoryConfig",
    "PostgresConnectionConfig",
    "resolve_event_store_factory_config",
]


@dataclass(frozen=True)
class PostgresConnectionConfig:
    """Resolved Postgres connection settings for event-store construction."""

    dsn: object | None
    host: object | None
    port: object | None
    dbname: object | None
    user: object | None
    password: object | None

    def kwargs(self) -> dict[str, object | None]:
        """Return keyword arguments accepted by `PostgresEventStore`."""
        return {
            "dsn": self.dsn,
            "host": self.host,
            "port": self.port,
            "dbname": self.dbname,
            "user": self.user,
            "password": self.password,
        }


@dataclass(frozen=True)
class BufferedEventStoreConfig:
    """Resolved buffering settings for `BufferedEventStore`."""

    enabled: bool
    flush_interval_ms: int
    max_batch_size: int
    max_queue_size: int
    block_on_full: bool


@dataclass(frozen=True)
class EventStoreFactoryConfig:
    """Normalized event-store factory decision values."""

    backend: str
    postgres: PostgresConnectionConfig
    buffer: BufferedEventStoreConfig


def resolve_event_store_factory_config(config: object) -> EventStoreFactoryConfig:
    """Return normalized event-store construction settings from runtime config."""
    return EventStoreFactoryConfig(
        backend=getattr(config, "event_store", "postgres").lower(),
        postgres=PostgresConnectionConfig(
            dsn=getattr(config, "pg_dsn", None) or None,
            host=getattr(config, "pg_host", None) or None,
            port=getattr(config, "pg_port", None) or None,
            dbname=getattr(config, "pg_db", None) or None,
            user=getattr(config, "pg_user", None) or None,
            password=getattr(config, "pg_password", None) or None,
        ),
        buffer=BufferedEventStoreConfig(
            enabled=getattr(config, "buffered_event_store", False),
            flush_interval_ms=getattr(config, "buffer_flush_interval_ms", 250),
            max_batch_size=getattr(config, "buffer_max_batch_size", 500),
            max_queue_size=getattr(config, "buffer_max_queue_size", 10000),
            block_on_full=getattr(config, "buffer_block_on_full", True),
        ),
    )
