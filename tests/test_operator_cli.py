"""Smoke tests for the operator CLI."""

from __future__ import annotations

import json
import subprocess
import sys


def test_operator_status_json_is_parseable(tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
runtime:
  mode: loop
strategy:
  id: noop
database:
  event_store: noop
market_data:
  source: noop
  symbols: []
broker:
  type: noop
""",
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, "run_operator.py", str(config_path), "status", "--json"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["health"]["status"] == "degraded"
    assert "no_run" in payload["health"]["reasons"]


def test_operator_health_exit_code_matches_payload(tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
runtime:
  mode: loop
strategy:
  id: noop
database:
  event_store: noop
market_data:
  source: noop
  symbols: []
broker:
  type: noop
""",
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, "run_operator.py", str(config_path), "health", "--json"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["exit_code"] == 1
    assert payload["status"] == "degraded"
