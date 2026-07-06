"""Pure tests for market-data quality summary builders."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from trader.market_data.queries import BarQuery
from trader.market_data.quality_summary import summarize_bar_quality_from_timestamps


def test_summarize_bar_quality_from_timestamps_reports_missing_gaps_and_symbols() -> None:
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


def test_summarize_bar_quality_from_timestamps_dedupes_and_builds_stable_report_id() -> None:
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
