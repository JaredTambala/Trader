"""Test-owned process orchestration for the first Console browser journey.

Subject: Next.js → actual FastAPI → dedicated PostgreSQL integration.
Level: Full-stack browser workflow.
Collaborators: Real Docker database, producer bootstrap, API, Next.js and Playwright Chromium.
Guarantees: App-owned browser assertions run against healthy, incompatible and unavailable real services.
Non-goals: Production deployment, trading sessions and the broader foundation qualification.
"""

import os
import subprocess

import pytest

from examples.console_demo.runtime import break_schema, restore_schema
from tests.cross_package.workflows.console_stack import (
    REPO_ROOT,
    api_command,
    database,
    free_port,
    server,
)


pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        os.environ.get("CONSOLE_BROWSER_TESTS") != "1",
        reason="Set CONSOLE_BROWSER_TESTS=1 with a built frontend and Chromium installed",
    ),
]


def test_browser_uses_real_api_and_database() -> None:
    """Run app-owned assertions against isolated real processes, including actual failure states."""
    app = REPO_ROOT / "apps/trader-console"
    api_port, web_port = free_port(), free_port()
    origin = f"http://127.0.0.1:{web_port}"
    environment = dict(
        os.environ,
        TRADER_CONSOLE_API_ORIGIN=f"http://127.0.0.1:{api_port}",
        CONSOLE_TEST_WEB_ORIGIN=origin,
        CONSOLE_TEST_STACK="1",
    )
    # Rewrites are captured at build time, so build against this test's API origin.
    subprocess.run(
        ["npm", "run", "build"], cwd=app, env=environment, check=True, timeout=180
    )

    def browser(scenario: str) -> None:
        subprocess.run(
            ["npm", "run", "test:e2e", "--", "--output", f"test-results/{scenario}"],
            cwd=app,
            env=dict(environment, CONSOLE_TEST_SCENARIO=scenario),
            check=True,
            timeout=120,
        )

    with database() as (port, compose, database_environment):
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
            origin,
            environment=environment,
            cwd=app,
        ):
            with server(
                api_command(port, api_port), f"http://127.0.0.1:{api_port}/health/ready"
            ):
                browser("healthy")
                break_schema(port)
                browser("schema")
                restore_schema(port)
                subprocess.run(
                    [*compose, "stop", "postgres"],
                    env=database_environment,
                    check=True,
                    timeout=30,
                )
                browser("database")
                subprocess.run(
                    [*compose, "up", "-d", "--wait"],
                    env=database_environment,
                    check=True,
                    timeout=60,
                )
                browser("healthy")
            browser("api")
