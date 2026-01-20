"""Tests for the trading cycle execution path."""

import os
import subprocess
import sys
from datetime import datetime, timezone

from trader.cycle import run_cycle
from trader.identifiers import deterministic_run_id


def test_run_cycle_returns_success(tmp_path, monkeypatch):
    """Verify run_cycle executes successfully and writes DuckDB state.

    Args:
        tmp_path: Pytest temporary path fixture.
        monkeypatch: Pytest fixture for environment overrides.

    Raises:
        AssertionError: If the cycle fails or DB is not created.
    """
    monkeypatch.setenv("DB_PATH", str(tmp_path / "events.duckdb"))
    monkeypatch.setenv("STRATEGY_ID", "noop")
    monkeypatch.setenv("MARKET_DATA_SOURCE", "noop")
    monkeypatch.setenv("MARKET_DATA_SYMBOLS", "")
    result = run_cycle()
    assert result.status == "success"
    assert result.run_id
    assert (tmp_path / "events.duckdb").exists()


def test_run_cycle_uses_deterministic_run_id(tmp_path, monkeypatch):
    """Ensure deterministic run IDs are used with a fixed decision timestamp.

    Args:
        tmp_path: Pytest temporary path fixture.
        monkeypatch: Pytest fixture for environment overrides.

    Raises:
        AssertionError: If the run ID does not match expectations.
    """
    decision_ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
    monkeypatch.setenv("DB_PATH", str(tmp_path / "events.duckdb"))
    monkeypatch.setenv("STRATEGY_ID", "demo")
    monkeypatch.setenv("MARKET_DATA_SOURCE", "noop")
    monkeypatch.setenv("MARKET_DATA_SYMBOLS", "")
    result = run_cycle(decision_ts=decision_ts)
    assert result.run_id == deterministic_run_id("demo", decision_ts)


def test_module_entrypoint_runs(tmp_path):
    """Smoke test the module entry point.

    Args:
        tmp_path: Pytest temporary path fixture.

    Raises:
        AssertionError: If module execution returns a non-zero code.
    """
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(["src", env.get("PYTHONPATH", "")]).strip(
        os.pathsep
    )
    env["DB_PATH"] = str(tmp_path / "events.duckdb")
    env["MARKET_DATA_SOURCE"] = "noop"
    env["MARKET_DATA_SYMBOLS"] = ""
    completed = subprocess.run(
        [sys.executable, "-m", "trader.cycle"],
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0
