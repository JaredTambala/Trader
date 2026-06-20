"""Compatibility re-export for the public strategy interface.

The canonical implementation lives in :mod:`trader.strategies.base`; this module
keeps ``from trader.strategy import Strategy`` working for external consumers.
"""

from trader.strategies.base import Strategy  # noqa: F401
