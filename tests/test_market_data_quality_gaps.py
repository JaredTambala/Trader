from __future__ import annotations

from datetime import datetime, timedelta, timezone

from trader.market_data.quality_gaps import (
    DataQualitySummary,
    analyze_gaps,
)
from trader.market_data.quality_reports import build_quality_report


def test_analyze_gaps_classifies_stock_overnight_gap_as_expected() -> None:
    timestamps = (
        datetime(2026, 1, 20, 20, 59, tzinfo=timezone.utc),
        datetime(2026, 1, 21, 14, 30, tzinfo=timezone.utc),
    )

    summary, gaps = analyze_gaps(
        symbol="DEMO",
        timestamps=timestamps,
        asset_class="stocks",
        timeframe="1Min",
        multipliers={"minute": 2.0},
        sessions={},
    )

    assert summary.missing_gaps == 0
    assert summary.expected_gaps == 1
    assert gaps[0].reason == "expected_session_gap"


def test_analyze_gaps_classifies_crypto_gap_as_missing_data() -> None:
    timestamps = (
        datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc),
        datetime(2026, 1, 20, 12, 5, tzinfo=timezone.utc),
    )

    summary, gaps = analyze_gaps(
        symbol="BTC/USD",
        timestamps=timestamps,
        asset_class="crypto",
        timeframe="1Min",
        multipliers={"minute": 2.0},
        sessions={},
    )

    assert summary.missing_gaps == 1
    assert summary.expected_gaps == 0
    assert gaps[0].reason == "gap"


def test_build_quality_report_has_stable_id_and_explicit_generated_at() -> None:
    summary = DataQualitySummary(
        symbol="DEMO",
        total_bars=2,
        missing_gaps=0,
        expected_gaps=0,
        max_gap=timedelta(minutes=1),
    )
    base_kwargs = {
        "symbols": ("DEMO",),
        "asset_class": "stocks",
        "timeframe": "1Min",
        "start": datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc),
        "end": datetime(2026, 1, 20, 12, 1, tzinfo=timezone.utc),
        "summaries": (summary,),
        "gaps_by_symbol": {"DEMO": ()},
    }

    first = build_quality_report(
        **base_kwargs,
        generated_at=datetime(2026, 1, 20, 12, 2, tzinfo=timezone.utc),
    )
    second = build_quality_report(
        **base_kwargs,
        generated_at=datetime(2026, 1, 20, 12, 3, tzinfo=timezone.utc),
    )

    assert first["report_id"] == second["report_id"]
    assert first["generated_at"] == "2026-01-20T12:02:00+00:00"
    assert first["summaries"][0]["max_gap_seconds"] == 60.0
