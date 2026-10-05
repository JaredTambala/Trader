"""Contracts for the Console's reproducible first-screen API schema.

Subject: Offline OpenAPI generation and representative public response JSON.
Level: Schema and command-line contract.
Collaborators: Real app/Pydantic schema generation, filesystem and subprocess; no database or frontend.
Guarantees: Checked schema matches the app, documents typed failures and exports without local credentials.
Non-goals: TypeScript generation, browser integration and PostgreSQL behavior.
"""

import json
import os
from pathlib import Path
import subprocess
import sys

from pydantic import ValidationError
import pytest

from trader_console_api.contracts import (
    ConsoleScope,
    LivenessResponse,
    ReadinessResponse,
)
from trader_console_api.openapi import main, render_openapi


ARTIFACT = Path("contracts/trader-console/openapi.json")


def test_checked_schema_matches_registered_routes_and_response_models() -> None:
    """Reject drift between the checked contract artifact and registered routes."""
    rendered = render_openapi()
    assert ARTIFACT.read_text(encoding="utf-8") == rendered
    schema = json.loads(rendered)
    assert set(schema["paths"]) == {
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
        "/api/market-data/evidence",
        "/api/data-scopes",
        "/api/data-scopes/{saved_scope_id}",
            "/api/data-scopes/{saved_scope_id}/revalidate",
            "/api/data-scope-comparisons",
        "/api/experiments",
        "/api/experiments/{experiment_id}/runs",
        "/api/runs/{run_id}",
        "/api/runs/{run_id}/next-decisions",
        "/api/runs/{run_id}/next-decisions/{decision_id}",
        "/api/runs/{run_id}/risk-decisions",
        "/api/experiments/{experiment_id}/comparison-views/preview",
        "/api/experiments/{experiment_id}/comparison-views",
        "/api/experiments/{experiment_id}/comparison-views/{view_id}",
        "/api/paper/runtime",
        "/api/paper/commands",
        "/api/paper/commands/{command_id}",
        "/api/agent-sessions/{session_id}",
        "/api/agent-sessions/{session_id}/commands",
        "/api/agent-sessions/{session_id}/commands/{command_id}",
        "/health/live",
        "/health/ready",
    }
    assert schema["paths"]["/api/context"]["get"]["operationId"] == "get_context"
    for path, code, model in [
        ("/api/context", "200", "ConsoleScope"),
        ("/health/live", "200", "LivenessResponse"),
        ("/health/ready", "200", "ReadinessResponse"),
        ("/health/ready", "503", "ReadinessResponse"),
        ("/api/paper/runtime", "200", "PaperRuntimeOperations"),
        ("/api/paper/commands", "200", "PaperOperatorCommandsResponse"),
    ]:
        response_schema = schema["paths"][path]["get"]["responses"][code]["content"][
            "application/json"
        ]["schema"]
        assert response_schema == {"$ref": f"#/components/schemas/{model}"}
    for forbidden in (
        "database_url",
        "principal_id",
        "unused.invalid",
        "schema-export",
    ):
        assert forbidden not in rendered


def test_export_cli_is_offline_and_environment_independent(tmp_path: Path) -> None:
    """Generate and check the artifact with no Console configuration or credentials present."""
    output = tmp_path / "openapi.json"
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("TRADER_CONSOLE_")
    }
    command = [
        sys.executable,
        "-m",
        "trader_console_api.openapi",
        "--output",
        str(output),
    ]
    subprocess.run(
        command, env=environment, check=True, capture_output=True, timeout=30
    )
    subprocess.run(
        [*command, "--check"],
        env=environment,
        check=True,
        capture_output=True,
        timeout=30,
    )
    assert output.read_text(encoding="utf-8") == render_openapi()


def test_check_mode_rejects_missing_or_stale_artifact(tmp_path: Path) -> None:
    """Fail the drift check without rewriting a missing or outdated checked artifact."""
    output = tmp_path / "openapi.json"
    with pytest.raises(SystemExit) as missing:
        main(["--output", str(output), "--check"])
    assert missing.value.code == 1
    output.write_text("{}\n", encoding="utf-8")
    with pytest.raises(SystemExit) as stale:
        main(["--output", str(output), "--check"])
    assert stale.value.code == 1
    assert output.read_text(encoding="utf-8") == "{}\n"


@pytest.mark.parametrize(
    "issues", [("database_unavailable",), ("database_schema_too_old",)]
)
def test_first_screen_failure_json_preserves_a_reason(issues: tuple[str, ...]) -> None:
    """Keep database loss and incompatible-schema evidence distinct from process liveness."""
    payload = {
        "status": "unavailable",
        "scope_id": "demo",
        "contract_version": None,
        "issues": list(issues),
    }
    response = ReadinessResponse.model_validate_json(json.dumps(payload))
    assert response.model_dump(mode="json") == payload
    assert (
        LivenessResponse.model_validate_json(
            '{"status":"alive","service":"trader-console-api"}'
        ).status
        == "alive"
    )


def test_public_scope_json_rejects_secrets_and_verified_claims() -> None:
    """Do not expand public context to include connection settings or unsupported account verification."""
    payload = {
        "scope_id": "paper",
        "display_name": "Paper",
        "environment": "paper",
        "broker_account_binding": "configured",
    }
    for extra in (
        {"database_url": "secret"},
        {"principal_id": "operator"},
        {"broker_account_binding": "verified"},
    ):
        with pytest.raises(ValidationError):
            ConsoleScope.model_validate_json(json.dumps(payload | extra))
