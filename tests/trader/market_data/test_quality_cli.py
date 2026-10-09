"""CLI boundary contract tests for core data-quality JSON output.

Subject: The standalone data-quality entrypoint's package boundary and output shape.
Level: In-process contract test over the core-owned renderer.
Collaborators: Real core quality CLI renderer and fixed report data; no MCP transport,
research package, database, provider, or filesystem.
Guarantees: The envelope preserves the documented read-only fields and is stable JSON.
Non-goals: Running a configured event-store query or testing MCP envelopes.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys

from trader.market_data.quality_cli import (
    data_quality_cli_envelope,
    render_data_quality_cli_json,
)


def test_data_quality_cli_envelope_is_core_owned_and_stable() -> None:
    """The CLI preserves the read-only envelope without MCP ownership imports."""
    report = {"report_id": "dq_test", "summaries": []}
    generated_at = datetime(2026, 10, 9, 12, 0, tzinfo=timezone.utc)

    envelope = data_quality_cli_envelope(
        report,
        report_path="artifacts/quality.json",
        generated_at=generated_at,
    )
    rendered = render_data_quality_cli_json(
        report,
        report_path="artifacts/quality.json",
        generated_at=generated_at,
    )

    assert envelope["command"] == "data_quality"
    assert envelope["agent_owner"] == "Data Agent"
    assert envelope["side_effect"] == "read_only"
    assert envelope["generated_at"] == "2026-10-09T12:00:00+00:00"
    assert json.loads(rendered) == envelope


def test_cli_entrypoint_has_no_mcp_import() -> None:
    """The operational script remains importable with MCP transport unavailable."""
    source = Path("run_data_quality.py").read_text(encoding="utf-8")
    assert "trader_mcp" not in source


def test_cli_entrypoint_runs_with_core_only_quality_boundary(tmp_path: Path) -> None:
    """The documented JSON command executes against the core no-op store."""
    config = tmp_path / "quality.yaml"
    config.write_text(
        """runtime:\n  mode: once\nstrategy:\n  id: demo\n  timeframe: 1Min\nbroker:\n  type: noop\nmarket_data:\n  source: noop\n  asset_class: stocks\n  symbols: [DEMO]\ndatabase:\n  event_store: noop\ndata_quality:\n  symbols: [DEMO]\n  asset_class: stocks\n  timeframe: 1Min\n""",
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, "run_data_quality.py", str(config), "--json"],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(result.stdout)
    assert payload["command"] == "data_quality"
    assert payload["data"]["report"]["summaries"][0]["symbol"] == "DEMO"
