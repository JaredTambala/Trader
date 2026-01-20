"""Trading system package for Stage 0 skeleton."""

from .broker import Broker, NoOpBroker
from .config import Config, load_config
from .alpaca_market_data import AlpacaMarketDataSource
from .data import DuckDBEventStore, EventStore, NoOpEventStore
from .identifiers import deterministic_client_order_id, deterministic_run_id
from .market_data import (
    CryptoBarEvent,
    MarketDataEvent,
    MarketDataIngestor,
    MarketDataSource,
    NoOpMarketDataSource,
    StockBarEvent,
    StaticMarketDataSource,
)
from .risk import RiskManager, NoOpRiskManager
from .strategy import Strategy, NoOpStrategy

__all__ = [
    "Broker",
    "NoOpBroker",
    "Config",
    "load_config",
    "EventStore",
    "DuckDBEventStore",
    "NoOpEventStore",
    "deterministic_client_order_id",
    "deterministic_run_id",
    "CryptoBarEvent",
    "MarketDataEvent",
    "MarketDataSource",
    "NoOpMarketDataSource",
    "StaticMarketDataSource",
    "StockBarEvent",
    "AlpacaMarketDataSource",
    "MarketDataIngestor",
    "RiskManager",
    "NoOpRiskManager",
    "Strategy",
    "NoOpStrategy",
]
