"""Unit contracts for research data-quality summaries.

Subject: Bounded multi-symbol quality reports, gap evidence, validation, and store availability.
Level: In-process unit contract.
Collaborators: Real Data quality service with shared DuckDB or a no-op event store; no provider.
Guarantees: Reports are stable, complete over full windows, gap-aware, and explicit about invalid input.
Non-goals: Core quality-file export, data loading, Postgres, live catalogues, or research decisions.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from tests.support.duckdb_store import DuckDBEventStore
from trader.event_store import NoOpEventStore
from trader.market_data.sample import load_sample_market_data_csv
from trader_research.data import DataQualityRequest, data_summarize_quality


SAMPLE_CSV = Path("examples/data/demo_stock_1min.csv")


def _request(
    *,
    symbols: tuple[str, ...] = ("DEMO",),
    asset_class: str = "stocks",
    timeframe: str = "1Min",
    start: datetime = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc),
    end: datetime = datetime(2026, 1, 20, 12, 11, tzinfo=timezone.utc),
    source: str | None = None,
) -> DataQualityRequest:
    return DataQualityRequest(
        symbols=symbols,
        asset_class=asset_class,
        timeframe=timeframe,
        start=start,
        end=end,
        source=source,
    )


def test_data_quality_returns_complete_sample_report(tmp_path: Path) -> None:
    """Complete sample coverage produces a stable quality identity with no gap warnings."""
    store = DuckDBEventStore(str(tmp_path / "events.duckdb"))
    load_sample_market_data_csv(store, SAMPLE_CSV)

    first = data_summarize_quality(store, _request())
    second = data_summarize_quality(store, _request())

    assert first.ok is True
    assert first.operation == "data_summarize_quality"
    assert first.warnings == ()
    report = first.to_dict()["data"]["data_quality_report"]
    assert (
        report["report_id"]
        == second.to_dict()["data"]["data_quality_report"]["report_id"]
    )
    assert report["asset_class"] == "stocks"
    assert report["symbols"] == ["DEMO"]
    assert report["timeframe"] == "1Min"
    assert report["total_bars"] == 12
    assert report["missing_gap_count"] == 0
    assert report["expected_gap_count"] == 0
    assert report["session_gap_count"] == 0
    assert report["max_gap_seconds"] == 0
    assert report["complete"] is True
    assert report["symbols_detail"][0]["bar_count"] == 12
    assert report["symbols_detail"][0]["missing_gap_count"] == 0


def test_data_quality_detects_removed_minute_gap(tmp_path: Path) -> None:
    """Removing one expected minute makes the report incomplete and identifies one missing bar."""
    store = DuckDBEventStore(str(tmp_path / "events.duckdb"))
    load_sample_market_data_csv(store, SAMPLE_CSV)
    store.connection().execute(
        "DELETE FROM stock_bar_events WHERE symbol = %s AND ts = %s",
        ["DEMO", datetime(2026, 1, 20, 12, 5, tzinfo=timezone.utc)],
    )

    envelope = data_summarize_quality(store, _request())
    report = envelope.to_dict()["data"]["data_quality_report"]

    assert envelope.ok is True
    assert report["complete"] is False
    assert report["total_bars"] == 11
    assert report["missing_gap_count"] == 1
    assert report["missing_bar_count"] == 1
    assert report["max_gap_seconds"] == 120
    assert "Detected 1 missing gap(s) for DEMO." in envelope.warnings


def test_data_quality_missing_symbol_returns_incomplete_report(tmp_path: Path) -> None:
    """A missing symbol yields bounded zero-coverage evidence and an explicit warning."""
    store = DuckDBEventStore(str(tmp_path / "events.duckdb"))
    load_sample_market_data_csv(store, SAMPLE_CSV)

    envelope = data_summarize_quality(store, _request(symbols=("MISSING",)))
    report = envelope.to_dict()["data"]["data_quality_report"]

    assert envelope.ok is True
    assert report["complete"] is False
    assert report["total_bars"] == 0
    assert report["symbols_detail"][0]["bar_count"] == 0
    assert envelope.warnings[0] == "No bars found for MISSING."


def test_data_quality_summarizes_more_than_default_fetch_limit(tmp_path: Path) -> None:
    """Quality summarization covers the entire requested window beyond ordinary query page limits."""
    store = DuckDBEventStore(str(tmp_path / "events.duckdb"))
    start = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    for index in range(1001):
        ts = start + timedelta(minutes=index)
        store.record_event(
            "stock_bar_events",
            {
                "symbol": "LONG",
                "timeframe": "1Min",
                "ts": ts,
                "ingested_at": ts,
                "open": 1.0,
                "high": 1.0,
                "low": 1.0,
                "close": 1.0,
                "volume": 1.0,
                "trade_count": None,
                "vwap": None,
                "source": "test",
            },
        )

    envelope = data_summarize_quality(
        store,
        _request(
            symbols=("LONG",),
            start=start,
            end=start + timedelta(minutes=1000),
            source="test",
        ),
    )
    report = envelope.to_dict()["data"]["data_quality_report"]

    assert envelope.ok is True
    assert report["total_bars"] == 1001
    assert report["symbols_detail"][0]["bar_count"] == 1001
    assert report["complete"] is True


@pytest.mark.parametrize(
    ("quality_request", "code", "message"),
    [
        (
            _request(symbols=("BAD;DROP",)),
            "validation_error",
            "Invalid bar query symbol",
        ),
        (
            _request(asset_class="forex"),
            "unsupported_instrument_type",
            "does not support instrument type forex",
        ),
        (_request(timeframe="bad"), "validation_error", "Invalid timeframe"),
        (
            _request(
                start=datetime(2026, 1, 20, 12, 11, tzinfo=timezone.utc),
                end=datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc),
            ),
            "validation_error",
            "end must be at or after start",
        ),
    ],
)
def test_data_quality_validation_failures(
    quality_request: DataQualityRequest,
    code: str,
    message: str,
) -> None:
    """Malformed symbols, instruments, timeframes, and windows yield specific validation evidence."""
    envelope = data_summarize_quality(NoOpEventStore(), quality_request)

    assert envelope.ok is False
    assert envelope.errors[0]["code"] == code
    assert message in str(envelope.errors[0]["message"])


def test_data_quality_requires_queryable_connection() -> None:
    """Quality inspection reports a structured failure when no query connection is available."""
    envelope = data_summarize_quality(NoOpEventStore(), _request())

    assert envelope.ok is False
    assert envelope.errors == (
        {
            "code": "event_store_connection_unavailable",
            "message": "Event store does not expose a queryable connection.",
        },
    )
