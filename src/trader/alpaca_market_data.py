"""Compatibility wrapper for Alpaca market-data implementations.

Canonical implementations live in `trader.market_data.alpaca`.
"""

from .market_data.alpaca import AlpacaMarketDataSource, AlpacaRequestSpec

__all__ = ["AlpacaMarketDataSource", "AlpacaRequestSpec"]
