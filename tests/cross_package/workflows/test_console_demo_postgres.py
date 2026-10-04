"""Real PostgreSQL and API lifecycle for a test-owned Console demonstration.

Subject: Producer schema → API context/readiness and failure recovery.
Level: Multi-process PostgreSQL integration.
Collaborators: Real Docker PostgreSQL, core installer and separately launched FastAPI.
Guarantees: Repeatable bootstrap, no trading rows, failed startup, outage and schema recovery.
Non-goals: Broker connectivity, production IAM and browser rendering.
"""

import os
import subprocess

import httpx
import pytest

from examples.console_demo.runtime import (
    bootstrap,
    break_schema,
    demo_connection,
    restore_schema,
)
from tests.cross_package.workflows.console_stack import (
    api_command,
    database,
    free_port,
    server,
)


pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        os.environ.get("CONSOLE_DEMO_TESTS") != "1",
        reason="Set CONSOLE_DEMO_TESTS=1 to provision a test-owned Docker database",
    ),
]


def test_real_demo_bootstrap_failure_and_recovery() -> None:
    """Keep the real API's context honest through schema loss and a stopped database."""
    with database() as (port, compose, environment):
        bootstrap(port)
        with demo_connection(port) as connection:
            assert connection.execute(
                "SELECT count(*) FROM console_read.sessions"
            ).fetchone() == (0,)
            assert connection.execute(
                "SELECT count(*) FROM console_read.orders"
            ).fetchone() == (0,)
        api_port = free_port()
        origin = f"http://127.0.0.1:{api_port}"
        command = api_command(port, api_port)
        with server(command, f"{origin}/health/ready"):
            assert (
                httpx.get(f"{origin}/api/context").json()["environment"]
                == "synthetic_demo"
            )
            break_schema(port)
            assert httpx.get(f"{origin}/health/ready").status_code == 503
            assert httpx.get(f"{origin}/health/live").status_code == 200
            restore_schema(port)
            assert httpx.get(f"{origin}/health/ready").status_code == 200
            subprocess.run(
                [*compose, "stop", "postgres"], env=environment, check=True, timeout=30
            )
            assert httpx.get(f"{origin}/health/ready", timeout=10).status_code == 503
            assert httpx.get(f"{origin}/api/context").status_code == 200
            subprocess.run(
                [*compose, "up", "-d", "--wait"],
                env=environment,
                check=True,
                timeout=60,
            )
            assert httpx.get(f"{origin}/health/ready", timeout=10).status_code == 200
        break_schema(port)
        failed = subprocess.run(command, capture_output=True, text=True, timeout=30)
        assert failed.returncode != 0
        assert "IncompatibleDatabaseSchema" in failed.stderr
        restore_schema(port)
