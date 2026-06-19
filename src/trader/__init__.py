"""Core trading engine package."""

from .broker import AlpacaPaperBroker, Broker, InternalPaperBroker, NoOpBroker
from .config import Config, build_config, load_yaml_config, resolve_log_level
from .market_data.alpaca import AlpacaMarketDataSource
from .event_store import EventStore, NoOpEventStore, PostgresEventStore
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
from .market_data.backfill import MarketDataBackfillRunner
from .market_data.stream import MarketDataStreamRunner
from .backtest import (
    BacktestAssumptions,
    BacktestResult,
    BacktestRunner,
    DataAssumptions,
    FeeAssumptions,
    PositionSummary,
    SlippageAssumptions,
    TradeRecord,
    build_backtest_assumptions,
    export_backtest_equity_curve_csv,
    export_backtest_result_json,
    export_backtest_trades_csv,
    serialize_backtest_result,
)
from .indicators import Indicator, IndicatorObservation
from .portfolio import Portfolio, PortfolioSnapshot, Position
from .risk import RiskContext, RiskManager, RiskPipeline
from .market_data.sample import load_sample_market_data_csv
from .signal_generators import SignalGenerator
from .signals import Bar, Signal
from .strategies import Strategy
from .strategy_metadata import StrategyInfo, resolve_strategy_info
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
    "BacktestAssumptions",
    "PositionSummary",
    "BacktestRunner",
    "FeeAssumptions",
    "SlippageAssumptions",
    "DataAssumptions",
    "TradeRecord",
    "build_backtest_assumptions",
    "serialize_backtest_result",
    "export_backtest_result_json",
    "export_backtest_equity_curve_csv",
    "export_backtest_trades_csv",
    "Indicator",
    "IndicatorObservation",
    "Portfolio",
    "PortfolioSnapshot",
    "Position",
    "StockBarEvent",
    "AlpacaMarketDataSource",
    "MarketDataIngestor",
    "Bar",
    "Signal",
    "SignalGenerator",
    "RiskContext",
    "RiskManager",
    "RiskPipeline",
    "Strategy",
    "StrategyInfo",
    "resolve_strategy_info",
    "TraderService",
    "load_sample_market_data_csv",
]
