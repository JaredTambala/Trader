"""Pure runtime health classification helpers.

Runtime status queries collect evidence from the event store. This module keeps
the deterministic health policy separate from those queries so the operator
classification can be tested without SQL connections, clocks, or stores.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

__all__ = ["RuntimeHealthAssessment", "assess_runtime_health", "evaluate_health"]


@dataclass(frozen=True)
class RuntimeHealthAssessment:
    """Typed runtime health classification for operator status payloads."""

    status: str
    exit_code: int
    reasons: tuple[str, ...]

    def to_record(self) -> dict[str, Any]:
        """Return the JSON-compatible health mapping used by existing callers."""
        return {
            "status": self.status,
            "exit_code": self.exit_code,
            "reasons": list(self.reasons),
        }


def evaluate_health(
    *,
    latest_run: Mapping[str, Any] | None,
    latest_cycle: Mapping[str, Any] | None,
    market_data: Mapping[str, Any],
    open_orders: Mapping[str, Any],
    halt: Mapping[str, Any],
) -> dict[str, Any]:
    """Classify runtime health from status subsections.

    Missing runs/cycles, active halt state, missing market data, and stale open
    orders degrade the result. Failed runs/cycles and stale market data are
    classified as unhealthy because they indicate trading decisions may be wrong
    or no longer operating.
    """
    return assess_runtime_health(
        latest_run=latest_run,
        latest_cycle=latest_cycle,
        market_data=market_data,
        open_orders=open_orders,
        halt=halt,
    ).to_record()


def assess_runtime_health(
    *,
    latest_run: Mapping[str, Any] | None,
    latest_cycle: Mapping[str, Any] | None,
    market_data: Mapping[str, Any],
    open_orders: Mapping[str, Any],
    halt: Mapping[str, Any],
) -> RuntimeHealthAssessment:
    """Classify runtime health from normalized status subsections.

    Args:
        latest_run: Latest run-session status mapping, if any.
        latest_cycle: Latest decision-cycle status mapping, if any.
        market_data: Market-data status summary.
        open_orders: Open-order status summary.
        halt: Operator halt-state summary.

    Returns:
        Immutable runtime health assessment.
    """
    reasons: list[str] = []
    exit_code = 0
    if latest_run is None:
        reasons.append("no_run")
        exit_code = max(exit_code, 1)
    elif str(latest_run.get("status", "")).lower() == "failed":
        reasons.append("latest_run_failed")
        exit_code = max(exit_code, 2)
    if latest_cycle is None:
        reasons.append("no_cycle")
        exit_code = max(exit_code, 1)
    elif str(latest_cycle.get("status", "")).lower() == "failed":
        reasons.append("latest_cycle_failed")
        exit_code = max(exit_code, 2)
    if bool(halt.get("halted")):
        reasons.append("halted")
        exit_code = max(exit_code, 1)
    if market_data.get("missing_count"):
        reasons.append("missing_market_data")
        exit_code = max(exit_code, 1)
    if market_data.get("stale_count"):
        reasons.append("stale_market_data")
        exit_code = max(exit_code, 2)
    if open_orders.get("stale_count"):
        reasons.append("stale_open_orders")
        exit_code = max(exit_code, 1)
    label = "healthy" if exit_code == 0 else "degraded" if exit_code == 1 else "unhealthy"
    return RuntimeHealthAssessment(status=label, exit_code=exit_code, reasons=tuple(reasons))
