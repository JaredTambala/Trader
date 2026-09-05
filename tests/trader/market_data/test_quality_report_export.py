"""Contract tests for core market-data quality report identity and export.

Subject: Stable quality-report generation and JSON-file materialization from normalized configuration.
Level: In-process contract with a temporary filesystem boundary.
Collaborators: Real core quality functions, a no-op event store selected by config, and a temporary path.
Guarantees: Equivalent inputs yield one report identity and the reported evidence can be written to disk.
Non-goals: Research quality envelopes, real stored bars, Postgres, provider calls, or gap-detection detail.
"""

from __future__ import annotations

from pathlib import Path

from trader.market_data.quality import run_data_quality, write_data_quality_report


def test_data_quality_returns_stable_report_id(tmp_path: Path) -> None:
    """Equivalent quality requests produce the same identity and an exported report file."""
    config_data = {
        "runtime": {"mode": "once"},
        "strategy": {"id": "demo", "timeframe": "1Min"},
        "broker": {"type": "noop"},
        "market_data": {"source": "noop", "asset_class": "stocks", "symbols": ["DEMO"]},
        "database": {"event_store": "noop"},
        "data_quality": {
            "symbols": ["DEMO"],
            "asset_class": "stocks",
            "timeframe": "1Min",
        },
    }

    first = run_data_quality(config_data)
    second = run_data_quality(config_data)
    output = write_data_quality_report(first, tmp_path / "quality.json")

    assert first["report_id"] == second["report_id"]
    assert first["summaries"] == [
        {
            "symbol": "DEMO",
            "total_bars": 0,
            "missing_gaps": 0,
            "expected_gaps": 0,
            "max_gap_seconds": None,
        }
    ]
    assert output.exists()
