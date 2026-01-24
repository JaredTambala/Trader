"""Compatibility exports for trading primitives.

This module remains as a stable import surface for signal/indicator primitives.
"""

from trader.signals import Bar, Signal, SmaCrossoverSignal
from trader.signal_generators.signal_generator import SignalGenerator
from trader.indicators import Indicator, SmaIndicator

__all__ = [
    "Bar",
    "Signal",
    "SmaCrossoverSignal",
    "SignalGenerator",
    "Indicator",
    "SmaIndicator",
]
