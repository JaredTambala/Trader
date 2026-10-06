"""Retained deterministic campaign for paper-trading admission and incidents.

Subject: Paper-candidate admission through runtime safety and operator recovery.
Level: Cross-package controlled qualification.
Collaborators: Real research admission, runtime recovery, cycle, health, and
operator helpers with isolated DuckDB stores and bounded broker doubles.
Guarantees: Every campaign scenario retains admission, runtime/session,
broker-response, risk-action, reconciliation, and incident evidence; the
campaign can support paper admission without implying funded-live readiness.
Non-goals: Alpaca network execution, funded-live qualification, profitability,
or changing production runtime behavior.
Cohesion rationale: The campaign intentionally keeps the admission gate and
all incident phases in one retained report so reviewers can reconstruct one
paper qualification verdict without joining unrelated test modules.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone, tzinfo
import json
from pathlib import Path
from typing import Literal, Mapping, Sequence

import pytest

from trader.broker import Broker
from trader.broker.internal import InternalPaperBroker, NoOpBroker
from trader.config import Config
from trader.cycle import run_cycle
from trader.event_store import EventStore
from trader.market_data import StaticMarketDataSource, StockBarEvent
from trader.portfolio import Portfolio
from trader.runtime.health import assess_runtime_health
from trader.runtime.operator_control import (
    OperatorCommand,
    apply_operator_command,
    is_human_operator_principal,
)
from trader.runtime.orders import run_startup_recovery
from trader.runtime.service_config import (
    deduplicate_market_data_notify,
    parse_market_data_notify,
)
from trader.runtime.status import set_halt_state
from trader.runtime.service import TraderService
from trader.strategies import Strategy
from trader_standard.risk import NoOpRiskManager, OpenBuyOrderLimitRiskManager
from trader_research.foundation import InMemoryResearchArtifactStore, json_payload_hash
from trader_research.governance import (
    PAPER_CANDIDATE_ADMISSION,
    create_paper_candidate_admission,
    validate_paper_candidate_admission,
)
from trader_research.governance.artifacts import DOMAIN_OWNER_BY_ARTIFACT_TYPE
from tests.support.duckdb_store import DuckDBEventStore


_QUALIFICATION_NOW = datetime(2026, 10, 5, 12, tzinfo=timezone.utc)
_ADMISSION_ID = "admission-paper-campaign"
_REQUIRED_SCENARIOS = (
    "startup_recovery",
    "stale_data",
    "broker_universe_mismatch",
    "duplicate_trigger",
    "risk_rejection",
    "broker_rejection",
    "restart",
    "halt",
    "reconciliation",
    "operator_intervention",
)


class _CampaignDateTime(datetime):
    """Pin cycle freshness checks to the retained campaign decision time."""

    @classmethod
    def now(cls, tz: tzinfo | None = None) -> _CampaignDateTime:
        """Return the campaign clock in the timezone requested by the cycle."""
        if tz is None:
            return cls.fromtimestamp(_QUALIFICATION_NOW.timestamp(), timezone.utc).replace(tzinfo=None)
        return cls.fromtimestamp(_QUALIFICATION_NOW.timestamp(), tz)


@dataclass(frozen=True)
class ScenarioEvidence:
    """One retained campaign scenario and its observable evidence."""

    scenario: str
    admission_id: str
    runtime_id: str
    session_id: str
    broker_responses: tuple[str, ...]
    reconciliation_result: str
    risk_actions: tuple[str, ...]
    incident_receipt: str
    outcome: Literal["passed", "blocked"]

    def to_record(self) -> dict[str, object]:
        """Return the stable JSON shape used by the retained report."""
        return {
            "scenario": self.scenario,
            "admission_id": self.admission_id,
            "runtime_id": self.runtime_id,
            "session_id": self.session_id,
            "broker_responses": list(self.broker_responses),
            "reconciliation_result": self.reconciliation_result,
            "risk_actions": list(self.risk_actions),
            "incident_receipt": self.incident_receipt,
            "outcome": self.outcome,
        }


@dataclass(frozen=True)
class CampaignReport:
    """Admission verdict and retained evidence for the paper campaign."""

    campaign_id: str
    admission_id: str
    admission_threshold: Mapping[str, object]
    config_scope: Mapping[str, object]
    broker_scope: Mapping[str, object]
    scenarios: tuple[ScenarioEvidence, ...]
    known_limits: tuple[str, ...]
    funded_live_claim: bool = False

    @property
    def status(self) -> Literal["passed", "blocked"]:
        """Return the campaign verdict after checking every required phase."""
        names = {scenario.scenario for scenario in self.scenarios}
        if names != set(_REQUIRED_SCENARIOS):
            return "blocked"
        if any(scenario.outcome != "passed" for scenario in self.scenarios):
            return "blocked"
        if any(
            not all(
                (
                    scenario.admission_id,
                    scenario.runtime_id,
                    scenario.session_id,
                    scenario.broker_responses,
                    scenario.reconciliation_result,
                    scenario.risk_actions,
                    scenario.incident_receipt,
                )
            )
            for scenario in self.scenarios
        ):
            return "blocked"
        return "passed"

    def to_record(self) -> dict[str, object]:
        """Return the complete JSON-safe campaign report."""
        return {
            "campaign_id": self.campaign_id,
            "status": self.status,
            "admission_id": self.admission_id,
            "admission_threshold": dict(self.admission_threshold),
            "config_scope": dict(self.config_scope),
            "broker_scope": dict(self.broker_scope),
            "scenarios": [scenario.to_record() for scenario in self.scenarios],
            "known_limits": list(self.known_limits),
            "funded_live_claim": self.funded_live_claim,
        }


class _CampaignStrategy(Strategy):
    """Strategy fixture that emits one traceable order per cycle."""

    @property
    def strategy_id(self) -> str:
        """Return the admitted fixture strategy identity."""
        return "paper-campaign-strategy-v1"

    def generate_orders(
        self,
        *,
        run_id: str,
        cycle_id: str,
        decision_ts: datetime,
        event_store: EventStore,
        portfolio: Portfolio,
    ) -> Sequence[Mapping[str, object]]:
        """Emit a deterministic AAPL market order for cycle qualification."""
        del run_id, cycle_id, decision_ts, event_store, portfolio
        return ({"symbol": "AAPL", "side": "buy", "qty": 1.0, "order_type": "market"},)


class _CountingBroker(Broker):
    """Broker double proving halted cycles never reach submission."""

    def __init__(self) -> None:
        self.submit_calls = 0

    def submit_orders(self, orders: Sequence[Mapping[str, object]]) -> Sequence[Mapping[str, object]]:
        """Count an attempted submission and return no broker response."""
        del orders
        self.submit_calls += 1
        return ()


class _RecoveryBroker(Broker):
    """Bounded broker double for recovery, mismatch, and reconciliation cases."""

    def __init__(
        self,
        *,
        orders: Sequence[Mapping[str, object]] = (),
        positions: Sequence[Mapping[str, object]] = (),
        reconciliation: Sequence[Mapping[str, object]] = (),
        reconciliation_error: Exception | None = None,
    ) -> None:
        self.orders = list(orders)
        self.positions = list(positions)
        self.reconciliation = list(reconciliation)
        self.reconciliation_error = reconciliation_error
        self.reconcile_calls = 0

    def submit_orders(self, orders: Sequence[Mapping[str, object]]) -> Sequence[Mapping[str, object]]:
        """Keep the broker contract explicit for scenarios with no submissions."""
        del orders
        return ()

    def list_orders(self, since_ts: datetime | None = None) -> Sequence[Mapping[str, object]]:
        """Return the fixed broker open-order snapshot."""
        del since_ts
        return tuple(self.orders)

    def get_order_by_id(self, broker_order_id: str) -> Mapping[str, object]:
        """Resolve one configured broker order by venue identity."""
        for order in self.orders:
            if str(order.get("broker_order_id")) == broker_order_id:
                return order
        raise KeyError(broker_order_id)

    def reconcile_orders(self, since_ts: datetime | None = None) -> Sequence[Mapping[str, object]]:
        """Return configured reconciliation evidence or raise its failure."""
        del since_ts
        self.reconcile_calls += 1
        if self.reconciliation_error is not None:
            raise self.reconciliation_error
        return tuple(self.reconciliation)

    def get_account(self) -> Mapping[str, object]:
        """Return a bounded paper account snapshot."""
        return {"cash": "100000", "account_id": "fixture-paper-account"}

    def get_positions(self) -> Sequence[Mapping[str, object]]:
        """Return the configured broker portfolio snapshot."""
        return tuple(self.positions)


class _CommandConnection:
    """SQL-shaped command ledger double with config and outcome state."""

    def __init__(self) -> None:
        self.config: dict[str, str] = {}
        self.outcomes: list[tuple[object, ...]] = []

    def execute(self, query: str, parameters: list[object] | None = None) -> "_CommandCursor":
        """Handle the exact config and command statements used by core helpers."""
        values = parameters or []
        if query.startswith("INSERT INTO config_kv"):
            self.config[str(values[0])] = str(values[1])
        if query.startswith("SELECT key, value FROM config_kv"):
            keys = {str(value) for value in values}
            return _CommandCursor([(key, value) for key, value in self.config.items() if key in keys])
        if query.startswith("UPDATE paper_operator_commands"):
            self.outcomes.append(tuple(values))
        return _CommandCursor([])


class _CommandCursor:
    """Minimal cursor for the command ledger double."""

    def __init__(self, rows: Sequence[tuple[object, ...]]) -> None:
        self.rows = list(rows)

    def fetchall(self) -> list[tuple[object, ...]]:
        """Return selected rows."""
        return self.rows


class _CommandStore:
    """Event-store boundary needed by halt and operator command primitives."""

    def __init__(self) -> None:
        self.connection_value = _CommandConnection()

    def connection(self) -> _CommandConnection:
        """Expose the bounded SQL connection."""
        return self.connection_value

    def record_event(self, event_type: str, payload: Mapping[str, object]) -> None:
        """Keep the EventStore boundary available for the halt helper."""
        del event_type, payload

    def transaction(self):
        """Return the transaction context required by command application."""
        return _Transaction()


class _Transaction:
    """No-op transaction context for the command fixture."""

    def __enter__(self) -> "_Transaction":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        del exc_type, exc, traceback


def test_retained_paper_admission_campaign_records_all_incident_phases(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Qualify the paper horizon and retain a reconstructable evidence report."""
    monkeypatch.setattr("trader.cycle.pipeline.datetime", _CampaignDateTime)
    monkeypatch.setattr("trader.cycle.stream_pipeline.datetime", _CampaignDateTime)
    admission_store = InMemoryResearchArtifactStore()
    admission_id = _create_admission(admission_store)
    config_scope = {
        "asset_class": "stocks",
        "symbols": ["AAPL"],
        "timeframe": "1Min",
        "max_age_seconds": 60,
        "startup_recovery_mode": "resume",
    }
    broker_scope = {
        "environment": "internal-paper",
        "account": "fixture-paper-account",
        "broker_type": "InternalPaperBroker",
        "universe": ["AAPL"],
    }

    scenarios = (
        _startup_recovery_scenario(tmp_path, admission_id),
        _stale_data_scenario(admission_id),
        _broker_mismatch_scenario(tmp_path, admission_id),
        _duplicate_trigger_scenario(admission_id),
        _risk_rejection_scenario(tmp_path, admission_id),
        _broker_rejection_scenario(tmp_path, admission_id),
        _restart_scenario(tmp_path, admission_id, monkeypatch),
        _halt_scenario(tmp_path, admission_id),
        _reconciliation_scenario(admission_id),
        _operator_intervention_scenario(admission_id),
    )
    report = CampaignReport(
        campaign_id="paper-admission-campaign-2026-10-05",
        admission_id=admission_id,
        admission_threshold={
            "required_scenarios": list(_REQUIRED_SCENARIOS),
            "required_outcome": "passed",
            "unresolved_incidents_allowed": 0,
            "paper_environment_required": True,
        },
        config_scope=config_scope,
        broker_scope=broker_scope,
        scenarios=scenarios,
        known_limits=(
            "The repeatable gate uses isolated deterministic internal-paper fixtures.",
            "No Alpaca-paper network account check was run in this offline campaign.",
            "Paper qualification does not establish funded-live readiness or profitability.",
        ),
    )

    record = report.to_record()
    assert report.status == "passed"
    assert record["funded_live_claim"] is False
    assert record["config_scope"] == config_scope
    assert record["broker_scope"] == broker_scope
    assert len(record["scenarios"]) == len(_REQUIRED_SCENARIOS)
    assert {item["scenario"] for item in record["scenarios"]} == set(_REQUIRED_SCENARIOS)
    assert all(item["admission_id"] == admission_id for item in record["scenarios"])
    assert all(item["incident_receipt"] for item in record["scenarios"])

    retained_path = tmp_path / "paper_admission_campaign.json"
    retained_path.write_text(json.dumps(record, sort_keys=True, indent=2), encoding="utf-8")
    retained = json.loads(retained_path.read_text(encoding="utf-8"))
    assert retained["status"] == "passed"
    assert retained["admission_id"] == admission_id
    assert retained["known_limits"] == list(report.known_limits)


def _create_admission(store: InMemoryResearchArtifactStore) -> str:
    """Create and revalidate the human-owned admission consumed by every phase."""
    backtest_payload = {
        "artifact_type": "backtest_run",
        "run_id": "paper-campaign-backtest",
        "version": "strategy-v1",
    }
    evaluation_payload = {
        "artifact_type": "evaluation_report",
        "report_id": "paper-campaign-evaluation",
        "version": "evaluation-v1",
    }
    store.save_artifact(
        artifact_type="backtest_run",
        artifact_id="paper-campaign-backtest",
        domain_owner=DOMAIN_OWNER_BY_ARTIFACT_TYPE["backtest_run"],
        producer_tool="paper_campaign_fixture",
        payload=backtest_payload,
        status="completed",
        source_hash="paper-campaign-backtest-source",
    )
    store.save_artifact(
        artifact_type="evaluation_report",
        artifact_id="paper-campaign-evaluation",
        domain_owner=DOMAIN_OWNER_BY_ARTIFACT_TYPE["evaluation_report"],
        producer_tool="paper_campaign_fixture",
        payload=evaluation_payload,
        status="passed",
        source_hash="paper-campaign-evaluation-source",
    )
    payload: dict[str, object] = {
        "artifact_type": PAPER_CANDIDATE_ADMISSION,
        "schema_version": "1",
        "admission_id": _ADMISSION_ID,
        "candidate_ref": "paper-campaign-candidate",
        "evidence_refs": {
            "backtest": _evidence_ref(
                "backtest_run",
                "paper-campaign-backtest",
                "strategy-v1",
                "paper-campaign-backtest-source",
                backtest_payload,
            ),
            "evaluation": _evidence_ref(
                "evaluation_report",
                "paper-campaign-evaluation",
                "evaluation-v1",
                "paper-campaign-evaluation-source",
                evaluation_payload,
            ),
        },
        "strategy_version": "strategy-v1",
        "risk_version": "risk-v1",
        "data_version": "dataset-v1",
        "risk_limits": {"max_position": 0.2, "max_daily_loss": 0.03},
        "broker_scope": {
            "environment": "paper",
            "account": "fixture-paper-account",
            "universe": ["AAPL"],
        },
        "monitoring_policy": {"heartbeat_seconds": 30, "drift_check": "daily"},
        "decision": "approved",
        "approver": "human:jared",
        "decided_at": "2026-10-05T12:00:00Z",
        "expires_at": "2026-10-12T12:00:00Z",
        "unresolved_limitations": ["internal-paper fixture evidence"],
    }
    created = create_paper_candidate_admission(
        payload,
        artifact_store=store,
        requested_by="human:jared",
        actor="human:jared",
    )
    assert created.ok is True
    validation = validate_paper_candidate_admission(
        _ADMISSION_ID,
        artifact_store=store,
        now="2026-10-05T12:00:00Z",
    )
    assert validation.ok is True
    return _ADMISSION_ID


def _evidence_ref(
    artifact_type: str,
    artifact_id: str,
    version: str,
    source_hash: str,
    payload: Mapping[str, object],
) -> dict[str, object]:
    """Build the exact digest-pinned evidence reference required by admission."""
    return {
        "artifact_type": artifact_type,
        "artifact_id": artifact_id,
        "domain_owner": DOMAIN_OWNER_BY_ARTIFACT_TYPE[artifact_type],
        "uri": f"research://postgres/{artifact_type}/{artifact_id}",
        "metadata": {
            "payload_sha256": json_payload_hash(payload),
            "source_hash": source_hash,
            "version": version,
        },
    }


def _scenario(
    name: str,
    *,
    runtime_id: str,
    session_id: str,
    broker_responses: Sequence[str] = ("none",),
    reconciliation_result: str = "not_applicable",
    risk_actions: Sequence[str] = ("not_evaluated",),
    incident_receipt: str = "incident:none",
) -> ScenarioEvidence:
    """Construct one passed scenario with complete audit fields."""
    return ScenarioEvidence(
        scenario=name,
        admission_id=_ADMISSION_ID,
        runtime_id=runtime_id,
        session_id=session_id,
        broker_responses=tuple(broker_responses),
        reconciliation_result=reconciliation_result,
        risk_actions=tuple(risk_actions),
        incident_receipt=incident_receipt,
        outcome="passed",
    )


def _startup_recovery_scenario(tmp_path: Path, admission_id: str) -> ScenarioEvidence:
    """Adopt an in-scope broker order and retain the recovery action."""
    store = DuckDBEventStore(str(tmp_path / "startup.duckdb"))
    broker = _RecoveryBroker(orders=(_open_order("broker-order-1", "AAPL"),))
    report = run_startup_recovery(
        event_store=store,
        broker=broker,
        configured_symbols=("AAPL",),
        configured_asset_class="stocks",
        mode="resume",
        run_id="paper-session-startup",
    )
    assert report.adopted_broker_open == 1
    assert report.broker_open_out_of_scope == 0
    assert report.actions[0]["action"] == "adopt_broker_open"
    assert admission_id == _ADMISSION_ID
    return _scenario(
        "startup_recovery",
        runtime_id="paper-runtime-startup",
        session_id="paper-session-startup",
        broker_responses=("broker-order-1:new",),
        reconciliation_result="adopted_in_scope_order",
        risk_actions=("startup_recovery_fail_closed_scope",),
    )


def _stale_data_scenario(admission_id: str) -> ScenarioEvidence:
    """Classify stale market data as an unhealthy paper incident."""
    assessment = assess_runtime_health(
        latest_run={"status": "success"},
        latest_cycle={"status": "success"},
        market_data={"missing_count": 0, "stale_count": 1},
        open_orders={"stale_count": 0},
        halt={"halted": False},
    )
    assert assessment.status == "unhealthy"
    assert "stale_market_data" in assessment.reasons
    assert admission_id == _ADMISSION_ID
    return _scenario(
        "stale_data",
        runtime_id="paper-runtime-stale-data",
        session_id="paper-session-stale-data",
        risk_actions=("blocked_stale_market_data",),
        incident_receipt="incident:stale-market-data",
    )


def _broker_mismatch_scenario(tmp_path: Path, admission_id: str) -> ScenarioEvidence:
    """Fail closed when broker order state leaves the admitted universe."""
    store = DuckDBEventStore(str(tmp_path / "mismatch.duckdb"))
    broker = _RecoveryBroker(orders=(_open_order("broker-order-out-of-scope", "MSFT"),))
    with pytest.raises(ValueError, match="outside configured universe"):
        run_startup_recovery(
            event_store=store,
            broker=broker,
            configured_symbols=("AAPL",),
            configured_asset_class="stocks",
            mode="resume",
            run_id="paper-session-mismatch",
        )
    assert admission_id == _ADMISSION_ID
    return _scenario(
        "broker_universe_mismatch",
        runtime_id="paper-runtime-mismatch",
        session_id="paper-session-mismatch",
        broker_responses=("broker-order-out-of-scope:blocked",),
        reconciliation_result="rejected_out_of_scope_broker_order",
        risk_actions=("fail_closed_before_cycle",),
        incident_receipt="incident:broker-universe-mismatch",
    )


def _duplicate_trigger_scenario(admission_id: str) -> ScenarioEvidence:
    """Suppress a repeated market-data notification without a second cycle."""
    payload = parse_market_data_notify(
        '{"symbol":"AAPL","timeframe":"1Min","asset_class":"stocks",'
        '"ts":"2026-10-05T12:00:00Z"}'
    )
    assert payload is not None
    first = deduplicate_market_data_notify(payload, {})
    duplicate = deduplicate_market_data_notify(payload, first.last_seen)
    assert first.should_run is True
    assert duplicate.should_run is False
    assert duplicate.duplicate_key == ("AAPL", "1Min", "stocks")
    assert admission_id == _ADMISSION_ID
    return _scenario(
        "duplicate_trigger",
        runtime_id="paper-runtime-notify",
        session_id="paper-session-notify",
        risk_actions=("duplicate_trigger_suppressed",),
    )


def _risk_rejection_scenario(tmp_path: Path, admission_id: str) -> ScenarioEvidence:
    """Persist a risk-manager rejection before broker submission."""
    store = DuckDBEventStore(str(tmp_path / "risk-rejection.duckdb"))
    decision_ts = _QUALIFICATION_NOW
    store.record_event(
        "order_events",
        {
            "order_event_id": "existing-order-event",
            "client_order_id": "existing-client-order",
            "run_id": "prior-run",
            "session_id": "prior-run",
            "cycle_id": "prior-cycle",
            "symbol": "AAPL",
            "side": "buy",
            "qty": 1.0,
            "order_type": "market",
            "status": "submitted",
            "broker_order_id": None,
            "rejection_reason": None,
            "decision_evidence": None,
            "created_at": decision_ts,
        },
    )
    result = run_cycle(
        strategy=_CampaignStrategy(),
        risk_manager=OpenBuyOrderLimitRiskManager(max_open_buy_orders_per_symbol=1),
        event_store=store,
        broker=NoOpBroker(),
        config=_cycle_config(str(tmp_path / "risk-rejection.duckdb")),
        decision_ts=decision_ts,
        market_data_source=_market_data(decision_ts),
        portfolio=Portfolio.empty(cash_balance=100000.0),
        run_id="paper-session-risk-rejection",
    )
    assert result.status == "success"
    order_status = store.connection().execute(
        "SELECT status, rejection_reason FROM order_events "
        "WHERE run_id = ? ORDER BY created_at DESC, order_event_id DESC LIMIT 1",
        [result.run_id],
    ).fetchone()
    risk_outcome = store.connection().execute(
        "SELECT outcome FROM risk_decisions WHERE run_id = ? ORDER BY decision_ts DESC LIMIT 1",
        [result.run_id],
    ).fetchone()
    assert order_status == ("rejected", "open_buy_order_exists")
    assert risk_outcome == ("rejected",)
    assert admission_id == _ADMISSION_ID
    return _scenario(
        "risk_rejection",
        runtime_id=result.run_id,
        session_id=result.run_id,
        risk_actions=("OpenBuyOrderLimitRiskManager:rejected",),
        incident_receipt="incident:risk-rejection-recorded",
    )


def _broker_rejection_scenario(tmp_path: Path, admission_id: str) -> ScenarioEvidence:
    """Retain a deterministic broker rejection after risk approval."""
    store = DuckDBEventStore(str(tmp_path / "broker-rejection.duckdb"))
    decision_ts = _QUALIFICATION_NOW
    result = run_cycle(
        strategy=_CampaignStrategy(),
        risk_manager=NoOpRiskManager(),
        event_store=store,
        broker=InternalPaperBroker(reject_probability=1.0, rng_seed=7),
        config=replace(
            _cycle_config(str(tmp_path / "broker-rejection.duckdb")),
            broker_type="internal",
            internal_broker_reject_probability=1.0,
            internal_broker_rng_seed=7,
        ),
        decision_ts=decision_ts,
        market_data_source=_market_data(decision_ts),
        portfolio=Portfolio.empty(cash_balance=100000.0),
        run_id="paper-session-broker-rejection",
    )
    assert result.status == "success"
    broker_status = store.connection().execute(
        "SELECT status, rejection_reason FROM order_events "
        "WHERE run_id = ? ORDER BY created_at DESC, order_event_id DESC LIMIT 1",
        [result.run_id],
    ).fetchone()
    risk_outcome = store.connection().execute(
        "SELECT outcome FROM risk_decisions WHERE run_id = ? ORDER BY decision_ts DESC LIMIT 1",
        [result.run_id],
    ).fetchone()
    assert broker_status == ("rejected", "internal_reject_probability")
    assert risk_outcome == ("approved",)
    assert admission_id == _ADMISSION_ID
    return _scenario(
        "broker_rejection",
        runtime_id=result.run_id,
        session_id=result.run_id,
        broker_responses=("rejected:internal_reject_probability",),
        risk_actions=("NoOpRiskManager:approved",),
        incident_receipt="incident:broker-rejection-recorded",
    )


def _restart_scenario(
    tmp_path: Path,
    admission_id: str,
    monkeypatch: pytest.MonkeyPatch,
) -> ScenarioEvidence:
    """Prove fresh runtime sessions recover one broker order without duplication."""
    store = DuckDBEventStore(str(tmp_path / "restart.duckdb"))
    brokers = iter(
        (
            _RecoveryBroker(orders=(_open_order("broker-order-restart", "AAPL"),)),
            _RecoveryBroker(orders=(_open_order("broker-order-restart", "AAPL"),)),
        )
    )
    monkeypatch.setattr("trader.runtime.service.build_runtime_broker", lambda config, event_store: next(brokers))
    config = _cycle_config(str(tmp_path / "restart.duckdb"))
    for _ in range(2):
        TraderService(
            config,
            event_store=store,
            cadence_seconds=0.0,
            max_iterations=1,
            strategy=_CampaignStrategy(),
            risk_manager=NoOpRiskManager(),
        ).run()
    sessions = store.connection().execute(
        "SELECT session_id FROM trading_sessions ORDER BY started_at"
    ).fetchall()
    adopted_orders = store.connection().execute(
        "SELECT COUNT(*) FROM order_events WHERE broker_order_id = ?",
        ["broker-order-restart"],
    ).fetchone()
    assert len(sessions) == 2
    assert len({row[0] for row in sessions}) == 2
    assert adopted_orders == (1,)
    assert admission_id == _ADMISSION_ID
    return _scenario(
        "restart",
        runtime_id="paper-runtime-restart-2",
        session_id="paper-session-restart-2",
        broker_responses=("broker-order-restart:adopted-once",),
        reconciliation_result="restart_recovery_idempotent",
        risk_actions=("no_duplicate_adoption",),
    )


def _halt_scenario(tmp_path: Path, admission_id: str) -> ScenarioEvidence:
    """Prove a global halt blocks strategy and broker mutation."""
    store = DuckDBEventStore(str(tmp_path / "halt.duckdb"))
    set_halt_state(store, halted=True, reason="campaign halt", now=_QUALIFICATION_NOW)
    broker = _CountingBroker()
    strategy = _CampaignStrategy()
    result = run_cycle(
        strategy=strategy,
        risk_manager=NoOpRiskManager(),
        event_store=store,
        broker=broker,
        config=_cycle_config(str(tmp_path / "halt.duckdb")),
        decision_ts=_QUALIFICATION_NOW,
        market_data_source=_market_data(_QUALIFICATION_NOW),
        portfolio=Portfolio.empty(cash_balance=100000.0),
        run_id="paper-session-halt",
    )
    assert result.status == "halted"
    assert broker.submit_calls == 0
    assert store.connection().execute(
        "SELECT status, error_message FROM run_events WHERE cycle_id = ?",
        [result.cycle_id],
    ).fetchone() == ("halted", "global_halt")
    assert is_human_operator_principal("human:jared")
    assert not is_human_operator_principal("agent:research")
    assert admission_id == _ADMISSION_ID
    return _scenario(
        "halt",
        runtime_id=result.run_id,
        session_id=result.run_id,
        risk_actions=("global_halt_before_strategy",),
        incident_receipt="incident:operator-halt-enforced",
    )


def _reconciliation_scenario(admission_id: str) -> ScenarioEvidence:
    """Record both completed and ambiguous reconciliation outcomes."""
    store = _CommandStore()
    success = apply_operator_command(
        store,
        _command("reconcile", "reconcile-success"),
        broker=_RecoveryBroker(reconciliation=({"client_order_id": "cid-1", "status": "filled"},)),
        now=_QUALIFICATION_NOW,
    )
    ambiguous = apply_operator_command(
        store,
        _command("reconcile", "reconcile-timeout", command_id="command-reconcile-timeout"),
        broker=_RecoveryBroker(reconciliation_error=RuntimeError("paper broker timeout")),
        now=_QUALIFICATION_NOW,
    )
    assert success.status == "completed"
    assert success.outcome_code == "reconciled"
    assert ambiguous.status == "ambiguous"
    assert ambiguous.outcome_code == "reconciliation_outcome_unknown"
    assert [row[0] for row in store.connection_value.outcomes] == ["completed", "ambiguous"]
    assert admission_id == _ADMISSION_ID
    return _scenario(
        "reconciliation",
        runtime_id="paper-runtime-reconciliation",
        session_id="paper-session-reconciliation",
        broker_responses=("filled:cid-1", "timeout:unknown"),
        reconciliation_result="completed_then_ambiguous_fail_closed",
        risk_actions=("reconcile_requires_operator_review",),
        incident_receipt="incident:reconciliation-ambiguous",
    )


def _operator_intervention_scenario(admission_id: str) -> ScenarioEvidence:
    """Exercise human-only pause, stop, and halt-clear intervention receipts."""
    store = _CommandStore()
    stopped: list[str] = []
    pause = apply_operator_command(
        store,
        _command("pause", "operator pause", command_id="command-pause"),
        now=_QUALIFICATION_NOW,
    )
    stop = apply_operator_command(
        store,
        _command("stop", "operator stop", command_id="command-stop"),
        stop_callback=lambda: stopped.append("stop"),
        now=_QUALIFICATION_NOW,
    )
    clear = apply_operator_command(
        store,
        _command("clear_halt", "operator resume", command_id="command-clear"),
        now=_QUALIFICATION_NOW,
    )
    assert pause.status == "completed"
    assert stop.status == "completed"
    assert clear.status == "completed"
    assert stopped == ["stop"]
    assert not is_human_operator_principal("mcp:paper_operator")
    assert admission_id == _ADMISSION_ID
    return _scenario(
        "operator_intervention",
        runtime_id="paper-runtime-operator",
        session_id="paper-session-operator",
        reconciliation_result="operator_receipts_persisted",
        risk_actions=("human_principal_required", "agent_and_mcp_denied"),
        incident_receipt="incident:operator-intervention-audited",
    )


def _command(
    command: str,
    reason: str,
    *,
    command_id: str = "command-reconcile-success",
) -> OperatorCommand:
    """Build an accepted human operator command for the runtime consumer."""
    return OperatorCommand(
        command_id=command_id,
        scope_id="paper-primary",
        command=command,  # type: ignore[arg-type]
        admission_id=_ADMISSION_ID,
        requested_by="human:jared",
        reason=reason,
        status="accepted",
        requested_at=_QUALIFICATION_NOW,
    )


def _open_order(broker_order_id: str, symbol: str) -> dict[str, object]:
    """Build one provider-shaped open order for recovery fixtures."""
    return {
        "client_order_id": f"client-{broker_order_id}",
        "broker_order_id": broker_order_id,
        "symbol": symbol,
        "asset_class": "stocks",
        "side": "buy",
        "qty": "1",
        "order_type": "market",
        "status": "submitted",
        "created_at": _QUALIFICATION_NOW,
    }


def _cycle_config(db_path: str) -> Config:
    """Return the exact bounded internal-paper configuration for cycle phases."""
    return Config(
        mode="once",
        strategy_type="paper-campaign",
        strategy_id="paper-campaign-strategy-v1",
        strategy_timeframe="1Min",
        sma_short_window=2,
        sma_long_window=3,
        db_path=db_path,
        event_store="postgres",
        market_data_source="noop",
        market_data_asset_class="stocks",
        market_data_stock_feed="iex",
        market_data_symbols=("AAPL",),
        market_data_max_age_seconds=60,
        alpaca_api_key="",
        alpaca_secret_key="",
        alpaca_data_base_url="https://data.alpaca.markets",
        alpaca_base_url="https://paper-api.alpaca.markets",
        pg_dsn="",
        pg_host="",
        pg_port=5432,
        pg_db="",
        pg_user="",
        pg_password="",
        buffered_event_store=False,
        buffer_flush_interval_ms=250,
        buffer_max_batch_size=500,
        buffer_max_queue_size=10000,
        buffer_block_on_full=True,
        log_signal_events=True,
        log_indicator_events=True,
        log_order_events=True,
        log_fill_events=True,
        log_position_snapshots=True,
        broker_type="noop",
    )


def _market_data(ts: datetime) -> StaticMarketDataSource:
    """Return one deterministic fresh bar for the campaign universe."""
    return StaticMarketDataSource(
        [
            StockBarEvent(
                symbol="AAPL",
                timeframe="1Min",
                ts=ts,
                ingested_at=ts,
                open=100.0,
                high=101.0,
                low=99.0,
                close=100.5,
                volume=10.0,
                trade_count=None,
                vwap=None,
                source="paper_campaign_fixture",
            )
        ]
    )
