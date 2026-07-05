"""Pure startup diagnostics helpers for decision cycles."""

from __future__ import annotations

from typing import Mapping

from ..config import Config


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


def _startup_config_log_values(config: Config) -> Mapping[str, object]:
    """Return startup configuration diagnostics with secrets masked."""
    return {
        "mode": config.mode,
        "strategy_type": config.strategy_type,
        "strategy_id": config.strategy_id,
        "strategy_timeframe": config.strategy_timeframe,
        "sma_short_window": config.sma_short_window,
        "sma_long_window": config.sma_long_window,
        "event_store": config.event_store,
        "market_data_source": config.market_data_source,
        "market_data_asset_class": config.market_data_asset_class,
        "market_data_stock_feed": config.market_data_stock_feed,
        "market_data_symbols": ",".join(config.market_data_symbols) or "<unset>",
        "market_data_max_age_seconds": config.market_data_max_age_seconds,
        "alpaca_api_key": _mask_secret(config.alpaca_api_key),
        "alpaca_secret_key": _mask_secret(config.alpaca_secret_key),
        "alpaca_data_base_url": config.alpaca_data_base_url,
        "pg_dsn": _mask_secret(config.pg_dsn),
        "pg_host": config.pg_host or "<unset>",
        "pg_port": config.pg_port,
        "pg_db": config.pg_db or "<unset>",
        "pg_user": config.pg_user or "<unset>",
        "pg_password": _mask_secret(config.pg_password),
    }


__all__ = ["_mask_secret", "_startup_config_log_values"]
