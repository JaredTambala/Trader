"""Core trading engine package."""

from .broker import AlpacaPaperBroker, Broker, InternalPaperBroker, NoOpBroker
from .config import Config, build_config, load_yaml_config, resolve_log_level
from .alpaca_market_data import AlpacaMarketDataSource
from .data import EventStore, NoOpEventStore, PostgresEventStore
from .identifiers import (
    deterministic_client_order_id,
    deterministic_cycle_id,
    deterministic_run_id,
    deterministic_run_session_id,
)
from .market_data import (
    CryptoBarEvent,
    MarketDataEvent,
    MarketDataIngestor,
    MarketDataSource,
    NoOpMarketDataSource,
    StockBarEvent,
    StaticMarketDataSource,
)
from .market_data_stream import MarketDataStreamRunner
from .market_data_backfill import MarketDataBackfillRunner
from .backtest import BacktestResult, BacktestRunner, PositionSummary
from .portfolio import Portfolio, PortfolioSnapshot, Position
from .risk import (
    HaltRiskManager,
    MaxGrossExposureRiskManager,
    MaxOrdersPerRunRiskManager,
    MaxPositionUsdPerSymbolRiskManager,
    NoOpRiskManager,
    OpenBuyOrderLimitRiskManager,
    RiskManager,
    RiskPipeline,
)
from .strategies import Strategy, NoOpStrategy, RandomStrategy
from .trader_service import TraderService

__all__ = [
    "Broker",
    "AlpacaPaperBroker",
    "InternalPaperBroker",
    "NoOpBroker",
    "Config",
    "build_config",
    "load_yaml_config",
    "resolve_log_level",
    "EventStore",
    "NoOpEventStore",
    "PostgresEventStore",
    "deterministic_client_order_id",
    "deterministic_cycle_id",
    "deterministic_run_id",
    "deterministic_run_session_id",
    "CryptoBarEvent",
    "MarketDataEvent",
    "MarketDataSource",
    "NoOpMarketDataSource",
    "StaticMarketDataSource",
    "MarketDataStreamRunner",
    "MarketDataBackfillRunner",
    "BacktestResult",
    "PositionSummary",
    "BacktestRunner",
    "Portfolio",
    "PortfolioSnapshot",
    "Position",
    "StockBarEvent",
    "AlpacaMarketDataSource",
    "MarketDataIngestor",
    "RiskManager",
    "NoOpRiskManager",
    "RiskPipeline",
    "HaltRiskManager",
    "MaxOrdersPerRunRiskManager",
    "MaxGrossExposureRiskManager",
    "MaxPositionUsdPerSymbolRiskManager",
    "OpenBuyOrderLimitRiskManager",
    "Strategy",
    "NoOpStrategy",
    "RandomStrategy",
    "TraderService",
]
