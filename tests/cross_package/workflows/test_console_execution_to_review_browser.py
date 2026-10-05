"""Browser qualification for a real Console execution-to-review run.

Subject: Next.js review workspace over the real API, worker and PostgreSQL
projection produced by the execution qualification fixture.
Level: Full-stack browser qualification.
Collaborators: Test-owned Docker PostgreSQL, the demo API, a separate worker,
Next.js and Playwright Chromium.
Guarantees: The browser reads the durable run created by the real worker,
shows the qualified scope and review evidence, and records a human decision.
Non-goals: Mocked UI fixtures, funded-live trading, and statistical claims.
"""

from __future__ import annotations

import os
from pathlib import Path
import subprocess

import httpx
import pytest

from examples.console_demo.runtime import bootstrap
from tests.cross_package.workflows.console_stack import (
    REPO_ROOT,
    api_command,
    database,
    free_port,
    server,
)
from tests.cross_package.workflows.test_console_execution_to_review import (
    _config_file,
    _definition_payload,
    _insert_fixture_bars,
    _run_worker,
    _scope_payload,
    _seed_review_artifacts,
    _wait_for_terminal,
)


pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        os.environ.get("CONSOLE_EXECUTION_BROWSER_TESTS") != "1",
        reason="Set CONSOLE_EXECUTION_BROWSER_TESTS=1 with a built frontend and Chromium installed",
    ),
]


def test_browser_reviews_real_worker_execution(tmp_path: Path) -> None:
    """Run the execution fixture through the actual browser application path."""
    app = REPO_ROOT / "apps/trader-console"
    api_port, web_port = free_port(), free_port()
    api_origin = f"http://127.0.0.1:{api_port}"
    web_origin = f"http://127.0.0.1:{web_port}"
    environment = dict(
        os.environ,
        TRADER_CONSOLE_API_ORIGIN=api_origin,
        CONSOLE_TEST_WEB_ORIGIN=web_origin,
        CONSOLE_TEST_STACK="1",
    )
    subprocess.run(
        ["npm", "run", "build"], cwd=app, env=environment, check=True, timeout=180
    )

    with database() as (port, _compose, _database_environment):
        bootstrap(port)
        _insert_fixture_bars(port)
        with server(api_command(port, api_port), f"{api_origin}/health/ready"):
            with httpx.Client(base_url=api_origin, timeout=15) as client:
                scope_response = client.post("/api/data-scopes", json=_scope_payload())
                scope_response.raise_for_status()
                scope = scope_response.json()
                definition_response = client.post(
                    "/api/backtests/definitions", json=_definition_payload(scope)
                )
                definition_response.raise_for_status()
                definition = definition_response.json()
                execution_response = client.post(
                    "/api/backtests/executions",
                    json={
                        "definition_id": definition["definition_id"],
                        "idempotency_key": "qualification-browser-execution-v1",
                    },
                )
                execution_response.raise_for_status()
                queued = execution_response.json()
                worker = _run_worker(_config_file(tmp_path, port), port)
                assert worker.returncode == 0, worker.stderr or worker.stdout
                completed = _wait_for_terminal(client, queued["execution_id"])
                assert completed["status"] == "completed", completed
                run_id = str(completed["run_id"])
                detail_response = client.get(f"/api/runs/{run_id}")
                detail_response.raise_for_status()
                review_fingerprint = detail_response.json()["scope"]["scope_fingerprint"]
                _seed_review_artifacts(port, run_id, review_fingerprint)
                decisions_response = client.get(f"/api/runs/{run_id}/next-decisions")
                assert decisions_response.status_code == 200, decisions_response.text

            with server(
                [
                    "node",
                    "node_modules/next/dist/bin/next",
                    "start",
                    "--hostname",
                    "127.0.0.1",
                    "--port",
                    str(web_port),
                ],
                web_origin,
                environment=environment,
                cwd=app,
            ):
                subprocess.run(
                    [
                        "npm",
                        "run",
                        "test:e2e",
                        "--",
                        "tests/e2e/execution-to-review.spec.ts",
                        "--output",
                        "test-results/execution-to-review",
                    ],
                    cwd=app,
                    env=dict(
                        environment,
                        CONSOLE_TEST_SCENARIO="execution",
                        CONSOLE_TEST_EXECUTION_RUN_ID=run_id,
                    ),
                    check=True,
                    timeout=180,
                )
