"""Cycle identity, execution-plan, timestamp, and run-session contracts.

Subject: Mode-dependent cycle identity, side-effect planning, halts, timestamps, and owned session recording.
Level: Deterministic lifecycle unit contracts with an in-memory recorder.
Collaborators: Real lifecycle and recording helpers, fixed clocks, and a minimal recording fake.
Guarantees: Runtime modes produce explicit ownership and timing decisions before the imperative shell acts.
Non-goals: Market data, strategy or risk evaluation, broker responses, and persistent event storage.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from trader.cycle.lifecycle import (
    _build_cycle_execution_plan,
    _build_cycle_identity,
    _build_cycle_run_session_outcome,
    _build_post_order_portfolio_snapshot_plan,
    _resolve_cycle_run_type,
    _resolve_cycle_snapshot_ts,
    _resolve_decision_ts,
    _resolve_portfolio_asof_ts,
    _should_halt_cycle,
    _should_load_broker_portfolio,
)
from trader.cycle.recording import (
    _record_owned_run_session_finish,
    _record_owned_run_session_start,
)
from trader.identifiers import deterministic_run_session_id


class RunSessionRecorder:
    """Minimal event-store recorder for run-session helper tests."""

    def __init__(self) -> None:
        self.starts: list[dict[str, object]] = []
        self.finishes: list[dict[str, object]] = []

    def record_run_session_start(self, **kwargs) -> None:
        self.starts.append(dict(kwargs))

    def record_run_session_finish(self, **kwargs) -> None:
        self.finishes.append(dict(kwargs))


def test_resolve_cycle_run_type_uses_mode_and_explicit_override() -> None:
    """Infer run type from mode unless the caller supplies an explicit override."""
    assert _resolve_cycle_run_type("backtest", None) == "backtest"
    assert _resolve_cycle_run_type("once", None) == "trading"
    assert _resolve_cycle_run_type("once", "BACKTEST") == "backtest"
    assert _resolve_cycle_run_type("backtest", "TRADING") == "trading"


def test_build_cycle_execution_plan_captures_shell_decisions() -> None:
    """Resolve broker, streaming, portfolio, and synchronization decisions before execution."""
    plan = _build_cycle_execution_plan(
        mode="backtest",
        broker_type="internal",
        portfolio_source="",
        run_type=None,
    )

    assert plan.run_type == "backtest"
    assert plan.broker_kind == "internal"
    assert plan.stream_mode is False
    assert plan.sync_portfolio_on_fill is True
    assert plan.portfolio_source == ""
    assert _should_load_broker_portfolio(plan) is False

    live_alpaca_plan = _build_cycle_execution_plan(
        mode="once",
        broker_type="ALPACA",
        portfolio_source="alpaca",
        run_type=None,
    )

    assert live_alpaca_plan.run_type == "trading"
    assert live_alpaca_plan.broker_kind == "alpaca"
    assert live_alpaca_plan.stream_mode is True
    assert live_alpaca_plan.sync_portfolio_on_fill is True
    assert _should_load_broker_portfolio(live_alpaca_plan) is True


def test_build_cycle_identity_is_deterministic_and_preserves_explicit_run_id() -> None:
    """Own a derived run session only when no existing run identifier is supplied."""
    decision_ts = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    started_at = datetime(2026, 1, 20, 12, 1, tzinfo=timezone.utc)

    owned = _build_cycle_identity(
        strategy_id="strategy_1",
        decision_ts=decision_ts,
        run_type="trading",
        started_at=started_at,
        run_id=None,
    )

    assert owned.run_id == deterministic_run_session_id("trading", started_at)
    assert owned.owns_run_session is True
    assert owned.cycle_id

    explicit = _build_cycle_identity(
        strategy_id="strategy_1",
        decision_ts=decision_ts,
        run_type="trading",
        started_at=started_at,
        run_id="run_existing",
    )

    assert explicit.run_id == "run_existing"
    assert explicit.cycle_id == owned.cycle_id
    assert explicit.owns_run_session is False


def test_cycle_run_session_outcome_and_recording_helpers() -> None:
    """Record session boundaries only for runs owned by the current cycle."""
    recorder = RunSessionRecorder()
    started_at = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    success = _build_cycle_run_session_outcome("success")
    failed = _build_cycle_run_session_outcome("failed", "boom")

    _record_owned_run_session_start(
        event_store=recorder,
        owns_run_session=False,
        run_id="run_ignored",
        run_type="trading",
        started_at=started_at,
        strategy_id="strategy_ignored",
        config_snapshot=None,
        mode="once",
        symbols=("AAPL",),
        timeframe="1Min",
    )
    _record_owned_run_session_finish(
        event_store=recorder,
        owns_run_session=False,
        run_id="run_ignored",
        run_type="trading",
        started_at=started_at,
        outcome=success,
        strategy_id="strategy_ignored",
        mode="once",
        symbols=("AAPL",),
        timeframe="1Min",
    )

    assert recorder.starts == []
    assert recorder.finishes == []
    assert success.status == "success"
    assert success.error_message is None
    assert failed.status == "failed"
    assert failed.error_message == "boom"

    _record_owned_run_session_start(
        event_store=recorder,
        owns_run_session=True,
        run_id="run_1",
        run_type="trading",
        started_at=started_at,
        strategy_id="strategy_1",
        config_snapshot={"mode": "once"},
        mode="once",
        symbols=("AAPL",),
        timeframe="1Min",
    )
    _record_owned_run_session_finish(
        event_store=recorder,
        owns_run_session=True,
        run_id="run_1",
        run_type="trading",
        started_at=started_at,
        outcome=failed,
        strategy_id="strategy_1",
        mode="once",
        symbols=("AAPL",),
        timeframe="1Min",
    )

    assert recorder.starts == [
        {
            "run_id": "run_1",
            "run_type": "trading",
            "started_at": started_at,
            "strategy_id": "strategy_1",
            "config_snapshot": {"mode": "once"},
            "mode": "once",
            "symbols": ("AAPL",),
            "timeframe": "1Min",
        }
    ]
    assert len(recorder.finishes) == 1
    assert recorder.finishes[0]["run_id"] == "run_1"
    assert recorder.finishes[0]["run_type"] == "trading"
    assert recorder.finishes[0]["started_at"] == started_at
    assert recorder.finishes[0]["status"] == "failed"
    assert recorder.finishes[0]["error_message"] == "boom"
    assert recorder.finishes[0]["strategy_id"] == "strategy_1"
    assert recorder.finishes[0]["mode"] == "once"
    assert recorder.finishes[0]["symbols"] == ("AAPL",)
    assert recorder.finishes[0]["timeframe"] == "1Min"
    assert isinstance(recorder.finishes[0]["finished_at"], datetime)


def test_resolve_decision_ts_uses_current_time_and_normalizes_naive_values() -> None:
    """Use the supplied clock fallback and normalize explicit naive decision times."""
    current_ts = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    naive_ts = datetime(2026, 1, 20, 13, 0)

    assert _resolve_decision_ts(None, current_ts=current_ts) == current_ts
    assert _resolve_decision_ts(naive_ts, current_ts=current_ts) == naive_ts.replace(
        tzinfo=timezone.utc
    )


def test_should_halt_cycle_never_halts_backtests() -> None:
    """Apply the global halt only to trading runs, never historical backtests."""
    assert _should_halt_cycle(run_type="trading", halted=True) is True
    assert _should_halt_cycle(run_type="trading", halted=False) is False
    assert _should_halt_cycle(run_type="backtest", halted=True) is False


def test_cycle_timestamp_resolvers_keep_backtest_time_deterministic() -> None:
    """Use decision time for backtests and wall-clock time for live snapshots."""
    decision_ts = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    current_ts = decision_ts + timedelta(minutes=5)

    assert _resolve_portfolio_asof_ts("backtest", decision_ts) == decision_ts
    assert _resolve_portfolio_asof_ts("once", decision_ts) is None
    assert (
        _resolve_cycle_snapshot_ts(
            mode="backtest",
            decision_ts=decision_ts,
            current_ts=current_ts,
        )
        == decision_ts
    )
    assert (
        _resolve_cycle_snapshot_ts(
            mode="once",
            decision_ts=decision_ts,
            current_ts=current_ts,
        )
        == current_ts
    )


def test_post_order_portfolio_snapshot_plan_selects_side_effect_path() -> None:
    """Choose one explicit portfolio action from orders, broker, and synchronization policy."""
    orders = [{"symbol": "AAPL", "side": "buy", "qty": 1.0}]

    assert (
        _build_post_order_portfolio_snapshot_plan(
            processed_orders=[],
            sync_portfolio_on_fill=False,
            broker_kind="noop",
        ).action
        == "none"
    )
    assert (
        _build_post_order_portfolio_snapshot_plan(
            processed_orders=orders,
            sync_portfolio_on_fill=True,
            broker_kind="alpaca",
        ).action
        == "skip_alpaca_synced"
    )
    assert (
        _build_post_order_portfolio_snapshot_plan(
            processed_orders=orders,
            sync_portfolio_on_fill=True,
            broker_kind="internal",
        ).action
        == "persist_broker_fill_snapshot"
    )
    assert (
        _build_post_order_portfolio_snapshot_plan(
            processed_orders=orders,
            sync_portfolio_on_fill=False,
            broker_kind="noop",
        ).action
        == "persist_order_intent_snapshot"
    )
