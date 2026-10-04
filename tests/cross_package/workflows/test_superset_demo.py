"""Real local Superset trial checks; disabled unless explicitly requested.

Subject: Superset metadata registration and database-enforced Trader read access.
Level: Multi-process Docker/PostgreSQL/HTTP integration.
Collaborators: Real pinned Superset, two PostgreSQL containers, producer installer and HTTP API.
Guarantees: Correct initialization order, repeatable fixture, retained metadata, MCP-created chart assets and
single-run backtest dashboard filters, PostgreSQL/Superset row reconciliation, preview and denied writes/DDL.
Non-goals: Superset adoption, remote deployment, or production IAM.
"""

import os
from pathlib import Path
import secrets
import socket
from uuid import uuid4

import httpx
import psycopg
import pytest

from examples.superset_demo.database import check_access
from examples.superset_demo.backtest_fixtures import fixture_summary, generate_fixtures
from examples.superset_demo.runtime import DemoStack
from examples.superset_demo.smoke import check_preview


pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        os.environ.get("SUPERSET_DEMO_TESTS") != "1",
        reason="Set SUPERSET_DEMO_TESTS=1 to provision the test-owned Superset stack",
    ),
]


def _free_port() -> int:
    # Stay below Docker Desktop's reserved dynamic host-port range.
    for _ in range(100):
        port = 20000 + secrets.randbelow(10000)
        with socket.socket() as listener:
            try:
                listener.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise RuntimeError("No available loopback port for the Superset test")


def test_isolated_superset_preview_and_reader_permissions(tmp_path: Path) -> None:
    """Initialize from empty metadata, reinitialize and restart without losing the preview or grants."""
    database_port = _free_port()
    ui_port = _free_port()
    mcp_port = _free_port()
    while ui_port in {database_port, mcp_port}:
        ui_port = _free_port()
    while mcp_port in {database_port, ui_port}:
        mcp_port = _free_port()
    stack = DemoStack(
        state_directory=tmp_path,
        project=f"trader-superset-test-{uuid4().hex[:12]}",
        database_port=database_port,
        ui_port=ui_port,
        mcp_port=mcp_port,
    )
    try:
        stack.up()
        check_access(stack)
        dataset_id = check_preview(stack)
        stack.compose("stop", "trader")
        with pytest.raises((httpx.HTTPError, psycopg.Error, RuntimeError)):
            check_preview(stack)
        stack.compose("up", "-d", "--wait", "trader")
        assert check_preview(stack) == dataset_id
        stack.up()
        check_access(stack)
        assert check_preview(stack) == dataset_id
        stack.restart()
        assert check_preview(stack) == dataset_id
        stack.down()
        # No installer: a surviving login and preview must come from retained metadata.
        stack.compose("up", "-d", "--wait", "trader", "metadata", "web")
        assert check_preview(stack) == dataset_id
    finally:
        stack.down(remove_test_volumes=True)


def test_backtest_fixtures_are_generated_by_trader_hot_path(tmp_path: Path) -> None:
    """Populate disposable review cases through BacktestRunner and repeat safely."""
    database_port = _free_port()
    ui_port = _free_port()
    mcp_port = _free_port()
    while ui_port in {database_port, mcp_port}:
        ui_port = _free_port()
    while mcp_port in {database_port, ui_port}:
        mcp_port = _free_port()
    stack = DemoStack(
        state_directory=tmp_path,
        project=f"trader-superset-test-{uuid4().hex[:12]}",
        database_port=database_port,
        ui_port=ui_port,
        mcp_port=mcp_port,
    )
    try:
        stack.up()
        first = generate_fixtures(stack)
        second = generate_fixtures(stack)
        assert first == second == {
            "complete_drawdown": 6,
            "zero_trade": 4,
            "multi_symbol": 8,
            "partial_run": 2,
            "missing_mark": 3,
            "failed_run": 0,
        }
        summary = fixture_summary(stack)
        assert {row["status"] for row in summary} == {"completed", "partial", "failed"}
        assert len(summary) == 6
        check_preview(stack)
        with psycopg.connect(stack.dsn()) as connection:
            assert connection.execute(
                "SELECT count(*) FROM stock_bar_events WHERE source = 'superset-demo'"
            ).fetchone() == (3,)
            assert connection.execute(
                "SELECT count(*) FROM crypto_bar_events WHERE source = 'superset-backtest-fixture'"
            ).fetchone()[0] > 0
    finally:
        stack.down(remove_test_volumes=True)
