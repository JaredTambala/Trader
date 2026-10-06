"""Contracts for classifying market-data gaps and building quality evidence.

Subject: Asset-aware gap classification and stable, explicitly timestamped quality reports.
Level: Pure domain unit contracts.
Collaborators: Real gap-analysis and report builders with fixed timestamps and summary values.
Guarantees: Session gaps remain distinct from missing data; detail is bounded while totals stay complete;
report identity excludes generation time and includes the retained evidence.
Non-goals: Querying stored bars, exchange-calendar completeness, persistence, or research promotion policy.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json

import pytest

from trader.market_data.quality_gaps import (
    DataQualitySummary,
    analyze_gaps,
)
from trader.market_data.quality_reports import build_quality_report


def test_analyze_gaps_classifies_stock_overnight_gap_as_expected() -> None:
    """Ensure a normal stock session boundary is not reported as missing data."""
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
    """Ensure continuous crypto timestamps expose an equivalent interval as missing data."""
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
    """Ensure generation time remains evidence without changing content-derived report identity."""
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
        "max_gap_samples": 3,
    }

    first = build_quality_report(
        **base_kwargs,
        generated_at=datetime(2026, 1, 20, 12, 2, tzinfo=timezone.utc),
    )
    second = build_quality_report(
        **base_kwargs,
        generated_at=datetime(2026, 1, 20, 12, 3, tzinfo=timezone.utc),
    )
    different_bound = build_quality_report(
        **{**base_kwargs, "max_gap_samples": 4},
        generated_at=datetime(2026, 1, 20, 12, 2, tzinfo=timezone.utc),
    )

    assert first["report_id"] == second["report_id"]
    assert first["report_id"] != different_bound["report_id"]
    assert first["generated_at"] == "2026-01-20T12:02:00+00:00"
    assert first["summaries"][0]["max_gap_seconds"] == 60.0
    assert first["gap_samples"]["DEMO"] == {
        "total_count": 0,
        "retained_count": 0,
        "truncated_count": 0,
        "truncated": False,
        "records": [],
    }


def test_gap_report_binds_detail_while_retaining_complete_counts() -> None:
    """A long gap sequence stays small and states exactly how much detail was omitted."""
    start = datetime(2026, 1, 20, tzinfo=timezone.utc)
    timestamps = [start + timedelta(minutes=5 * index) for index in range(10_001)]
    summary, samples = analyze_gaps(
        symbol="BTC/USD",
        timestamps=timestamps,
        asset_class="crypto",
        timeframe="1Min",
        multipliers={"minute": 2.0},
        sessions={},
        max_gap_samples=3,
    )
    report = build_quality_report(
        symbols=("BTC/USD",),
        asset_class="crypto",
        timeframe="1Min",
        start=start,
        end=timestamps[-1],
        summaries=(summary,),
        gaps_by_symbol={"BTC/USD": samples},
        max_gap_samples=3,
        generated_at=start,
    )

    assert summary.missing_gaps == 10_000
    assert len(samples) == 3
    assert report["gap_samples"]["BTC/USD"]["total_count"] == 10_000
    assert report["gap_samples"]["BTC/USD"]["truncated_count"] == 9_997
    assert report["gap_samples"]["BTC/USD"]["truncated"] is True
    assert len(json.dumps(report)) < 3_000


@pytest.mark.parametrize("sample_limit", [0, 1, 5])
def test_gap_samples_report_exact_small_or_zero_detail(sample_limit: int) -> None:
    """Small reports retain all available gaps unless an explicit lower bound is selected."""
    start = datetime(2026, 1, 20, tzinfo=timezone.utc)
    summary, samples = analyze_gaps(
        symbol="BTC/USD",
        timestamps=(start, start + timedelta(minutes=5)),
        asset_class="crypto",
        timeframe="1Min",
        multipliers={"minute": 2.0},
        sessions={},
        max_gap_samples=sample_limit,
    )
    report = build_quality_report(
        symbols=("BTC/USD",),
        asset_class="crypto",
        timeframe="1Min",
        start=start,
        end=None,
        summaries=(summary,),
        gaps_by_symbol={"BTC/USD": samples},
        max_gap_samples=sample_limit,
        generated_at=start,
    )

    assert report["gap_samples"]["BTC/USD"]["retained_count"] == min(sample_limit, 1)
    assert report["gap_samples"]["BTC/USD"]["truncated_count"] == (1 if sample_limit == 0 else 0)


def test_gap_sample_bound_must_be_nonnegative_integer() -> None:
    """Invalid detail bounds fail before analysis rather than silently changing report evidence."""
    with pytest.raises(ValueError, match="non-negative integer"):
        analyze_gaps(
            symbol="BTC/USD",
            timestamps=(),
            asset_class="crypto",
            timeframe="1Min",
            multipliers={},
            sessions={},
            max_gap_samples=-1,
        )
