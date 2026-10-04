"""Contracts for Console resource service normalization.

Subject: Mapping producer run projections into public summary contracts.
Level: In-process service boundary.
Collaborators: Pydantic response model; no database or HTTP transport.
Guarantees: Producer-only columns do not break the closed summary contract.
Non-goals: SQL selection, persistence, or frontend rendering.
"""

from datetime import datetime, timezone

from trader_console_api.services.resources import _run_summary


def test_run_summary_discards_producer_only_run_columns() -> None:
    """Allow ``runs.*`` repository rows to reach the typed summary safely."""
    summary = _run_summary(
        {
            "experiment_run_id": "er-1",
            "experiment_id": "exp-1",
            "run_id": "run-1",
            "status": "completed",
            "created_at": datetime(2026, 9, 28, tzinfo=timezone.utc),
            "symbols": ["BTC/USD"],
            "error_message": None,
            "artifact_dir": "/tmp/backtest",
        }
    )

    assert summary.run_id == "run-1"
    assert summary.symbols == ("BTC/USD",)
