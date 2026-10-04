"""Guarded PostgreSQL verification for the Trader Console read contract.

Subject: Installed Console views and direct SQL backtest projections.
Level: PostgreSQL integration contract.
Collaborators: Guarded runtime database, real source tables, and Psycopg connections.
Guarantees: The Console can derive evidence and metrics from persisted runtime rows without a metrics snapshot.
Non-goals: API transaction behavior, deployment authentication, roles, grants, or production IAM policy.
"""

from __future__ import annotations

from typing import Iterator

import pytest

from trader.event_store import PostgresEventStore
from trader.event_store.console_read_contract import (
    CONSOLE_READ_CONTRACT,
    CONSOLE_READ_VERSION_QUERY,
    inspect_console_read_contract,
    install_console_read_contract,
    rollback_console_read_contract,
)


pytestmark = pytest.mark.postgres


@pytest.fixture
def installed_console_read_contract(
    postgres_event_store: PostgresEventStore,
) -> Iterator[PostgresEventStore]:
    """Install and remove the contract using the guarded test database owner."""
    connection = postgres_event_store.connection()
    if connection.execute("SELECT to_regnamespace('console_read')").fetchone() != (None,):
        pytest.skip("guarded test database already contains console_read")
    install_console_read_contract(connection)
    try:
        yield postgres_event_store
    finally:
        rollback_console_read_contract(connection)


def test_console_contract_projects_safe_fields_with_stable_names(
    installed_console_read_contract: PostgresEventStore,
) -> None:
    """Read approved data through stable views while excluded fields remain absent."""
    connection = installed_console_read_contract.connection()
    connection.execute(
        """
        INSERT INTO trading_sessions (
            session_id, strategy_id, status, config_snapshot, mode, symbols
        ) VALUES (%s, %s, %s, %s, %s, %s)
        """,
        ["session_console_contract", "strategy_demo", "running", '{"secret": "not-for-console"}', "paper", ["AAPL"]],
    )
    row = connection.execute(
        """
        SELECT session_id, strategy_id, status, mode, symbols
        FROM console_read.sessions WHERE session_id = %s
        """,
        ["session_console_contract"],
    ).fetchone()
    columns = connection.execute(
        """
        SELECT column_name FROM information_schema.columns
        WHERE table_schema = 'console_read' AND table_name = 'sessions'
        ORDER BY ordinal_position
        """
    ).fetchall()
    assert row == ("session_console_contract", "strategy_demo", "running", "paper", ["AAPL"])
    assert "config_snapshot" not in {column[0] for column in columns}


def test_console_contract_reports_compatible_catalog_and_rolls_back(
    installed_console_read_contract: PostgresEventStore,
) -> None:
    """Verify current metadata and let fixture teardown remove only the read schema."""
    connection = installed_console_read_contract.connection()
    inspection = inspect_console_read_contract(connection)
    version = connection.execute(CONSOLE_READ_VERSION_QUERY, [CONSOLE_READ_CONTRACT]).fetchone()
    assert inspection.ready is True
    assert inspection.issues == ()
    assert version == (8, 1)


def test_console_contract_derives_backtest_evidence_without_metrics_snapshot(
    installed_console_read_contract: PostgresEventStore,
) -> None:
    """Derive trade, equity, performance, and scope rows from normalized runtime evidence."""
    connection = installed_console_read_contract.connection()
    run_id = "console_direct_backtest_run"
    ts = "2026-01-01T00:00:00+00:00"
    fill_ts = "2026-01-01T00:01:00+00:00"
    config = {
        "backtest": {
            "asset_class": "stock", "timeframe": "1Min", "initial_cash": 1000,
            "initial_positions": [],
            "assumptions": {"fill_model": "full_fill", "fees": {"bps": 10}, "slippage": {"bps": 2}},
        },
        "market_data": {"source": "test"},
    }
    connection.execute(
        """
        INSERT INTO runs (run_id, run_type, started_at, finished_at, status, config_snapshot,
                          mode, symbols, timeframe, start_ts, end_ts)
        VALUES (%s, 'backtest', %s, %s, 'success', %s, 'backtest', %s, '1Min', %s, %s)
        """,
        [run_id, ts, fill_ts, config, ["AAPL"], ts, fill_ts],
    )
    connection.execute(
        """
        INSERT INTO experiment_runs (experiment_run_id, experiment_id, run_id, status, created_at,
            finished_at, strategy_id, strategy_name, symbols, asset_class, timeframe, start_ts, end_ts)
        VALUES ('console_direct_experiment_run', 'console_direct_experiment', %s, 'success', %s, %s,
            'direct_strategy', 'direct_strategy', %s, 'stock', '1Min', %s, %s)
        """,
        [run_id, ts, fill_ts, ["AAPL"], ts, fill_ts],
    )
    connection.execute(
        """
        INSERT INTO stock_bar_events (symbol, timeframe, ts, open, high, low, close, volume, source)
        VALUES ('AAPL', '1Min', %s, 100, 101, 99, 100, 10, 'test'),
               ('AAPL', '1Min', %s, 100, 102, 99, 101, 10, 'test')
        """,
        [ts, fill_ts],
    )
    connection.execute(
        """
        INSERT INTO position_snapshots (asof_ts, symbol, qty, avg_price, cash_balance, run_id, cycle_id)
        VALUES (%s, 'AAPL', 0, NULL, 1000, %s, NULL)
        """,
        [ts, run_id],
    )
    connection.execute(
        """
        INSERT INTO order_events (order_event_id, client_order_id, run_id, cycle_id, symbol, side, qty, status, created_at)
        VALUES ('direct-order-event', 'direct-order', %s, 'direct-cycle', 'AAPL', 'buy', 1, 'filled', %s)
        """,
        [run_id, fill_ts],
    )
    connection.execute(
        """
        INSERT INTO fill_events (fill_event_id, client_order_id, run_id, cycle_id, fill_ts, fill_qty,
                                 raw_fill_price, slippage_amount, fee_amount, fill_price)
        VALUES ('direct-fill-event', 'direct-order', %s, 'direct-cycle', %s, 1, 100, 0.02, 0.1, 100.02)
        """,
        [run_id, fill_ts],
    )

    assert connection.execute("SELECT count(*) FROM metrics_snapshots WHERE run_id = %s", [run_id]).fetchone() == (0,)
    trade = connection.execute(
        "SELECT symbol, side, fill_qty, fill_price FROM console_read.backtest_trades WHERE run_id = %s", [run_id]
    ).fetchone()
    scope = connection.execute(
        "SELECT initial_cash, fill_model, fee_bps FROM console_read.backtest_scope WHERE run_id = %s", [run_id]
    ).fetchone()
    performance = connection.execute(
        "SELECT strategy_start_equity, strategy_end_equity, total_fees FROM console_read.backtest_performance WHERE run_id = %s",
        [run_id],
    ).fetchone()
    assert trade == ("AAPL", "buy", 1.0, 100.02)
    assert scope == (1000.0, "full_fill", 10.0)
    assert performance[0] == 1000.0
    assert performance[1] == pytest.approx(1000.88)
    assert performance[2] == pytest.approx(0.1)
