"""Bootstrap and exercise only the dedicated loopback Console demo database."""

from contextlib import contextmanager
from collections.abc import Iterator

import psycopg
from psycopg.conninfo import make_conninfo
from pydantic import SecretStr

from trader.event_store.console_read_contract import install_console_read_contract
from trader.event_store.schema import POSTGRES_SCHEMA_STATEMENTS
from trader_console_api import (
    BrokerAccountBinding,
    ConsoleApiSettings,
    ConsoleEnvironment,
    ConsoleScope,
)


DATABASE_NAME = "trader_console_demo"
DATABASE_USER = "console_demo"


def demo_dsn(port: int = 55432) -> str:
    """Return a fixed local demo connection; never consume general PG settings."""
    if isinstance(port, bool) or not 1024 <= port <= 65535:
        raise ValueError("demo database port must be between 1024 and 65535")
    return make_conninfo(
        host="127.0.0.1",
        port=port,
        dbname=DATABASE_NAME,
        user=DATABASE_USER,
        password="console_demo_local",
        connect_timeout=3,
    )


@contextmanager
def demo_connection(port: int = 55432) -> Iterator[psycopg.Connection]:
    """Verify the dedicated database/user before allowing demo-only changes."""
    with psycopg.connect(demo_dsn(port)) as connection:
        identity = connection.execute(
            "SELECT current_database(), session_user"
        ).fetchone()
        if identity != (DATABASE_NAME, DATABASE_USER):
            raise RuntimeError("Refusing to modify a database outside the Console demo")
        yield connection


def bootstrap(port: int = 55432) -> None:
    """Idempotently install producer schemas without inserting or deleting trading data."""
    with demo_connection(port) as connection:
        for statement in POSTGRES_SCHEMA_STATEMENTS:
            connection.execute(statement)
        install_console_read_contract(connection)


def break_schema(port: int = 55432) -> None:
    """Remove only demo compatibility metadata to exercise failed readiness.

    Restore using ``restore_schema``. Source tables and recorded evidence stay intact.
    """
    with demo_connection(port) as connection:
        connection.execute(
            "DELETE FROM console_read.contract_versions WHERE contract_name = %s",
            ("trader_console",),
        )


def restore_schema(port: int = 55432) -> None:
    """Restore demo compatibility using the canonical producer installer."""
    with demo_connection(port) as connection:
        install_console_read_contract(connection)


def api_settings(port: int = 55432) -> ConsoleApiSettings:
    """Configure synthetic context independently of shell account/DSN variables."""
    return ConsoleApiSettings(
        database_url=SecretStr(demo_dsn(port)),
        scope=ConsoleScope(
            scope_id="console-demo",
            display_name="Local Console demo",
            environment=ConsoleEnvironment.SYNTHETIC_DEMO,
            broker_account_binding=BrokerAccountBinding.NOT_APPLICABLE,
        ),
    )
