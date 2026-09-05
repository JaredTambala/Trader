"""Contracts for summarizing bounded timestamp coverage into quality evidence.

Subject: Per-symbol coverage, missing bars and gaps, warnings, deduplication, and stable report identity.
Level: Pure domain unit contracts.
Collaborators: The real quality-summary builder with normalized bar queries and fixed timestamp mappings.
Guarantees: Complete and incomplete datasets produce deterministic counts, warnings, and content-derived IDs.
Non-goals: Loading bars, exchange-calendar policy, persistence, report attachment, or promotion decisions.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from trader.market_data.queries import BarQuery
from trader.market_data.quality_summary import summarize_bar_quality_from_timestamps


def test_summarize_bar_quality_from_timestamps_reports_missing_gaps_and_symbols() -> (
    None
):
    """Ensure incomplete symbol coverage produces explicit counts and ordered warnings."""
    start = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    query = BarQuery(
        symbols=("AAPL", "MSFT"),
        asset_class="stocks",
        timeframe="1Min",
        start=start,
        end=start + timedelta(minutes=2),
    )

    report, warnings = summarize_bar_quality_from_timestamps(
        query,
        {
            "AAPL": (start, start + timedelta(minutes=2)),
            "MSFT": (),
        },
    )

    assert report["total_bars"] == 2
    assert report["missing_gap_count"] == 1
    assert report["missing_bar_count"] == 1
    assert report["complete"] is False
    assert warnings == (
        "AAPL has 2 bars but expected 3.",
        "Detected 1 missing gap(s) for AAPL.",
        "No bars found for MSFT.",
        "MSFT has 0 bars but expected 3.",
    )


def test_summarize_bar_quality_from_timestamps_dedupes_and_builds_stable_report_id() -> (
    None
):
    """Ensure duplicate timestamps do not alter completeness or stable report identity."""
    start = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    query = BarQuery(
        symbols=(" aapl ",),
        asset_class="us_equity",
        timeframe="1Min",
        start=start,
        end=start + timedelta(minutes=1),
        source="fixture",
    )

    first, first_warnings = summarize_bar_quality_from_timestamps(
        query,
        {"AAPL": (start, start, start + timedelta(minutes=1))},
    )
    second, second_warnings = summarize_bar_quality_from_timestamps(
        query,
        {"AAPL": (start, start + timedelta(minutes=1))},
    )

    assert first["report_id"] == second["report_id"]
    assert first["symbols"] == ["AAPL"]
    assert first["source_filter"] == "fixture"
    assert first["total_bars"] == 2
    assert first["complete"] is True
    assert first_warnings == ()
    assert second_warnings == ()
