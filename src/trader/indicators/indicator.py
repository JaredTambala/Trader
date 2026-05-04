"""Indicator primitives for derived time-series values."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime
from typing import Any, Mapping, Sequence

from trader.signals.bar import Bar


@dataclass(frozen=True)
class IndicatorObservation:
    """Auditable latest observation emitted by an indicator.

    `value` may be a scalar, a dataclass, a mapping, or another JSON-serializable object. `scalar_value` preserves the
    existing numeric audit path when an indicator has a single float-like output. `payload` carries structured values
    and metadata for richer indicators such as MACD components or model classifier outputs.
    """

    indicator_name: str
    ts: datetime
    value: object
    payload: Mapping[str, object] = field(default_factory=dict)

    @property
    def scalar_value(self) -> float | None:
        """Return the numeric scalar value when this observation is directly float-like."""
        if isinstance(self.value, bool):
            return None
        if isinstance(self.value, (int, float)):
            return float(self.value)
        return None

    def to_payload(self) -> dict[str, object]:
        """Return a JSON-serializable audit payload."""
        return {
            "indicator_name": self.indicator_name,
            "ts": self.ts.isoformat(),
            "value": _jsonable(self.value),
            "metadata": _jsonable(dict(self.payload)),
        }


class Indicator(ABC):
    """Compute derived values from a sequence of bars."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable indicator name."""

    @property
    @abstractmethod
    def window(self) -> int:
        """Number of bars required to compute the indicator."""

    @abstractmethod
    def compute_series(self, bars: Sequence[Bar]) -> Sequence[object]:
        """Compute a series of indicator values aligned with the bars.

        Args:
            bars: Bars in descending timestamp order (latest first).

        Returns:
            Sequence of indicator values aligned to bar indices (latest first).
        """

    def compute(self, bars: Sequence[Bar]) -> IndicatorObservation | None:
        """Compute the latest auditable observation from a latest-first bar window."""
        if not bars:
            return None
        series = self.compute_series(bars)
        if not series:
            return None
        return IndicatorObservation(
            indicator_name=self.name,
            ts=bars[0].ts,
            value=series[0],
            payload={
                "window": self.window,
                "bars_used": min(len(bars), self.window),
            },
        )


def _jsonable(value: object) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return _jsonable(asdict(value))
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _jsonable(inner) for key, inner in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    return value
