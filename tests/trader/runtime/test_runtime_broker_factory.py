"""Contracts for selecting and constructing the configured runtime broker.

Subject: No-op fallback and internal-paper aliases at the runtime composition boundary.
Level: Deterministic factory unit contracts.
Collaborators: The real broker factory, typed configuration, and a no-op event store.
Guarantees: Supported simulation aliases select the internal broker while unknown choices remain safely no-op.
Non-goals: Alpaca credentials, provider clients, broker submission, persistence, or application startup.
"""

from __future__ import annotations

from trader.broker import InternalPaperBroker, NoOpBroker
from trader.config import Config
from trader.event_store import NoOpEventStore
from trader.runtime.broker_factory import build_runtime_broker


def _config(**overrides: object) -> Config:
    values = {
        "mode": "loop",
        "strategy_type": "noop",
        "strategy_id": "noop",
        "strategy_timeframe": "1Min",
        "sma_short_window": 2,
        "sma_long_window": 3,
        "db_path": ":memory:",
        "event_store": "postgres",
        "market_data_source": "noop",
        "market_data_asset_class": "stocks",
        "market_data_stock_feed": "iex",
        "market_data_symbols": (),
        "market_data_max_age_seconds": 60,
        "alpaca_api_key": "",
        "alpaca_secret_key": "",
        "alpaca_data_base_url": "https://data.alpaca.markets",
        "alpaca_base_url": "https://paper-api.alpaca.markets",
        "pg_dsn": "",
        "pg_host": "",
        "pg_port": 5432,
        "pg_db": "",
        "pg_user": "",
        "pg_password": "",
        "buffered_event_store": False,
        "buffer_flush_interval_ms": 250,
        "buffer_max_batch_size": 500,
        "buffer_max_queue_size": 10000,
        "buffer_block_on_full": True,
        "log_signal_events": True,
        "log_indicator_events": True,
        "log_order_events": True,
        "log_fill_events": True,
        "log_position_snapshots": True,
        "broker_type": "noop",
    }
    values.update(overrides)
    return Config(**values)


def test_build_runtime_broker_returns_noop_for_unknown_or_noop_type() -> None:
    """Ensure unknown and explicit no-op configuration select the safe broker implementation."""
    assert isinstance(build_runtime_broker(_config(), NoOpEventStore()), NoOpBroker)
    assert isinstance(
        build_runtime_broker(_config(broker_type="unknown"), NoOpEventStore()),
        NoOpBroker,
    )


def test_build_runtime_broker_returns_internal_paper_broker_for_sim_aliases() -> None:
    """Ensure every supported simulation alias selects the internal paper broker."""
    assert isinstance(
        build_runtime_broker(_config(broker_type="internal"), NoOpEventStore()),
        InternalPaperBroker,
    )
    assert isinstance(
        build_runtime_broker(_config(broker_type="paper"), NoOpEventStore()),
        InternalPaperBroker,
    )
    assert isinstance(
        build_runtime_broker(_config(broker_type="sim"), NoOpEventStore()),
        InternalPaperBroker,
    )
