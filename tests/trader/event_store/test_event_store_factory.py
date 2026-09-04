"""Contracts for normalizing configuration and constructing event-store adapters.

Subject: Backend selection, Postgres settings, buffer settings, and invalid factory configuration.
Level: Deterministic configuration-boundary unit contracts.
Collaborators: Real factory/configuration helpers, simple namespace inputs, and no-op store values.
Guarantees: Runtime configuration maps to explicit adapter settings and unsupported choices fail clearly.
Non-goals: Opening Postgres connections, exercising buffers, environment loading, or event persistence.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from trader.event_store import NoOpEventStore
from trader.event_store.factory import build_event_store
from trader.event_store.factory_config import resolve_event_store_factory_config


def test_resolve_event_store_factory_config_normalizes_postgres_settings() -> None:
    """Ensure factory config copies Postgres and buffer values from runtime config."""
    config = SimpleNamespace(
        event_store="postgres",
        pg_dsn="",
        pg_host="localhost",
        pg_port=5432,
        pg_db="trader",
        pg_user="postgres",
        pg_password="secret",
        buffered_event_store=True,
        buffer_flush_interval_ms=100,
        buffer_max_batch_size=50,
        buffer_max_queue_size=1000,
        buffer_block_on_full=False,
    )

    settings = resolve_event_store_factory_config(config)

    assert settings.backend == "postgres"
    assert settings.postgres.kwargs() == {
        "dsn": None,
        "host": "localhost",
        "port": 5432,
        "dbname": "trader",
        "user": "postgres",
        "password": "secret",
    }
    assert settings.buffer.enabled is True
    assert settings.buffer.flush_interval_ms == 100
    assert settings.buffer.max_batch_size == 50
    assert settings.buffer.max_queue_size == 1000
    assert settings.buffer.block_on_full is False


def test_resolve_event_store_factory_config_uses_defaults() -> None:
    """Ensure absent optional config values resolve to current factory defaults."""
    settings = resolve_event_store_factory_config(SimpleNamespace())

    assert settings.backend == "postgres"
    assert settings.postgres.kwargs() == {
        "dsn": None,
        "host": None,
        "port": None,
        "dbname": None,
        "user": None,
        "password": None,
    }
    assert settings.buffer.enabled is False
    assert settings.buffer.flush_interval_ms == 250
    assert settings.buffer.max_batch_size == 500
    assert settings.buffer.max_queue_size == 10000
    assert settings.buffer.block_on_full is True


def test_build_event_store_returns_noop_without_postgres_dependency() -> None:
    """Ensure the no-op backend can be constructed without importing Postgres support."""
    assert isinstance(
        build_event_store(SimpleNamespace(event_store="noop")), NoOpEventStore
    )
    assert isinstance(
        build_event_store(SimpleNamespace(event_store="none")), NoOpEventStore
    )


def test_build_event_store_rejects_unknown_backend() -> None:
    """Ensure unsupported backends fail with a clear error."""
    with pytest.raises(ValueError, match="Unsupported event store: sqlite"):
        build_event_store(SimpleNamespace(event_store="sqlite"))
