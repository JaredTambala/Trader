"""Minimal Alpaca stock bars probe using alpaca-py."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os

from alpaca.data.enums import DataFeed
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit


def _get_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


def main() -> int:
    api_key = _get_env("ALPACA_API_KEY")
    secret_key = _get_env("ALPACA_SECRET_KEY")
    base_url = os.getenv("ALPACA_DATA_BASE_URL", "https://data.alpaca.markets")
    symbols = os.getenv("MARKET_DATA_SYMBOLS", "AAPL").split(",")
    symbols = [symbol.strip().upper() for symbol in symbols if symbol.strip()]
    if not symbols:
        raise RuntimeError("MARKET_DATA_SYMBOLS must include at least one symbol")

    feed_value = os.getenv("MARKET_DATA_STOCK_FEED", "iex").strip().lower()
    feed = DataFeed.IEX if feed_value != "sip" else DataFeed.SIP

    lag_minutes = int(os.getenv("MARKET_DATA_STOCK_LAG_MINUTES", "0"))
    end_time = datetime.now(timezone.utc) - timedelta(minutes=lag_minutes)
    start_time = end_time - timedelta(minutes=5)
    client = StockHistoricalDataClient(api_key, secret_key, url_override=base_url)
    request = StockBarsRequest(
        symbol_or_symbols=symbols,
        timeframe=TimeFrame(amount=1, unit=TimeFrameUnit.Minute),
        start=start_time,
        end=end_time,
        limit=5,
        feed=feed,
    )

    response = client.get_stock_bars(request)
    print(response)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
