from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from tests.support.duckdb_store import DuckDBEventStore
from trader.data import NoOpEventStore
from trader.market_data_queries import (
    BarQuery,
    EventStoreConnectionUnavailable,
    MarketDataQueryValidationError,
    count_bar_rows,
    count_bar_sources,
    count_bar_symbols,
    fetch_bar_ranges,
    fetch_bars,
    normalize_bar_query,
)
from trader.sample_data import load_sample_market_data_csv


SAMPLE_CSV = Path("examples/data/demo_stock_1min.csv")


def _query(
    *,
    symbols: tuple[str, ...] = ("DEMO",),
    asset_class: str = "stocks",
    timeframe: str = "1Min",
    start: datetime = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc),
    end: datetime = datetime(2026, 1, 20, 12, 11, tzinfo=timezone.utc),
    source: str | None = None,
    limit: int | None = None,
) -> BarQuery:
    return BarQuery(
        symbols=symbols,
        asset_class=asset_class,
        timeframe=timeframe,
        start=start,
        end=end,
        source=source,
        limit=limit,
    )


def test_market_data_queries_count_rows_ranges_sources_and_symbols(tmp_path: Path) -> None:
    store = DuckDBEventStore(str(tmp_path / "events.duckdb"))
    load_sample_market_data_csv(store, SAMPLE_CSV)

    query = _query(symbols=("DEMO", "MISSING"))

    assert [(item.symbol, item.row_count) for item in count_bar_rows(store, query)] == [
        ("DEMO", 12),
        ("MISSING", 0),
    ]
    assert count_bar_symbols(store, query) == 1
    assert [(item.symbol, item.first_ts, item.last_ts) for item in fetch_bar_ranges(store, query)] == [
        (
            "DEMO",
            datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc),
            datetime(2026, 1, 20, 12, 11, tzinfo=timezone.utc),
        ),
        ("MISSING", None, None),
    ]
    assert [(item.symbol, item.source, item.row_count) for item in count_bar_sources(store, query)] == [
        ("DEMO", "sample", 12),
    ]


def test_fetch_bars_is_bounded_and_ordered(tmp_path: Path) -> None:
    store = DuckDBEventStore(str(tmp_path / "events.duckdb"))
    load_sample_market_data_csv(store, SAMPLE_CSV)

    bars = fetch_bars(store, _query(limit=2))

    assert len(bars) == 2
    assert bars[0].symbol == "DEMO"
    assert bars[0].timeframe == "1Min"
    assert bars[0].ts == datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    assert bars[0].open == 9.67
    assert bars[0].source == "sample"
    assert bars[1].ts == datetime(2026, 1, 20, 12, 1, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    ("query", "message"),
    [
        (_query(symbols=()), "at least one symbol"),
        (_query(symbols=tuple(f"SYM{index}" for index in range(21))), "at most 20 symbols"),
        (_query(asset_class="forex"), "Unsupported bar query asset class"),
        (_query(timeframe="bad"), "Invalid timeframe"),
        (
            _query(
                start=datetime(2026, 1, 20, 12, 11, tzinfo=timezone.utc),
                end=datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc),
            ),
            "end must be at or after start",
        ),
        (_query(limit=10_001), "at most 10000 rows"),
    ],
)
def test_normalize_bar_query_validates_inputs(query: BarQuery, message: str) -> None:
    with pytest.raises(MarketDataQueryValidationError, match=message):
        normalize_bar_query(query, default_limit=1_000)


def test_market_data_queries_require_queryable_connection() -> None:
    with pytest.raises(EventStoreConnectionUnavailable, match="queryable connection"):
        count_bar_rows(NoOpEventStore(), _query())
