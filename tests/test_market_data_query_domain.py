from __future__ import annotations

from datetime import datetime, timezone

from trader.market_data.query_domain import (
    BarQuery,
    BarSymbolDiscoveryQuery,
    _bar_record_from_row,
    _discovered_bar_symbol_from_row,
    normalize_bar_query,
    normalize_bar_symbol_discovery_query,
)
from trader.market_data.query_sql import (
    _symbol_discovery_where_clause,
    _symbol_discovery_where_params,
    _where_clause,
    _where_params,
)


def test_normalize_bar_query_canonicalizes_symbols_and_defaults_limit() -> None:
    query = normalize_bar_query(
        BarQuery(
            symbols=(" demo ", "DEMO"),
            asset_class="stock",
            timeframe="1min",
            start=datetime(2026, 1, 20, 12, 0),
            end=datetime(2026, 1, 20, 12, 1, tzinfo=timezone.utc),
            source=" ",
        ),
        default_limit=100,
    )

    assert query.symbols == ("DEMO",)
    assert query.asset_class == "stocks"
    assert query.timeframe == "1Min"
    assert query.start == datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    assert query.source is None
    assert query.limit == 100


def test_bar_query_sql_predicate_and_params_include_optional_source() -> None:
    query = normalize_bar_query(
        BarQuery(
            symbols=("DEMO", "OTHER"),
            asset_class="stocks",
            timeframe="1Min",
            start=datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc),
            end=datetime(2026, 1, 20, 12, 5, tzinfo=timezone.utc),
            source="sample",
        )
    )

    assert _where_clause(query) == (
        "symbol IN (%s, %s) AND COALESCE(timeframe, '1Min') = %s "
        "AND ts >= %s AND ts <= %s AND source = %s"
    )
    assert _where_params(query) == [
        "DEMO",
        "OTHER",
        "1Min",
        datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc),
        datetime(2026, 1, 20, 12, 5, tzinfo=timezone.utc),
        "sample",
    ]


def test_symbol_discovery_normalization_and_sql_params_are_deterministic() -> None:
    query = normalize_bar_symbol_discovery_query(
        BarSymbolDiscoveryQuery(
            asset_class="stocks",
            timeframe="1min",
            source="sample",
            symbols=("demo",),
            query=" em ",
            limit=10,
            include_coverage=True,
        )
    )

    assert query.symbols == ("DEMO",)
    assert query.query == "EM"
    assert _symbol_discovery_where_clause(query) == (
        "1 = 1 AND symbol IN (%s) AND UPPER(symbol) LIKE %s "
        "AND COALESCE(timeframe, '1Min') = %s AND source = %s"
    )
    assert _symbol_discovery_where_params(query) == ["DEMO", "%EM%", "1Min", "sample"]


def test_row_mappers_return_typed_market_data_records() -> None:
    bar = _bar_record_from_row(
        (
            "DEMO",
            "1Min",
            "2026-01-20T12:00:00Z",
            1,
            2,
            0.5,
            1.5,
            100,
            None,
            1.25,
            "sample",
        )
    )
    discovered = _discovered_bar_symbol_from_row(
        ("DEMO", 12, "2026-01-20T12:00:00Z", "2026-01-20T12:11:00Z", "1Min", "sample"),
        include_coverage=True,
    )

    assert bar.ts == datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    assert bar.open == 1.0
    assert bar.trade_count is None
    assert discovered.first_ts == datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    assert discovered.timeframes == ("1Min",)
    assert discovered.sources == ("sample",)
