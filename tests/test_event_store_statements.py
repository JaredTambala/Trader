"""Tests for Postgres event-store SQL statement contracts."""

from trader.event_store.records import EXPERIMENT_RUN_FIELDS
from trader.event_store.statements import (
    CYCLE_FINISH_SQL,
    CYCLE_START_SQL,
    EXPERIMENT_RUN_FINISH_SQL,
    EXPERIMENT_RUN_START_SQL,
    LIST_EXPERIMENT_RUNS_SQL,
    RUN_SESSION_FINISH_SQL,
    RUN_SESSION_START_SQL,
    TRADING_SESSION_FINISH_SQL,
    TRADING_SESSION_START_SQL,
    UPSERT_EXPERIMENT_SQL,
)


def test_lifecycle_statement_placeholder_counts_match_parameters() -> None:
    """Ensure lifecycle SQL placeholders match PostgresEventStore parameter lists."""
    assert RUN_SESSION_START_SQL.count("%s") == 11
    assert TRADING_SESSION_START_SQL.count("%s") == 11
    assert RUN_SESSION_FINISH_SQL.count("%s") == 12
    assert TRADING_SESSION_FINISH_SQL.count("%s") == 12
    assert CYCLE_START_SQL.count("%s") == 7
    assert CYCLE_FINISH_SQL.count("%s") == 10


def test_experiment_statement_placeholder_counts_match_parameters() -> None:
    """Ensure experiment SQL placeholders match PostgresEventStore parameter lists."""
    assert UPSERT_EXPERIMENT_SQL.count("%s") == 7
    assert EXPERIMENT_RUN_START_SQL.count("%s") == 18
    assert EXPERIMENT_RUN_FINISH_SQL.count("%s") == 11
    assert LIST_EXPERIMENT_RUNS_SQL.count("%s") == 1


def test_list_experiment_runs_query_covers_record_fields() -> None:
    """Ensure list query returns the fields expected by row mapping."""
    for field in EXPERIMENT_RUN_FIELDS:
        assert field in LIST_EXPERIMENT_RUNS_SQL
