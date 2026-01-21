"""Configuration loader for the trading system."""

from __future__ import annotations

from dataclasses import dataclass
import os


def _parse_symbols(raw: str) -> tuple[str, ...]:
    """Parse a comma-delimited symbol list into normalized tickers.

    Args:
        raw: Comma-separated string of symbols.

    Returns:
        Tuple of uppercased symbols with whitespace removed.

    Raises:
        None.
    """
    symbols = [symbol.strip().upper() for symbol in raw.split(",") if symbol.strip()]
    return tuple(symbols)


@dataclass(frozen=True)
class Config:
    """Typed configuration values for a trading cycle.

    Attributes:
        mode: Execution mode (once/loop/realtime).
        strategy_id: Identifier for the active strategy version.
        db_path: Path to the DuckDB event store.
        event_store: Event store backend (duckdb/postgres).
        market_data_source: Source identifier for market data ingestion.
        market_data_asset_class: Asset class for market data (stocks/crypto).
        market_data_stock_feed: Alpaca stock data feed (iex/sip).
        market_data_symbols: Universe of symbols to fetch.
        market_data_max_age_seconds: Staleness cutoff before skipping trading.
        alpaca_api_key: Alpaca API key for data access.
        alpaca_secret_key: Alpaca secret key for data access.
        alpaca_data_base_url: Base URL for Alpaca data API.
        pg_dsn: Optional Postgres DSN.
        pg_host: Postgres host.
        pg_port: Postgres port.
        pg_db: Postgres database name.
        pg_user: Postgres user.
        pg_password: Postgres password.
    """
    mode: str
    strategy_id: str
    db_path: str
    event_store: str
    market_data_source: str
    market_data_asset_class: str
    market_data_stock_feed: str
    market_data_symbols: tuple[str, ...]
    market_data_max_age_seconds: int
    alpaca_api_key: str
    alpaca_secret_key: str
    alpaca_data_base_url: str
    pg_dsn: str
    pg_host: str
    pg_port: int
    pg_db: str
    pg_user: str
    pg_password: str


def load_config() -> Config:
    """Load configuration from environment variables with safe defaults.

    Returns:
        Config populated from environment variables.

    Raises:
        ValueError: If numeric environment values cannot be parsed.
    """
    return Config(
        mode=os.getenv("MODE", "once"),
        strategy_id=os.getenv("STRATEGY_ID", "noop"),
        db_path=os.getenv("DB_PATH", "events.duckdb"),
        event_store=os.getenv("EVENT_STORE", "duckdb"),
        market_data_source=os.getenv("MARKET_DATA_SOURCE", "alpaca"),
        market_data_asset_class=os.getenv("MARKET_DATA_ASSET_CLASS", "stocks"),
        market_data_stock_feed=os.getenv("MARKET_DATA_STOCK_FEED", "iex"),
        market_data_symbols=_parse_symbols(os.getenv("MARKET_DATA_SYMBOLS", "")),
        market_data_max_age_seconds=int(os.getenv("MARKET_DATA_MAX_AGE_SECONDS", "60")),
        alpaca_api_key=os.getenv("ALPACA_API_KEY", ""),
        alpaca_secret_key=os.getenv("ALPACA_SECRET_KEY", ""),
        alpaca_data_base_url=os.getenv("ALPACA_DATA_BASE_URL", "https://data.alpaca.markets"),
        pg_dsn=os.getenv("PG_DSN", ""),
        pg_host=os.getenv("PG_HOST", ""),
        pg_port=int(os.getenv("PG_PORT", "5432")),
        pg_db=os.getenv("PG_DB", ""),
        pg_user=os.getenv("PG_USER", ""),
        pg_password=os.getenv("PG_PASSWORD", ""),
    )
