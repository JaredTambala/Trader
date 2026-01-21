"""Single execution cycle entry point."""

from __future__ import annotations

from dataclasses import dataclass
from dotenv import load_dotenv
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Sequence

from .broker import Broker, NoOpBroker
from .config import Config, load_config
from .data import EventStore, build_event_store
from .identifiers import deterministic_run_id
from .alpaca_market_data import AlpacaMarketDataSource
from .market_data import (
    MarketDataEvent,
    MarketDataIngestor,
    MarketDataSource,
    NoOpMarketDataSource,
)
from .risk import RiskManager, NoOpRiskManager
from .strategy import Strategy, NoOpStrategy


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CycleResult:
    run_id: str
    status: str


def run_cycle(
    event_store: EventStore | None = None,
    strategy: Strategy | None = None,
    risk_manager: RiskManager | None = None,
    broker: Broker | None = None,
    config: Config | None = None,
    decision_ts: datetime | None = None,
    market_data_source: MarketDataSource | None = None,
) -> CycleResult:
    """Execute a cycle and record run events.

    Args:
        event_store: Optional event store; defaults to DuckDB-backed store.
        strategy: Strategy used to generate signals.
        risk_manager: Risk manager applied to candidate orders.
        broker: Broker used to submit orders.
        config: Optional Config object; defaults to environment config.
        decision_ts: Optional decision timestamp for deterministic run IDs.
        market_data_source: Optional market data source override.

    Returns:
        CycleResult describing the run outcome.

    Raises:
        Exception: Propagates any unexpected errors after recording a failed run.
    """
    config = config or load_config()
    strategy = strategy or NoOpStrategy()
    risk_manager = risk_manager or NoOpRiskManager()
    broker = broker or NoOpBroker()

    owns_event_store = False
    if event_store is None:
        if config.event_store.lower() == "duckdb":
            db_path = Path(config.db_path)
            db_path.parent.mkdir(parents=True, exist_ok=True)
        event_store = build_event_store(config)
        owns_event_store = True

    if market_data_source is None:
        market_data_source = _build_market_data_source(config)

    decision_ts = decision_ts or datetime.now(timezone.utc)
    if decision_ts.tzinfo is None:
        decision_ts = decision_ts.replace(tzinfo=timezone.utc)

    run_id = deterministic_run_id(config.strategy_id, decision_ts)
    started_at = datetime.now(timezone.utc)

    try:
        event_store.record_run_start(
            run_id=run_id,
            strategy_id=config.strategy_id,
            mode=config.mode,
            decision_ts=decision_ts,
            started_at=started_at,
        )
        with event_store.transaction():
            market_data_events = MarketDataIngestor(event_store, market_data_source).ingest()
            should_skip = _should_skip_trading(
                market_data_events,
                datetime.now(timezone.utc),
                config.market_data_max_age_seconds,
            )

            if should_skip:
                logger.warning("Skipping trading due to missing or stale market data")
            else:
                signals = list(strategy.generate_signals())
                validated_orders = risk_manager.validate(signals)
                broker.submit_orders(validated_orders)

            finished_at = datetime.now(timezone.utc)
            event_store.record_run_finish(
                run_id=run_id,
                strategy_id=config.strategy_id,
                mode=config.mode,
                decision_ts=decision_ts,
                started_at=started_at,
                finished_at=finished_at,
                status="success",
                error_message=None,
            )
    except Exception as exc:
        finished_at = datetime.now(timezone.utc)
        event_store.record_run_finish(
            run_id=run_id,
            strategy_id=config.strategy_id,
            mode=config.mode,
            decision_ts=decision_ts,
            started_at=started_at,
            finished_at=finished_at,
            status="failed",
            error_message=str(exc),
        )
        raise
    finally:
        if owns_event_store:
            event_store.close()

    logger.info("Completed cycle", extra={"run_id": run_id})
    return CycleResult(run_id=run_id, status="success")


def _build_market_data_source(config: Config) -> MarketDataSource:
    """Construct the market data source based on configuration.

    Args:
        config: Loaded configuration values.

    Returns:
        A MarketDataSource instance.

    Raises:
        None.
    """
    source_name = config.market_data_source.lower()
    if source_name in {"", "noop"}:
        return NoOpMarketDataSource()

    if source_name == "alpaca":
        if not config.market_data_symbols:
            logger.warning("MARKET_DATA_SYMBOLS is empty; skipping market data ingestion")
            return NoOpMarketDataSource()
        asset_class = config.market_data_asset_class.lower()
        if asset_class not in {"stocks", "stock", "crypto", "cryptocurrency"}:
            logger.warning("Unknown MARKET_DATA_ASSET_CLASS; skipping market data ingestion", extra={"asset_class": asset_class})
            return NoOpMarketDataSource()
        if asset_class in {"stocks", "stock"} and (not config.alpaca_api_key or not config.alpaca_secret_key):
            logger.warning("Alpaca credentials missing; skipping market data ingestion")
            return NoOpMarketDataSource()
        return AlpacaMarketDataSource(
            api_key=config.alpaca_api_key,
            secret_key=config.alpaca_secret_key,
            base_url=config.alpaca_data_base_url,
            symbols=config.market_data_symbols,
            asset_class=asset_class,
            stock_feed=config.market_data_stock_feed,
        )

    logger.warning("Unknown MARKET_DATA_SOURCE; skipping market data ingestion", extra={"source": source_name})
    return NoOpMarketDataSource()


def _should_skip_trading(
    market_data_events: Sequence[MarketDataEvent],
    now: datetime,
    max_age_seconds: int,
) -> bool:
    """Decide whether to skip trading based on market data freshness.

    Args:
        market_data_events: Events collected from ingestion.
        now: Current timestamp for staleness comparison.
        max_age_seconds: Maximum allowed staleness in seconds.

    Returns:
        True if trading should be skipped, otherwise False.

    Raises:
        ValueError: If max_age_seconds is negative.
    """
    if max_age_seconds < 0:
        raise ValueError("max_age_seconds must be non-negative")
    if not market_data_events:
        return True

    latest_ts = max(_normalize_timestamp(event.ts) for event in market_data_events)
    return now - latest_ts > timedelta(seconds=max_age_seconds)


def _normalize_timestamp(timestamp: datetime) -> datetime:
    """Normalize timestamps to timezone-aware UTC.

    Args:
        timestamp: Input timestamp.

    Returns:
        UTC-aware datetime.

    Raises:
        None.
    """
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(timezone.utc)

def _log_startup_env() -> None:
    """Log relevant environment variables for startup diagnostics.

    Sensitive values are masked to avoid leaking credentials.
    """
    keys = [
        "MODE",
        "STRATEGY_ID",
        "DB_PATH",
        "EVENT_STORE",
        "MARKET_DATA_SOURCE",
        "MARKET_DATA_ASSET_CLASS",
        "MARKET_DATA_STOCK_FEED",
        "MARKET_DATA_SYMBOLS",
        "MARKET_DATA_MAX_AGE_SECONDS",
        "ALPACA_API_KEY",
        "ALPACA_SECRET_KEY",
        "ALPACA_DATA_BASE_URL",
        "ALPACA_BASE_URL",
        "PG_DSN",
        "PG_HOST",
        "PG_PORT",
        "PG_DB",
        "PG_USER",
        "PG_PASSWORD",
    ]
    masked = {
        key: _mask_secret(os.getenv(key))
        if key in {"ALPACA_API_KEY", "ALPACA_SECRET_KEY", "PG_PASSWORD"}
        else os.getenv(key, "<unset>")
        for key in keys
    }
    formatted = ", ".join(f"{key}={value}" for key, value in masked.items())
    logger.info("Startup environment: %s", formatted)


def _mask_secret(value: str | None) -> str:
    """Mask secret values for logging.

    Args:
        value: Secret string or None.

    Returns:
        Masked secret string.
    """
    if not value:
        return "<unset>"
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}***{value[-4:]}"


def main() -> None:
    """Module entry point for running a single cycle.

    Raises:
        Exception: Propagates unexpected errors from run_cycle.
    """
    load_dotenv(".env")
    logging.basicConfig(level=logging.INFO)
    _log_startup_env()
    result = run_cycle()
    logger.info("Cycle complete", extra={"run_id": result.run_id, "status": result.status})


if __name__ == "__main__":
    main()
