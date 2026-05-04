from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
import psycopg

from trader.data import PostgresEventStore


def _postgres_settings_from_env() -> dict[str, object] | None:
    host = os.getenv("PG_HOST")
    port = os.getenv("PG_PORT")
    db = os.getenv("PG_DB")
    user = os.getenv("PG_USER")
    password = os.getenv("PG_PASSWORD")
    if not all([host, port, db, user, password]):
        return None
    return {
        "host": host,
        "port": int(port),
        "dbname": db,
        "user": user,
        "password": password,
    }


def _truncate_runtime_tables(store: PostgresEventStore) -> None:
    connection = store.connection()
    connection.execute(
        """
        TRUNCATE TABLE
            metrics_snapshots,
            position_snapshots,
            fill_events,
            order_events,
            indicator_events,
            signal_events,
            stock_bar_events,
            crypto_bar_events,
            run_events,
            trading_sessions,
            runs,
            experiment_runs,
            experiments,
            config_kv
        """
    )


@pytest.fixture
def postgres_settings() -> dict[str, object]:
    settings = _postgres_settings_from_env()
    if settings is None:
        pytest.skip("Postgres test env vars missing (PG_HOST/PG_PORT/PG_DB/PG_USER/PG_PASSWORD)")
    return settings


@pytest.fixture
def postgres_event_store(postgres_settings: dict[str, object]) -> Iterator[PostgresEventStore]:
    store = PostgresEventStore(**postgres_settings)
    _truncate_runtime_tables(store)
    try:
        yield store
    finally:
        _truncate_runtime_tables(store)
        store.close()


@pytest.fixture
def postgres_listener_connection(postgres_settings: dict[str, object]) -> Iterator[psycopg.Connection]:
    connection = psycopg.connect(**postgres_settings)
    connection.autocommit = True
    try:
        yield connection
    finally:
        connection.close()
