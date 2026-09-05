"""Runtime broker construction helpers."""

from __future__ import annotations

from ..broker import AlpacaPaperBroker, Broker, InternalPaperBroker, NoOpBroker
from ..config import Config
from ..event_store import EventStore

__all__ = ["build_runtime_broker"]


def build_runtime_broker(config: Config, event_store: EventStore) -> Broker:
    """Construct one broker instance for the lifetime of a trader service."""
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
            base_url=config.alpaca_base_url,
            event_store=event_store,
        )
    return NoOpBroker()
