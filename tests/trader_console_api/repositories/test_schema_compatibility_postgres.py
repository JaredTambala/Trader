"""Guarded PostgreSQL integration for Console database compatibility.

Subject: API compatibility with the installed `console_read` schema through real asynchronous connections.
Level: PostgreSQL adapter integration contract.
Collaborators: Guarded core event store, producer migration, Psycopg pool, and Console compatibility adapters.
Guarantees: Real startup admission succeeds and current query transactions are database-enforced read-only.
Non-goals: Production IAM, request authorization, operational evidence endpoints, and frontend behavior.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator

from pydantic import SecretStr
from psycopg.conninfo import make_conninfo
import pytest

from trader.event_store import PostgresEventStore
from trader.event_store.console_read_contract import (
    install_console_read_contract,
    rollback_console_read_contract,
)
from trader_console_api import (
    BrokerAccountBinding,
    ConsoleApiSettings,
    ConsoleEnvironment,
    ConsoleScope,
)
from trader_console_api.repositories import (
    ConsoleDatabase,
    SchemaCompatibilityRepository,
    create_connection_pool,
)
from trader_console_api.services import HealthService


pytestmark = pytest.mark.postgres


@pytest.fixture
def console_api_settings(
    postgres_event_store: PostgresEventStore,
    postgres_settings: dict[str, object],
) -> Iterator[ConsoleApiSettings]:
    """Install the producer contract and expose guarded settings to API tests."""
    connection = postgres_event_store.connection()
    if connection.execute("SELECT to_regnamespace('console_read')").fetchone() != (
        None,
    ):
        pytest.skip("guarded test database already contains console_read")
    install_console_read_contract(connection)
    try:
        yield ConsoleApiSettings(
            database_url=SecretStr(make_conninfo(**postgres_settings)),
            scope=ConsoleScope(
                scope_id="postgres-contract",
                display_name="Guarded PostgreSQL contract",
                environment=ConsoleEnvironment.PAPER,
                broker_account_binding=BrokerAccountBinding.CONFIGURED,
            ),
            pool_min_size=1,
            pool_max_size=2,
        )
    finally:
        rollback_console_read_contract(connection)


async def _inspect_real_schema(settings: ConsoleApiSettings) -> tuple[bool, str]:
    pool = create_connection_pool(settings)
    await pool.open(wait=True, timeout=settings.pool_open_timeout_seconds)
    database = ConsoleDatabase(pool, settings)
    try:
        inspection = await HealthService(
            scope_id=settings.scope.scope_id,
            compatibility_repository=SchemaCompatibilityRepository(database),
        ).require_startup_readiness()
        async with database.transaction() as connection:
            cursor = await connection.execute("SHOW transaction_read_only")
            transaction_read_only = (await cursor.fetchone())[0]
        return inspection.ready, str(transaction_read_only)
    finally:
        await pool.close(timeout=settings.pool_close_timeout_seconds)


def test_real_pool_admits_installed_schema_inside_current_query_policy(
    console_api_settings: ConsoleApiSettings,
) -> None:
    """Prove the current compatibility query runs under PostgreSQL read-only enforcement."""
    ready, transaction_read_only = asyncio.run(
        _inspect_real_schema(console_api_settings)
    )

    assert ready
    assert transaction_read_only == "on"
