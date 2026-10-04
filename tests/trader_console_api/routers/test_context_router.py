"""Contracts for the first Console screen's configured context.

Subject: Context transport, service wiring and the public scope response.
Level: In-process application contract without lifespan startup.
Collaborators: Real FastAPI app, ContextService and Pydantic models; a pool factory that must not run.
Guarantees: Context uses server configuration, preserves missing labels and exposes no credentials or principal.
Non-goals: Database startup/readiness, frontend rendering and deployment authentication.
"""

import pytest
from fastapi.testclient import TestClient

from trader_console_api import ConsoleApiSettings, ConsoleScope, create_app


@pytest.mark.parametrize(
    ("environment", "label", "binding"),
    [
        ("paper", "Paper A", "configured"),
        ("paper", None, "configured"),
        ("backtest", None, "not_applicable"),
        ("synthetic_demo", None, "not_applicable"),
    ],
)
def test_context_preserves_configured_identity_without_querying_storage(
    environment: str,
    label: str | None,
    binding: str,
) -> None:
    """Return the exact public scope even when no account label or broker binding applies."""
    values = {
        "TRADER_CONSOLE_DATABASE_URL": "postgresql://secret:password@private-db/store",
        "TRADER_CONSOLE_SCOPE_ID": "local",
        "TRADER_CONSOLE_SCOPE_ENVIRONMENT": environment,
    }
    if label is not None:
        values["TRADER_CONSOLE_BROKER_ACCOUNT_DISPLAY_LABEL"] = label
    settings = ConsoleApiSettings.from_environment(values)

    def unexpected_pool(_settings: ConsoleApiSettings) -> None:
        pytest.fail("context must not open a database pool")

    app = create_app(settings, pool_factory=unexpected_pool)
    # No context manager: startup admission is covered by the lifecycle tests.
    client = TestClient(app)
    response = client.get(
        "/api/context",
        params={"scope_id": "other"},
        headers={"X-Account-ID": "other", "X-User-ID": "other"},
    )
    expected = {
        "scope_id": "local",
        "display_name": "local",
        "environment": environment,
        "data_source_kind": "postgresql",
        "isolation_kind": "isolated_database",
        "broker_account_display_label": label,
        "broker_account_binding": binding,
        "presentation_timezone": "UTC",
    }
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == expected
    assert ConsoleScope.model_validate_json(response.content) == settings.scope
    assert app.state.context_service.context() is settings.scope


def test_context_router_delegates_to_its_service() -> None:
    """Use the service result rather than retrieving configuration in the HTTP handler."""
    from fastapi import FastAPI
    from trader_console_api.routers import context_router

    scope = ConsoleScope.model_validate(
        {
            "scope_id": "demo",
            "display_name": "Demo",
            "environment": "synthetic_demo",
            "broker_account_binding": "not_applicable",
        }
    )

    class RecordingService:
        calls = 0

        def context(self) -> ConsoleScope:
            self.calls += 1
            return scope

    service = RecordingService()
    app = FastAPI()
    app.state.context_service = service
    app.include_router(context_router)
    assert TestClient(app).get("/api/context").json() == scope.model_dump(mode="json")
    assert service.calls == 1
