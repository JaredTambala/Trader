"""Bootstrap and permission checks restricted to the dedicated synthetic Trader database."""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import psycopg
from psycopg import sql

from trader.event_store.console_read_contract import install_console_read_contract
from trader.event_store.schema import POSTGRES_SCHEMA_STATEMENTS

from .runtime import DATABASE, OWNER, READER, DemoStack, local_secrets


@contextmanager
def owner_connection(stack: DemoStack) -> Iterator[psycopg.Connection]:
    """Verify the connected demo identity before any schema, fixture or grant change."""
    with psycopg.connect(stack.dsn()) as connection:
        if connection.execute("SELECT current_database(), session_user").fetchone() != (DATABASE, OWNER):
            raise RuntimeError("Refusing to modify a database outside the Superset demo")
        yield connection


def bootstrap(stack: DemoStack) -> None:
    """Install producer schemas, three synthetic bars and a single-view reader grant."""
    with owner_connection(stack) as connection:
        for statement in POSTGRES_SCHEMA_STATEMENTS:
            connection.execute(statement)
        install_console_read_contract(connection)
        for index in range(3):
            timestamp = datetime(2026, 1, 5, 14, 30, tzinfo=timezone.utc) + timedelta(minutes=index)
            connection.execute(
                """INSERT INTO public.stock_bar_events
                (symbol, timeframe, ts, ingested_at, open, high, low, close, volume, source)
                VALUES ('DEMO', '1Min', %s, %s, %s, %s, %s, %s, %s, 'superset-demo')
                ON CONFLICT (symbol, timeframe, ts, source) DO NOTHING""",
                (timestamp, timestamp, 100 + index, 102 + index, 99 + index, 101 + index, 1000 + index * 100),
            )
        _configure_reader(connection, local_secrets(stack.state_directory)["READER_PASSWORD"])


def _configure_reader(connection: psycopg.Connection, password: str) -> None:
    if not connection.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (READER,)).fetchone():
        connection.execute(sql.SQL("CREATE ROLE {} LOGIN").format(sql.Identifier(READER)))
    connection.execute(sql.SQL(
        "ALTER ROLE {} NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT PASSWORD {}"
    ).format(sql.Identifier(READER), sql.Literal(password)))
    connection.execute(sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC, {}").format(
        sql.Identifier(DATABASE), sql.Identifier(READER)
    ))
    connection.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
        sql.Identifier(DATABASE), sql.Identifier(READER)
    ))
    connection.execute("REVOKE ALL ON SCHEMA public, console_read FROM PUBLIC, superset_demo_reader")
    connection.execute("REVOKE ALL ON ALL TABLES IN SCHEMA public, console_read FROM PUBLIC, superset_demo_reader")
    connection.execute("GRANT USAGE ON SCHEMA console_read TO superset_demo_reader")
    connection.execute(
        sql.SQL("GRANT SELECT ON {} TO {}").format(
            sql.SQL(", ").join(
                sql.Identifier("console_read", relation)
                for relation in (
                    "stock_bars",
                    "backtest_runs",
                    "backtest_performance",
                    "backtest_exposure",
                    "backtest_equity_curve",
                    "backtest_trades",
                    "backtest_positions",
                    "backtest_assumptions",
                    "backtest_warnings",
                    "backtest_provenance",
                    "signal_lifecycle",
                    "order_lifecycle",
                    "fill_lifecycle",
                    "backtest_evidence_coverage",
                    "backtest_scope",
                    "backtest_comparison_runs",
                    "backtest_comparison_curves",
                )
            ),
            sql.Identifier(READER),
        )
    )
    connection.execute("ALTER ROLE superset_demo_reader SET default_transaction_read_only = on")
    connection.execute("ALTER ROLE superset_demo_reader SET statement_timeout = '15s'")


def check_access(stack: DemoStack) -> None:
    """Prove grants deny writes and DDL even with the session read-only default disabled.

    Mutation probes target only a uniquely named disposable table in this demo.
    The table is removed afterwards; no existing fixture or trading row is changed.
    """
    probe = f"superset_probe_{uuid4().hex}"
    target = sql.Identifier("public", probe)
    with owner_connection(stack) as owner:
        owner.execute(sql.SQL("CREATE TABLE {} (value integer)").format(target))
        owner.execute(sql.SQL("INSERT INTO {} VALUES (1)").format(target))
        owner.commit()
        try:
            with psycopg.connect(stack.dsn(reader=True), autocommit=True) as reader:
                if reader.execute("SELECT current_database(), session_user").fetchone() != (DATABASE, READER):
                    raise RuntimeError("Unexpected reader identity")
                if reader.execute("SELECT count(*) FROM console_read.stock_bars WHERE source = 'superset-demo'").fetchone() != (3,):
                    raise RuntimeError("Synthetic bar fixture is missing or changed")
                reader.execute("SET default_transaction_read_only = off")
                probes = [
                    sql.SQL(statement).format(target) for statement in (
                        "INSERT INTO {} VALUES (2)", "UPDATE {} SET value = 2",
                        "DELETE FROM {}", "TRUNCATE {}", "ALTER TABLE {} ADD COLUMN denied integer",
                        "DROP TABLE {}",
                    )
                ]
                probes.extend([
                    sql.SQL("CREATE TABLE {} (value integer)").format(sql.Identifier("public", probe + "_new")),
                    sql.SQL("CREATE TEMP TABLE {} (value integer)").format(sql.Identifier(probe)),
                    sql.SQL("SELECT * FROM public.stock_bar_events LIMIT 1"),
                    sql.SQL("SELECT * FROM console_read.orders LIMIT 1"),
                    sql.SQL("UPDATE console_read.stock_bars SET volume = volume WHERE false"),
                ])
                for statement in probes:
                    try:
                        reader.execute(statement)
                    except psycopg.errors.InsufficientPrivilege:
                        continue
                    raise RuntimeError("Reader unexpectedly permitted a restricted operation")
        finally:
            owner.execute(sql.SQL("DROP TABLE IF EXISTS {}, {}").format(
                target, sql.Identifier("public", probe + "_new")
            ))
    print("Reader check passed: approved SELECT; restricted reads, writes and DDL denied.")
