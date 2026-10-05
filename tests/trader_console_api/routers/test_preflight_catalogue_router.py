"""HTTP contracts for catalogue discovery and backtest preflight.

Subject: FastAPI transport for allowlisted profile metadata and validation results.
Level: In-process router tests.
Collaborators: Fake catalogue/preflight services and Pydantic response contracts.
Guarantees: The router returns typed catalogue data, invalid drafts remain 200 preflight results, and outages use the stable 503 envelope.
Non-goals: Database coverage SQL, profile builder behavior, frontend authoring, or worker execution.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from uuid import uuid4

from trader_console_api.contracts import (
    BacktestCatalogueResponse,
    BacktestPreflightResponse,
)
from trader_console_api.routers.catalogue import (
    get_catalogue_service,
    get_preflight_service,
    router,
)
from trader_console_api.services.catalogue import CatalogueDatabaseUnavailable


class _CatalogueService:
    """Fake catalogue service for HTTP response tests."""

    def describe(self) -> BacktestCatalogueResponse:
        """Return an empty but typed catalogue fixture."""
        return BacktestCatalogueResponse(
            catalogue_version="standard-1",
            strategy_profiles=(),
            risk_profiles=(),
        )


class _PreflightService:
    """Fake preflight service for HTTP response tests."""

    def __init__(self, result: BacktestPreflightResponse | Exception) -> None:
        self.result = result

    async def preflight(self, _draft: object) -> BacktestPreflightResponse:
        """Return a configured result or raise the configured outage."""
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def _app(preflight: object) -> FastAPI:
    """Compose the isolated catalogue router with dependency overrides."""
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_catalogue_service] = lambda: _CatalogueService()
    app.dependency_overrides[get_preflight_service] = lambda: preflight
    return app


def test_catalogue_route_returns_versioned_profile_shape() -> None:
    """Expose typed profile collections without allowing caller-selected code."""
    response = TestClient(_app(_PreflightService(_result()))).get("/api/backtests/catalogue")

    assert response.status_code == 200
    assert response.json()["catalogue_version"] == "standard-1"
    assert response.json()["strategy_profiles"] == []


def test_preflight_route_returns_invalid_result_without_queueing() -> None:
    """Return validation findings as a typed result rather than creating execution state."""
    response = TestClient(_app(_PreflightService(_result(valid=False)))).post(
        "/api/backtests/preflight",
        json={
            "strategy_profile_id": "unknown",
            "asset_class": "crypto",
            "symbols": ["BTC/USD"],
            "timeframe": "1Min",
            "start": "2026-01-01T00:00:00Z",
            "end": "2026-01-01T01:00:00Z",
            "data_scope": _scope_payload(),
        },
    )

    assert response.status_code == 200
    assert response.json()["valid"] is False


def test_preflight_route_maps_database_outage_to_stable_503() -> None:
    """Keep coverage database loss distinct from a rejected definition."""
    response = TestClient(_app(_PreflightService(CatalogueDatabaseUnavailable("database")))).post(
        "/api/backtests/preflight",
        json={
            "strategy_profile_id": "noop",
            "asset_class": "crypto",
            "symbols": ["BTC/USD"],
            "timeframe": "1Min",
            "start": "2026-01-01T00:00:00Z",
            "end": "2026-01-01T01:00:00Z",
            "data_scope": _scope_payload(),
        },
    )

    assert response.status_code == 503


def _result(*, valid: bool = True) -> BacktestPreflightResponse:
    """Build a compact preflight response fixture."""
    return BacktestPreflightResponse(valid=valid, catalogue_version="standard-1")


def _scope_payload() -> dict[str, object]:
    """Return the exact saved-scope handoff required by authoring preflight."""
    return {
        "saved_scope_id": str(uuid4()), "fingerprint": "a" * 64,
        "asset_class": "crypto", "symbols": ["BTC/USD"], "universe": None,
        "timeframe": "1Min", "interval": "1Min",
        "start": "2026-01-01T00:00:00Z", "end": "2026-01-01T01:00:00Z",
        "source_policy": {"provider": "fixture", "source": "fixture", "allow_fallback": False},
        "manifest_artifact_id": "manifest-1", "quality_artifact_id": "quality-1",
        "evidence_status": "active", "evidence_reason": None,
    }
