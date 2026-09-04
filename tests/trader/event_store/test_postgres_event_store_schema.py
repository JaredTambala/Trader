"""Contracts for the Postgres event-store schema declaration.

Subject: Generic insert allowlists, bar-table identity, and table coverage in schema statements.
Level: Static persistence-schema unit contracts.
Collaborators: Real event-table constants and immutable schema-bootstrap SQL statements.
Guarantees: Every supported generic insert table is declared and bootstrapped, with bars identified explicitly.
Non-goals: Executing DDL, validating columns or indexes, schema migration, or database permissions.
"""

from trader.event_store.schema import (
    BAR_EVENT_TABLES,
    POSTGRES_EVENT_TABLES,
    POSTGRES_SCHEMA_STATEMENTS,
)


def test_postgres_event_tables_cover_runtime_insert_paths() -> None:
    """Ensure generic event insertion accepts the expected runtime tables."""
    assert POSTGRES_EVENT_TABLES == frozenset(
        {
            "runs",
            "trading_sessions",
            "run_events",
            "stock_bar_events",
            "crypto_bar_events",
            "signal_events",
            "indicator_events",
            "prediction_events",
            "order_events",
            "fill_events",
            "position_snapshots",
            "config_kv",
            "metrics_snapshots",
            "experiments",
            "experiment_runs",
        }
    )
    assert BAR_EVENT_TABLES == frozenset({"stock_bar_events", "crypto_bar_events"})
    assert BAR_EVENT_TABLES < POSTGRES_EVENT_TABLES


def test_postgres_schema_statements_include_runtime_tables() -> None:
    """Ensure schema bootstrap DDL contains every generic event table."""
    schema_sql = "\n".join(POSTGRES_SCHEMA_STATEMENTS)

    for table in POSTGRES_EVENT_TABLES:
        assert table in schema_sql
