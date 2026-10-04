"""Contracts for resource HTTP transport.

Subject: Resource route status and error envelopes.
Level: In-process FastAPI transport.
Collaborators: Fake application service; no database or browser.
Guarantees: Public typed resources expose stable 404/503 responses.
Non-goals: Repository SQL and PostgreSQL compatibility admission.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from trader_console_api.contracts import BarsResponse, PageInfo, RiskDecision, RiskDecisionsResponse
from trader_console_api.routers.resources import get_resource_service, router


class _Service:
    def __init__(self) -> None:
        self.bar_calls: list[dict[str, object]] = []

    async def bars(self, **_kwargs: object) -> BarsResponse:
        self.bar_calls.append(_kwargs)
        return BarsResponse(items=(), page=PageInfo(limit=1000, offset=0, total=0, has_more=False))

    async def run_detail(self, **_kwargs: object) -> None:
        return None

    async def risk_decisions(self, **_kwargs: object) -> RiskDecisionsResponse:
        return RiskDecisionsResponse(
            items=(
                RiskDecision(
                    risk_decision_id="riskdec-1",
                    composition_fingerprint="fingerprint",
                    run_id="run-1",
                    cycle_id="cycle-1",
                    decision_ts="2026-01-01T00:00:00Z",
                    manager_id="max_orders_per_run",
                    manager_type="trader_standard.risk.MaxOrdersPerRunRiskManager",
                    manager_position=0,
                    outcome="rejected",
                    reason_code="limit_exceeded",
                    before_qty=0.2,
                ),
            ),
            page=PageInfo(limit=25, offset=0, total=1, has_more=False),
        )


class _MissingRiskService(_Service):
    """Service double returning no published run for trace lookup."""

    async def risk_decisions(self, **_kwargs: object) -> None:
        """Represent an unknown canonical run."""
        return None


def _app(service: object) -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_resource_service] = lambda: service
    return app


def test_run_not_found_is_a_stable_error() -> None:
    """Report absent runs without conflating them with a database outage."""
    response = TestClient(_app(_Service())).get("/api/runs/missing")
    assert response.status_code == 404
    assert response.json()["code"] == "run_not_found"


def test_bar_response_is_typed_and_empty_is_valid() -> None:
    """Allow an empty data slice while retaining explicit pagination evidence."""
    service = _Service()
    response = TestClient(_app(service)).get("/api/market-data/bars?symbol=AAPL&limit=50000")
    assert response.status_code == 200
    assert response.json()["page"]["total"] == 0
    assert service.bar_calls[0]["limit"] == 50000


def test_bar_limit_rejects_values_above_the_50k_window() -> None:
    """Keep oversized chart windows outside the API contract."""
    response = TestClient(_app(_Service())).get("/api/market-data/bars?symbol=AAPL&limit=50001")
    assert response.status_code == 422


def test_risk_decisions_route_exposes_typed_filters_and_page() -> None:
    """Return a bounded manager trace through the public read contract."""
    response = TestClient(_app(_Service())).get(
        "/api/runs/run-1/risk-decisions?manager_id=max_orders_per_run&outcome=rejected&limit=25"
    )

    assert response.status_code == 200
    assert response.json()["items"][0]["reason_code"] == "limit_exceeded"
    assert response.json()["page"] == {"limit": 25, "offset": 0, "total": 1, "has_more": False}


def test_risk_decisions_route_rejects_unknown_outcomes() -> None:
    """Keep trace filtering inside the allowlisted outcome vocabulary."""
    response = TestClient(_app(_Service())).get("/api/runs/run-1/risk-decisions?outcome=blocked")

    assert response.status_code == 422


def test_risk_decisions_route_preserves_unknown_run_as_404() -> None:
    """Do not confuse an absent run with an empty risk trace."""
    response = TestClient(_app(_MissingRiskService())).get("/api/runs/missing/risk-decisions")

    assert response.status_code == 404
    assert response.json()["code"] == "run_not_found"
