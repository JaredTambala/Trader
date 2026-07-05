"""Pure lifecycle and execution-plan helpers for decision cycles."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal, Mapping, Sequence

from ..identifiers import deterministic_cycle_id, deterministic_run_session_id


@dataclass(frozen=True)
class CycleResult:
    """Terminal identity and status for one completed decision cycle.

    Attributes:
        run_id: Session/run identifier that groups one or more cycles.
        cycle_id: Deterministic identifier for this decision timestamp.
        status: Terminal cycle status such as `success`, `failed`, or `halted`.
    """

    run_id: str
    cycle_id: str
    status: str


@dataclass(frozen=True)
class CycleExecutionPlan:
    """Pure execution decisions derived from cycle configuration."""

    run_type: str
    broker_kind: str
    stream_mode: bool
    sync_portfolio_on_fill: bool
    portfolio_source: str | None


@dataclass(frozen=True)
class CycleIdentity:
    """Deterministic run and cycle identity for one decision timestamp."""

    run_id: str
    cycle_id: str
    owns_run_session: bool


@dataclass(frozen=True)
class CycleRunSessionOutcome:
    """Terminal run-session status derived from the cycle result."""

    status: str
    error_message: str | None


@dataclass(frozen=True)
class CycleWorkflowResult:
    """Cycle result paired with the run-session outcome it implies."""

    cycle_result: CycleResult
    run_session_outcome: CycleRunSessionOutcome


PortfolioSnapshotAction = Literal[
    "none",
    "skip_alpaca_synced",
    "persist_broker_fill_snapshot",
    "persist_order_intent_snapshot",
]


@dataclass(frozen=True)
class CyclePortfolioSnapshotPlan:
    """Decision describing how processed orders should affect portfolio snapshots."""

    action: PortfolioSnapshotAction


def _resolve_cycle_run_type(mode: str, run_type: str | None) -> str:
    """Return the effective run type for cycle lifecycle records."""
    return (run_type or ("backtest" if mode.lower() == "backtest" else "trading")).lower()


def _build_cycle_execution_plan(
    *,
    mode: str,
    broker_type: str,
    portfolio_source: str | None,
    run_type: str | None,
) -> CycleExecutionPlan:
    """Build deterministic cycle execution decisions from explicit inputs."""
    broker_kind = (broker_type or "noop").lower()
    effective_run_type = _resolve_cycle_run_type(mode, run_type)
    return CycleExecutionPlan(
        run_type=effective_run_type,
        broker_kind=broker_kind,
        stream_mode=mode.lower() != "backtest",
        sync_portfolio_on_fill=broker_kind in {"alpaca", "internal"},
        portfolio_source=portfolio_source,
    )


def _build_cycle_identity(
    *,
    strategy_id: str,
    decision_ts: datetime,
    run_type: str,
    started_at: datetime,
    run_id: str | None,
) -> CycleIdentity:
    """Build deterministic run/cycle identity without touching storage."""
    owns_run_session = run_id is None
    effective_run_id = (
        deterministic_run_session_id(run_type, started_at)
        if owns_run_session
        else run_id
    )
    return CycleIdentity(
        run_id=effective_run_id,
        cycle_id=deterministic_cycle_id(strategy_id, decision_ts),
        owns_run_session=owns_run_session,
    )


def _build_cycle_run_session_outcome(
    status: str,
    error_message: str | None = None,
) -> CycleRunSessionOutcome:
    """Build a terminal run-session outcome value."""
    return CycleRunSessionOutcome(status=status, error_message=error_message)


def _should_load_broker_portfolio(plan: CycleExecutionPlan) -> bool:
    """Return whether broker state should be authoritative for this cycle."""
    return (
        plan.run_type != "backtest"
        and plan.broker_kind == "alpaca"
        and plan.portfolio_source == "alpaca"
    )


def _resolve_portfolio_asof_ts(mode: str, decision_ts: datetime) -> datetime | None:
    """Return the portfolio read timestamp used by backtests."""
    return decision_ts if mode.lower() == "backtest" else None


def _resolve_cycle_snapshot_ts(
    *,
    mode: str,
    decision_ts: datetime,
    current_ts: datetime,
) -> datetime:
    """Return the timestamp to use for cycle snapshots in this mode."""
    return decision_ts if mode.lower() == "backtest" else current_ts


def _build_post_order_portfolio_snapshot_plan(
    *,
    processed_orders: Sequence[Mapping[str, object]],
    sync_portfolio_on_fill: bool,
    broker_kind: str,
) -> CyclePortfolioSnapshotPlan:
    """Decide how portfolio state should be persisted after submitted orders."""
    if not processed_orders:
        return CyclePortfolioSnapshotPlan(action="none")
    if sync_portfolio_on_fill and broker_kind == "alpaca":
        return CyclePortfolioSnapshotPlan(action="skip_alpaca_synced")
    if sync_portfolio_on_fill and broker_kind == "internal":
        return CyclePortfolioSnapshotPlan(action="persist_broker_fill_snapshot")
    return CyclePortfolioSnapshotPlan(action="persist_order_intent_snapshot")


def _should_use_stream_ingestion(*, ingest_market_data: bool, stream_mode: bool) -> bool:
    """Return whether the cycle should use streaming market-data ingestion."""
    return ingest_market_data and stream_mode


def _resolve_market_data_freshness_ts(
    *,
    mode: str,
    decision_ts: datetime,
    current_ts: datetime,
) -> datetime:
    """Return the timestamp used for cycle market-data freshness checks."""
    return decision_ts if mode.lower() == "backtest" else current_ts


def _resolve_decision_ts(
    decision_ts: datetime | None,
    *,
    current_ts: datetime,
) -> datetime:
    """Return the cycle decision timestamp normalized to timezone-aware UTC."""
    resolved = decision_ts or current_ts
    if resolved.tzinfo is None:
        resolved = resolved.replace(tzinfo=timezone.utc)
    return resolved


def _should_halt_cycle(*, run_type: str, halted: bool) -> bool:
    """Return whether the global halt flag should stop this cycle."""
    return run_type != "backtest" and halted


__all__ = [
    "CycleExecutionPlan",
    "CycleIdentity",
    "CyclePortfolioSnapshotPlan",
    "CycleResult",
    "CycleRunSessionOutcome",
    "CycleWorkflowResult",
]
