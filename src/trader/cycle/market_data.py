"""Pure market-data value and query helpers for decision cycles."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Mapping, Sequence

from ..market_data import CryptoBarEvent, MarketDataEvent, StockBarEvent
from .readiness import _normalize_timestamp


@dataclass(frozen=True)
class CycleMarketDataPipelineResult:
    """Orders, bars, and prices produced by cycle market-data processing."""

    processed_orders: Sequence[Mapping[str, object]]
    market_data_events: Sequence[MarketDataEvent]
    price_lookup: Mapping[str, float]


@dataclass(frozen=True)
class RecentMarketDataQuery:
    """SQL and parameters for loading one symbol's latest stored market bar."""

    sql: str
    params: tuple[object, ...]


def _empty_market_data_pipeline_result() -> CycleMarketDataPipelineResult:
    """Return an empty market-data processing result."""
    return CycleMarketDataPipelineResult(
        processed_orders=(),
        market_data_events=(),
        price_lookup={},
    )


def _build_price_lookup(events: Sequence[MarketDataEvent]) -> Mapping[str, float]:
    """Return the latest close price per symbol from fetched market events."""
    latest_prices: dict[str, tuple[datetime, float]] = {}
    for event in events:
        timestamp = _normalize_timestamp(event.ts)
        current = latest_prices.get(event.symbol)
        if current is None or timestamp > current[0]:
            latest_prices[event.symbol] = (timestamp, float(event.close))
    return {symbol: price for symbol, (_, price) in latest_prices.items()}


def _market_data_event_table_name(asset_class: str) -> str:
    """Return the persisted market-data table for an asset class."""
    return "crypto_bar_events" if asset_class.lower() in {"crypto", "cryptocurrency"} else "stock_bar_events"


def _build_recent_market_data_query(
    *,
    table: str,
    symbol: str,
    timeframe: str,
    as_of_ts: datetime | None,
) -> RecentMarketDataQuery:
    """Build a latest-bar lookup query for one symbol and optional upper bound."""
    where_clause = "WHERE symbol = %s AND COALESCE(timeframe, '1Min') = %s"
    params: tuple[object, ...] = (symbol.upper(), timeframe)
    if as_of_ts is not None:
        where_clause = f"{where_clause} AND ts <= %s"
        params = (*params, as_of_ts)
    sql = f"""
            SELECT ts, ingested_at, open, high, low, close, volume, trade_count, vwap, source
            FROM {table}
            {where_clause}
            ORDER BY ts DESC
            LIMIT 1
        """
    return RecentMarketDataQuery(sql=sql, params=params)


def _row_to_market_event(
    asset_class: str,
    symbol: str,
    timeframe: str,
    row: Sequence[object],
) -> MarketDataEvent:
    """Convert a stored stock/crypto bar row into the matching event object."""
    common = dict(
        symbol=symbol,
        timeframe=timeframe,
        ts=row[0],
        ingested_at=row[1],
        open=float(row[2]),
        high=float(row[3]),
        low=float(row[4]),
        close=float(row[5]),
        volume=float(row[6]),
        trade_count=float(row[7]) if row[7] is not None else None,
        vwap=float(row[8]) if row[8] is not None else None,
        source=str(row[9]) if row[9] is not None else "event_store",
    )
    if asset_class in {"crypto", "cryptocurrency"}:
        return CryptoBarEvent(**common)
    return StockBarEvent(**common)


__all__ = [
    "CycleMarketDataPipelineResult",
    "RecentMarketDataQuery",
]
