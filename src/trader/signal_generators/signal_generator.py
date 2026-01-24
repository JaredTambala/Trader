"""Signal generator interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Mapping, Sequence

from trader.signals import Signal


class SignalGenerator(ABC):
    """Produces computed signal values for symbols given market/portfolio data."""

    @property
    @abstractmethod
    def signals(self) -> Sequence[Signal]:
        """Signals computed by this generator."""

    @property
    def supports_symbol_generation(self) -> bool:
        """Whether this generator can compute per-symbol signals incrementally."""
        return False

    @abstractmethod
    def generate(
        self,
        *,
        as_of_ts: datetime | None = None,
        run_id: str | None = None,
        cycle_id: str | None = None,
    ) -> Mapping[str, Mapping[str, float]]:
        """Compute signal values for the configured symbol set.

        Args:
            as_of_ts: Optional timestamp cutoff for historical/backtest runs.
            run_id: Optional run identifier for telemetry logging.
            cycle_id: Optional cycle identifier for telemetry logging.

        Returns:
            Mapping of symbol -> {signal_name: signal_value}.
        """

    def generate_for_symbol(
        self,
        symbol: str,
        *,
        as_of_ts: datetime | None = None,
        run_id: str | None = None,
        cycle_id: str | None = None,
    ) -> Mapping[str, float] | None:
        """Compute signal values for a single symbol."""
        raise NotImplementedError("Per-symbol generation not supported")
