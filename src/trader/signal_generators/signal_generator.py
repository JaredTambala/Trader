"""Signal generator interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Mapping, Sequence

from trader.signals import Signal


class SignalGenerator(ABC):
    """Contract for producing named numeric signals for a symbol universe.

    Generators may support full-universe batch generation, per-symbol
    incremental generation, or both. Returned mappings are keyed by symbol and
    then by signal name so strategies can consume multiple signal families.
    """

    @property
    @abstractmethod
    def signals(self) -> Sequence[Signal]:
        """Return signal definitions evaluated by this generator in deterministic output order."""

    @property
    def supports_symbol_generation(self) -> bool:
        """Report whether `generate_for_symbol` can compute one requested symbol independently for streaming."""
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
        """Compute signal values for one symbol when incremental generation is supported.

        The base implementation raises because most generators only implement
        batch generation. Incremental generators override this and return
        `None` when the requested symbol has no available bar window.
        """
        raise NotImplementedError("Per-symbol generation not supported")
