"""HTTP contract for the read-only paper-runtime route.

Subject: Paper operations transport and outage behavior.
Level: In-process FastAPI transport.
Collaborators: Service double; no database or broker.
Guarantees: typed response and 503 database envelope.
Non-goals: repository SQL and browser layout.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from trader_console_api.contracts import (
    BrokerAccountBinding, PaperRuntimeOperations,
)
from trader_console_api.routers.paper_runtime import get_paper_runtime_service, router


class _Service:
    async def operations(self) -> PaperRuntimeOperations:
        from datetime import datetime, timezone
        from trader_console_api.contracts import (
            PaperDataFreshness, PaperFills, PaperHaltState, PaperOrders, PaperPortfolio,
            PaperReconciliation, PaperRiskOutcomes, PaperRuntimeHealth, PaperRuntimeSession,
            RuntimeEvidence,
        )
        evidence = RuntimeEvidence(status="unavailable", source="fixture")
        return PaperRuntimeOperations(
            scope_id="paper", generated_at=datetime.now(timezone.utc),
            broker_account_binding=BrokerAccountBinding.CONFIGURED,
            session=PaperRuntimeSession(evidence=evidence),
            health=PaperRuntimeHealth(status="unavailable", checked_at=datetime.now(timezone.utc), evidence=evidence),
            data_freshness=PaperDataFreshness(status="unavailable", checked_at=datetime.now(timezone.utc), evidence=evidence),
            portfolio=PaperPortfolio(evidence=evidence), open_orders=PaperOrders(evidence=evidence),
            fills=PaperFills(evidence=evidence), risk=PaperRiskOutcomes(evidence=evidence),
            reconciliation=PaperReconciliation(status="unavailable", evidence=evidence), halt=PaperHaltState(evidence=evidence),
        )


def test_paper_runtime_is_read_only_typed_response() -> None:
    """Expose operational state without a command method or mutation input."""
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_paper_runtime_service] = _Service
    response = TestClient(app).get("/api/paper/runtime")
    assert response.status_code == 200
    assert response.json()["session"]["evidence"]["status"] == "unavailable"
    assert response.headers["cache-control"] == "no-store"
