"""Contracts for the independent Console API lifecycle and health surface.

Subject: FastAPI composition, bounded pool ownership, context and liveness/readiness semantics.
Level: In-process application contract.
Collaborators: Real FastAPI routes and database boundary with an asynchronous recording pool; no PostgreSQL server.
Guarantees: One pool is lifespan-owned, current queries are read-only, startup fails closed, and health claims stay narrow.
Non-goals: Request authorization, trading health, producer migration, and frontend workflow behavior.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
import json
from typing import Any

from fastapi import Request
from fastapi.testclient import TestClient
import psycopg
from psycopg_pool import PoolTimeout
import pytest
from pydantic import SecretStr

from trader_console_api import (
    BrokerAccountBinding,
    ConsoleApiSettings,
    ConsoleEnvironment,
    ConsoleScope,
    TraderPrincipal,
    create_app,
)
from trader_console_api.application import AuthenticationProvider, ConsoleStartupError
from trader_console_api.repositories import EXPECTED_CONTRACT_COLUMNS
from trader_console_api.services import IncompatibleDatabaseSchema


def _settings() -> ConsoleApiSettings:
    return ConsoleApiSettings(
        database_url=SecretStr("postgresql://unused/test"),
        scope=ConsoleScope(
            scope_id="paper-primary",
            display_name="Primary paper account",
            environment=ConsoleEnvironment.PAPER,
            broker_account_binding=BrokerAccountBinding.CONFIGURED,
        ),
        pool_min_size=1,
        pool_max_size=3,
        statement_timeout_ms=1_250,
    )


def _catalog_rows() -> list[tuple[str, str]]:
    return [
        (relation_name, column_name)
        for relation_name, columns in EXPECTED_CONTRACT_COLUMNS.items()
        for column_name in columns
    ]


class _Cursor:
    def __init__(
        self,
        *,
        row: tuple[int, int] | None = None,
        rows: list[tuple[str, str]] | None = None,
    ) -> None:
        self._row = row
        self._rows = rows or []

    async def fetchone(self) -> tuple[int, int] | None:
        return self._row

    async def fetchall(self) -> list[tuple[str, str]]:
        return self._rows


class _RecordingConnection:
    def __init__(
        self,
        pool: _RecordingPool,
        version_row: tuple[int, int] | None,
    ) -> None:
        self._pool = pool
        self._version_row = version_row

    @asynccontextmanager
    async def transaction(self) -> Any:
        self._pool.transactions += 1
        yield

    async def execute(
        self,
        query: str,
        parameters: object | None = None,
    ) -> _Cursor:
        self._pool.queries.append((query, parameters))
        if "FROM console_read.contract_versions" in query:
            return _Cursor(row=self._version_row)
        if "FROM information_schema.columns" in query:
            return _Cursor(rows=_catalog_rows())
        return _Cursor()


class _RecordingPool:
    def __init__(
        self,
        *,
        version_row: tuple[int, int] | None = (1, 1),
        fail_open: bool = False,
        fail_connections_after: int | None = None,
    ) -> None:
        self.version_row = version_row
        self.fail_open = fail_open
        self.fail_connections_after = fail_connections_after
        self.open_calls: list[tuple[bool, float]] = []
        self.close_calls: list[float] = []
        self.connection_calls = 0
        self.transactions = 0
        self.queries: list[tuple[str, object | None]] = []

    async def open(self, wait: bool = False, timeout: float = 30.0) -> None:
        self.open_calls.append((wait, timeout))
        if self.fail_open:
            raise PoolTimeout("test pool timeout")

    async def close(self, timeout: float = 5.0) -> None:
        self.close_calls.append(timeout)

    @asynccontextmanager
    async def connection(self, timeout: float | None = None) -> Any:
        self.connection_calls += 1
        if (
            self.fail_connections_after is not None
            and self.connection_calls > self.fail_connections_after
        ):
            raise psycopg.OperationalError("test connection outage")
        yield _RecordingConnection(self, self.version_row)


class _RecordingAuthenticationProvider(AuthenticationProvider):
    def __init__(self) -> None:
        self.calls = 0

    async def authenticate(self, request: Request) -> TraderPrincipal:
        self.calls += 1
        return TraderPrincipal(principal_id="operator@example.test")


def test_lifespan_owns_one_pool_and_current_probes_use_read_only_transactions() -> None:
    """Open one pool while applying current query policy to each health probe."""
    pool = _RecordingPool()
    factory_calls: list[ConsoleApiSettings] = []

    def pool_factory(settings: ConsoleApiSettings) -> _RecordingPool:
        factory_calls.append(settings)
        return pool

    app = create_app(_settings(), pool_factory=pool_factory)
    with TestClient(app) as client:
        live_response = client.get("/health/live")
        ready_response = client.get("/health/ready")
        context_response = client.get("/api/context")

    assert factory_calls == [_settings()]
    assert pool.open_calls == [(True, 10.0)]
    assert pool.close_calls == [5.0]
    assert pool.transactions == 2
    assert sum(query == "SET TRANSACTION READ ONLY" for query, _ in pool.queries) == 2
    assert live_response.json() == {"status": "alive", "service": "trader-console-api"}
    assert ready_response.json()["status"] == "ready"
    assert live_response.headers["cache-control"] == "no-store"
    assert ready_response.headers["cache-control"] == "no-store"
    assert context_response.json() == _settings().scope.model_dump(mode="json")


def test_incompatible_schema_aborts_startup_and_closes_the_open_pool() -> None:
    """Fail closed before serving requests when compatibility metadata is not admissible."""
    pool = _RecordingPool(version_row=(0, 0))
    app = create_app(_settings(), pool_factory=lambda _settings: pool)

    with pytest.raises(IncompatibleDatabaseSchema, match="database_schema_too_old"):
        with TestClient(app):
            pass

    assert pool.close_calls == [5.0]


def test_liveness_survives_database_outage_while_readiness_returns_unavailable() -> None:
    """Keep process liveness distinct from database readiness after startup."""
    pool = _RecordingPool(fail_connections_after=1)
    app = create_app(_settings(), pool_factory=lambda _settings: pool)

    with TestClient(app) as client:
        live_response = client.get("/health/live")
        ready_response = client.get("/health/ready")
        context_response = client.get("/api/context")
        pool.fail_connections_after = None
        recovered_response = client.get("/health/ready")

    assert live_response.status_code == 200
    assert ready_response.status_code == 503
    assert ready_response.json()["issues"] == ["database_unavailable"]
    assert ready_response.headers["cache-control"] == "no-store"
    assert context_response.status_code == 200
    assert context_response.json() == _settings().scope.model_dump(mode="json")
    assert recovered_response.status_code == 200
    assert recovered_response.json()["status"] == "ready"


def test_pool_open_failure_is_reported_as_a_console_startup_error() -> None:
    """Translate initial pool failure into an actionable service-level startup error."""
    pool = _RecordingPool(fail_open=True)
    app = create_app(_settings(), pool_factory=lambda _settings: pool)

    with pytest.raises(ConsoleStartupError, match="could not open"):
        with TestClient(app):
            pass

    assert pool.close_calls == []


def test_startup_database_outage_is_reported_as_compatibility_inspection_failure() -> None:
    """Explain a database outage during initial admission and still close the opened pool."""
    pool = _RecordingPool(fail_connections_after=0)
    app = create_app(_settings(), pool_factory=lambda _settings: pool)

    with pytest.raises(ConsoleStartupError, match="could not inspect"):
        with TestClient(app):
            pass

    assert pool.close_calls == [5.0]


def test_health_routes_do_not_invoke_or_claim_request_authentication() -> None:
    """Retain the authentication injection seam without inventing Phase Zero authorization behavior."""
    pool = _RecordingPool()
    provider = _RecordingAuthenticationProvider()
    app = create_app(
        _settings(),
        pool_factory=lambda _settings: pool,
        authentication_provider=provider,
    )

    with TestClient(app) as client:
        response = client.get("/health/ready")
        assert client.get("/api/context").status_code == 200

    assert response.status_code == 200
    assert provider.calls == 0
    assert app.state.authentication_provider is provider


def test_openapi_exposes_no_client_database_or_scope_override() -> None:
    """Ensure the scaffold has no request input capable of overriding server scope configuration."""
    pool = _RecordingPool()
    app = create_app(_settings(), pool_factory=lambda _settings: pool)

    with TestClient(app) as client:
        schema = client.get("/openapi.json").json()

        assert set(schema["paths"]) == {
            "/health/live",
            "/health/ready",
            "/api/context",
            "/api/backtests/catalogue",
            "/api/backtests/preflight",
            "/api/backtests/definitions",
            "/api/backtests/definitions/{definition_id}",
            "/api/backtests/definitions/{definition_id}/revisions",
            "/api/backtests/executions",
            "/api/backtests/executions/{execution_id}",
            "/api/market-data/datasets",
            "/api/market-data/bars",
            "/api/experiments",
            "/api/experiments/{experiment_id}/runs",
            "/api/runs/{run_id}",
            "/api/runs/{run_id}/risk-decisions",
            "/api/experiments/{experiment_id}/comparison-views/preview",
            "/api/experiments/{experiment_id}/comparison-views",
            "/api/experiments/{experiment_id}/comparison-views/{view_id}",
            "/api/paper/runtime",
        }
    rendered = json.dumps(schema)
    for forbidden in ("database_url", "postgresql://", "scope_id_override"):
        assert forbidden not in rendered
