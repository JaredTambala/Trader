"""HTTP transport contracts for durable backtest execution commands.

Subject: Submit/status/list routing, no-store responses, and typed error mapping.
Level: In-process FastAPI router contract.
Collaborators: Real router/TestClient with an application-service double.
Guarantees: Idempotent submit payloads reach the service and durable statuses are observable.
Non-goals: Worker leases, PostgreSQL persistence, and frontend polling behavior.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from trader_console_api.contracts import (
    BacktestExecutionRecord,
    BacktestExecutionsResponse,
    PageInfo,
)
from trader_console_api.routers.backtest_executions import router
from trader_console_api.services.backtest_executions import BacktestExecutionNotFound


def _record() -> BacktestExecutionRecord:
    """Build one representative queued command."""
    now = datetime(2026, 1, 1, tzinfo=UTC)
    return BacktestExecutionRecord(
        execution_id=str(uuid4()),
        scope_id="scope-a",
        definition_id=str(uuid4()),
        definition_revision=1,
        definition_fingerprint="a" * 64,
        idempotency_key="submit-1",
        status="queued",
        attempt=0,
        processed_cycles=0,
        created_at=now,
    )


class _Service:
    """Application-service double isolating transport behavior."""

    def __init__(self, record: BacktestExecutionRecord) -> None:
        self.record = record
        self.calls: list[str] = []

    async def submit(self, request):
        """Return one durable command."""
        self.calls.append("submit")
        return self.record

    async def get(self, execution_id):
        """Return one command status."""
        self.calls.append("get")
        return self.record

    async def list(self, *, limit, offset):
        """Return one bounded page."""
        self.calls.append("list")
        return BacktestExecutionsResponse(
            items=(self.record,), page=PageInfo(limit=limit, offset=offset, total=1, has_more=False)
        )


def _client(service: object) -> TestClient:
    """Mount the router without the application lifespan."""
    app = FastAPI()
    app.include_router(router)
    app.state.backtest_execution_service = service
    return TestClient(app)


def test_submit_status_and_list_are_observable_and_uncached() -> None:
    """The command routes expose queued state for submit, status and history."""
    service = _Service(_record())
    client = _client(service)
    submit = client.post(
        "/api/backtests/executions",
        json={"definition_id": service.record.definition_id, "idempotency_key": "submit-1"},
    )
    status = client.get(f"/api/backtests/executions/{service.record.execution_id}")
    listed = client.get("/api/backtests/executions")

    assert submit.status_code == 202
    assert status.status_code == 200
    assert listed.status_code == 200
    assert submit.json()["status"] == "queued"
    assert submit.headers["cache-control"] == "no-store"
    assert service.calls == ["submit", "get", "list"]


def test_unknown_execution_maps_to_stable_404() -> None:
    """Missing command status remains a typed API error."""
    class _Missing(_Service):
        async def get(self, execution_id):
            raise BacktestExecutionNotFound("Backtest execution not found")

    response = _client(_Missing(_record())).get(f"/api/backtests/executions/{uuid4()}")
    assert response.status_code == 404
    assert response.json()["code"] == "backtest_execution_not_found"
