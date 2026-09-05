"""Infrastructure adapter builders for decision cycles."""

from __future__ import annotations

import logging

from ..broker import AlpacaPaperBroker, Broker, InternalPaperBroker, NoOpBroker
from ..config import Config
from ..event_store import EventStore, FilteredEventStore
from ..market_data import MarketDataSource, NoOpMarketDataSource
from ..market_data.alpaca import AlpacaMarketDataSource
from .filters import _allowed_cycle_event_types


logger = logging.getLogger(__name__)


def _apply_event_filters(event_store: EventStore, config: Config) -> EventStore:
    """Wrap the event store so optional observability streams respect config.

    Core lifecycle, market-data, config, and metrics events are always allowed.
    Signal, indicator, order, fill, and portfolio events are included only when
    the corresponding logging flags are enabled.
    """
    return FilteredEventStore(
        event_store,
        allowed_event_types=_allowed_cycle_event_types(config),
    )


def _build_market_data_source(config: Config) -> MarketDataSource:
    """Construct the market-data source requested by configuration."""
    source_name = config.market_data_source.lower()
    if source_name in {"", "noop"}:
        return NoOpMarketDataSource()

    if source_name == "alpaca":
        if not config.market_data_symbols:
            logger.warning("MARKET_DATA_SYMBOLS is empty; skipping market data ingestion")
            return NoOpMarketDataSource()
        asset_class = config.market_data_asset_class.lower()
        if asset_class not in {"stocks", "stock", "crypto", "cryptocurrency"}:
            logger.warning(
                "Unknown MARKET_DATA_ASSET_CLASS; skipping market data ingestion",
                extra={"asset_class": asset_class},
            )
            return NoOpMarketDataSource()
        if asset_class in {"stocks", "stock"} and (
            not config.alpaca_api_key or not config.alpaca_secret_key
        ):
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

    logger.warning(
        "Unknown MARKET_DATA_SOURCE; skipping market data ingestion",
        extra={"source": source_name},
    )
    return NoOpMarketDataSource()


def _build_broker(config: Config, event_store: EventStore) -> Broker:
    """Construct the broker implementation requested by configuration."""
    broker_type = (getattr(config, "broker_type", "noop") or "noop").lower()
    if broker_type in {"internal", "paper", "sim"}:
        return InternalPaperBroker(
            reject_probability=getattr(config, "internal_broker_reject_probability", 0.0),
            fill_delay_ms_mean=getattr(config, "internal_broker_fill_delay_ms_mean", 0.0),
            fill_delay_ms_stddev=getattr(config, "internal_broker_fill_delay_ms_stddev", 0.0),
            fill_qty_fraction_mean=getattr(config, "internal_broker_fill_qty_fraction_mean", 1.0),
            fill_qty_fraction_stddev=getattr(config, "internal_broker_fill_qty_fraction_stddev", 0.0),
            rng_seed=getattr(config, "internal_broker_rng_seed", None),
        )
    if broker_type in {"alpaca", "alpaca-paper", "alpaca_paper"}:
        return AlpacaPaperBroker(
            api_key=config.alpaca_api_key,
            secret_key=config.alpaca_secret_key,
            base_url=getattr(config, "alpaca_base_url", None),
            event_store=event_store,
        )
    return NoOpBroker()


__all__ = []
