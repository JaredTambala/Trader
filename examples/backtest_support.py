"""Shared helpers for example backtest wrappers."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime

from trader.backtest import BacktestAssumptions, build_backtest_assumptions


def parse_datetime(value: str) -> datetime:
    """Parse ISO-like datetimes into UTC-aware values."""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def assumptions_from_backtest_config(
    backtest_cfg: Mapping[str, object] | None,
) -> BacktestAssumptions:
    """Build backtest assumptions from a wrapper config section."""
    backtest_cfg = backtest_cfg or {}
    assumptions_cfg = backtest_cfg.get("assumptions")
    if assumptions_cfg is None:
        return BacktestAssumptions()
    if not isinstance(assumptions_cfg, Mapping):
        raise ValueError("backtest.assumptions must be a mapping")
    return build_backtest_assumptions(assumptions_cfg)
