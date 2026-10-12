"""Fail-closed adapter from an admitted ResearchJob to a backtest producer.

The durable worker owns leases and terminal state. This adapter owns the
research-to-producer boundary: it reloads the immutable job request, proposal,
and approved protocol, revalidates their pinned inputs, and only then invokes
the canonical backtest producer. ``BacktestRunnerResearchProducer`` is the
production composition for this boundary; tests may inject a bounded producer
to exercise denial and partial paths. No copied protocol payload or stale
worker memory can authorize execution.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import asdict
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, Sequence
from typing import Protocol

from trader.backtest import BacktestResult, BacktestRunner, BacktestSpec, build_backtest_assumptions
from trader.backtest.export_payloads import (
    _build_equity_curve_csv_rows,
    _build_trade_csv_rows,
    serialize_backtest_result,
)
from trader.config import Config
from trader.event_store import EventStore
from trader.portfolio import Position
from trader.risk import RiskManager
from trader_research.experiments.implementations import (
    ImplementationVersion,
    instantiate_risk_manager,
    instantiate_strategy,
)
from trader_research.experiments.backtests.execution import (
    RecordingRiskPipeline,
    _available_risk_telemetry,
    _exposure_summary,
    _result_summary,
    _risk_breaches,
    _risk_decisions,
    _symbol_metrics,
)
from trader_research.experiments import ExperimentJobRequest
from trader_research.foundation import (
    EXPERIMENTS_DOMAIN_OWNER,
    ResearchArtifactStore,
    ResearchArtifactStoreError,
    json_payload_hash,
    parse_research_artifact_uri,
)
from trader_research.foundation.artifacts import SCHEMA_VERSION
from trader_research.governance import (
    BACKTEST_RUN,
    DATASET_MANIFEST,
    DATA_QUALITY_REPORT,
    EXPERIMENT_JOB_REQUEST,
    EXPERIMENT_PROTOCOL,
    EXPERIMENT_PROTOCOL_PROPOSAL,
    ArtifactReportRef,
    ExperimentProtocol,
    ExperimentProtocolProposal,
    ProtocolDataset,
    ResearchJob,
    ResearchIssue,
    apply_experiment_protocol_approvals,
    revalidate_experiment_protocol_inputs,
)

from .worker import (
    AmbiguousExecutionError,
    ResearchJobExecutionOutcome,
    ResearchJobExecutor,
    ResearchJobProgressSink,
)


class ApprovedExperimentBacktestProducer(Protocol):
    """Canonical producer invoked only after request and protocol rereads."""

    async def execute(
        self,
        request: ExperimentJobRequest,
        protocol: ExperimentProtocol,
        *,
        run_id: str,
        progress: ResearchJobProgressSink,
    ) -> ResearchJobExecutionOutcome:
        """Run one approved backtest and return bounded child evidence."""


@dataclass(frozen=True)
class BacktestRunnerResearchProducer:
    """Execute an approved protocol through Trader's canonical backtest runner.

    The producer deliberately accepts the protocol and request only after the
    enclosing :class:`ApprovedExperimentBacktestExecutor` has reread and
    revalidated them. It resolves every implementation and Data reference from
    the canonical artifact store, constructs the same strategy/risk contracts
    used by research backtests, and writes one deterministic ``backtest_run``
    receipt. No MCP or agent code can bypass this boundary.

    Attributes:
        artifact_store: Canonical store for pinned inputs and run evidence.
        config: Core Trader configuration owned by the worker composition.
        event_store: Queryable event store containing the qualified replay bars.
    """

    artifact_store: ResearchArtifactStore
    config: Config
    event_store: EventStore

    async def execute(
        self,
        request: ExperimentJobRequest,
        protocol: ExperimentProtocol,
        *,
        run_id: str,
        progress: ResearchJobProgressSink,
    ) -> ResearchJobExecutionOutcome:
        """Run one approved protocol and retain a canonical backtest receipt."""
        loop = asyncio.get_running_loop()

        def emit_progress(
            processed: int, total: int, last_ts: datetime | None
        ) -> None:
            """Bridge the synchronous runner callback to the async lease sink."""

            async def notify() -> None:
                _ = processed, total
                await progress(last_ts)

            asyncio.run_coroutine_threadsafe(notify(), loop).result()

        try:
            result, risk_pipeline = await asyncio.to_thread(
                self._run,
                request,
                protocol,
                run_id,
                emit_progress,
            )
        except AmbiguousExecutionError:
            raise
        except Exception as exc:
            raise RuntimeError(f"approved experiment backtest failed: {exc}") from exc

        status = "passed" if result.total_runs > 0 and result.failed_runs == 0 else "blocked"
        payload = _backtest_run_payload(
            request=request,
            protocol=protocol,
            run_id=run_id,
            result=result,
            risk_manager=risk_pipeline,
            status=status,
        )
        try:
            record = self.artifact_store.save_artifact(
                artifact_type=BACKTEST_RUN,
                artifact_id=run_id,
                domain_owner=EXPERIMENTS_DOMAIN_OWNER,
                producer_tool="research_run_approved_experiment_backtest",
                requested_by=request.requested_by,
                actor=request.actor,
                payload=payload,
                status=status,
                metadata={
                    "protocol_id": protocol.protocol_id,
                    "dataset_id": payload["dataset_id"],
                },
            )
        except Exception as exc:
            raise AmbiguousExecutionError(
                "BacktestRunner completed but its canonical run receipt could not be retained"
            ) from exc

        reference = ArtifactReportRef(
            artifact_id=record.artifact_id,
            artifact_type=record.artifact_type,
            domain_owner=record.domain_owner,
            uri=record.uri,
            metadata={"payload_sha256": json_payload_hash(record.payload)},
        )
        if status == "passed":
            return ResearchJobExecutionOutcome(
                status="succeeded",
                produced_artifact_refs=(reference,),
                warnings=tuple(
                    ResearchIssue(
                        code="backtest_warning",
                        message=warning,
                        details={"run_id": run_id},
                    )
                    for warning in result.warnings
                ),
            )
        return ResearchJobExecutionOutcome(
            status="partial",
            produced_artifact_refs=(reference,),
            warnings=tuple(
                ResearchIssue(
                    code="backtest_warning",
                    message=warning,
                    details={"run_id": run_id},
                )
                for warning in result.warnings
            ),
            blockers=(
                ResearchIssue(
                    code="backtest_replay_incomplete",
                    message="The canonical runner did not complete every replay cycle.",
                    details={
                        "run_id": run_id,
                        "total_runs": result.total_runs,
                        "failed_runs": result.failed_runs,
                    },
                ),
            ),
        )

    def _run(
        self,
        request: ExperimentJobRequest,
        protocol: ExperimentProtocol,
        run_id: str,
        progress: Callable[[int, int, datetime | None], None],
    ) -> tuple[BacktestResult, RecordingRiskPipeline]:
        """Resolve pinned inputs and execute the synchronous core runner."""
        dataset = _primary_dataset(protocol.datasets)
        manifest = _load_pinned_record(
            self.artifact_store,
            dataset.dataset_manifest_ref,
            expected_type=DATASET_MANIFEST,
        )
        quality = _load_pinned_record(
            self.artifact_store,
            dataset.data_quality_report_ref,
            expected_type=DATA_QUALITY_REPORT,
        )
        strategy_record = _load_pinned_record(
            self.artifact_store,
            protocol.strategy.implementation_ref,
            expected_type="implementation_version",
        )
        strategy_version = ImplementationVersion.from_dict(strategy_record.payload)
        if strategy_version.implementation_kind != "strategy":
            raise ValueError("approved protocol strategy implementation kind drifted")
        symbols = tuple(dataset.requirement.symbols)
        strategy = instantiate_strategy(
            strategy_version,
            symbols=list(symbols),
            asset_class=_runner_asset_class(dataset.requirement.asset_class),
            timeframe=dataset.requirement.timeframe,
            parameters=protocol.strategy.parameters,
            sizing=protocol.strategy.sizing,
        )
        risk_managers: list[tuple[str, RiskManager]] = []
        for risk in protocol.risk_managers:
            record = _load_pinned_record(
                self.artifact_store,
                risk.implementation_ref,
                expected_type="implementation_version",
            )
            version = ImplementationVersion.from_dict(record.payload)
            if version.implementation_kind != "risk_manager":
                raise ValueError("approved protocol risk implementation kind drifted")
            risk_managers.append(
                (
                    version.implementation_version_id,
                    instantiate_risk_manager(version, parameters=risk.parameters),
                )
            )
        risk_pipeline = RecordingRiskPipeline(risk_managers)
        start, end = _dataset_window(manifest.payload, dataset.requirement.start, dataset.requirement.end)
        positions = tuple(
            Position(item.symbol, item.quantity, item.avg_price)
            for item in protocol.initial_portfolio.positions
        )
        runner = BacktestRunner(
            self.config,
            BacktestSpec(
                start=start,
                end=end,
                timeframe=dataset.requirement.timeframe,
                max_runs=protocol.max_runs,
            ),
            strategy=strategy,
            risk_manager=risk_pipeline,
            symbols=symbols,
            asset_class=_runner_asset_class(dataset.requirement.asset_class),
            event_store=self.event_store,
            initial_positions=positions,
            initial_cash=protocol.initial_portfolio.cash,
            assumptions=build_backtest_assumptions(
                _protocol_assumptions(protocol.strategy.execution_assumptions, protocol.costs)
            ),
            run_id=run_id,
            config_snapshot=_safe_config_snapshot(self.config),
            started_at=start,
        )
        result = runner.run(
            log_cycle_details=protocol.log_cycle_details,
            progress_callback=progress,
        )
        if result.run_id != run_id:
            raise ValueError("BacktestRunner returned a different run identity")
        del request, quality
        return result, risk_pipeline


@dataclass(frozen=True)
class ApprovedExperimentBacktestExecutor(ResearchJobExecutor):
    """Resolve one admitted job and delegate to the canonical producer.

    Attributes:
        artifact_store: Canonical store used for fresh request and protocol reads.
        producer: Operation-specific adapter that invokes ``BacktestRunner``.
    """

    artifact_store: ResearchArtifactStore
    producer: ApprovedExperimentBacktestProducer

    async def execute(
        self,
        job: ResearchJob,
        *,
        run_id: str,
        progress: ResearchJobProgressSink,
    ) -> ResearchJobExecutionOutcome:
        """Reload and validate the approved request before producer execution.

        Raises:
            ValueError: If any immutable request, approval, or input identity
                has drifted, or if the producer returns an unresolvable child
                artifact reference.
        """
        request_record = _load_uri_record(
            self.artifact_store,
            job.request_ref,
            expected_type=EXPERIMENT_JOB_REQUEST,
        )
        request = ExperimentJobRequest.from_dict(request_record.payload)
        if request.request_id != request_record.artifact_id:
            raise ValueError("experiment job request artifact identity drifted")
        if json_payload_hash(request.to_dict()) != job.request_digest:
            raise ValueError("research job request digest drifted")
        if request.requested_by != job.requested_by:
            raise ValueError("research job requester drifted")
        if request.actor != job.actor:
            raise ValueError("research job actor drifted")
        if request.code_identity != job.code_identity:
            raise ValueError("research job code identity drifted")
        if request.environment_identity != job.environment_identity:
            raise ValueError("research job environment identity drifted")

        proposal_record = _load_pinned_record(
            self.artifact_store,
            request.proposal_ref,
            expected_type=EXPERIMENT_PROTOCOL_PROPOSAL,
        )
        protocol_record = _load_pinned_record(
            self.artifact_store,
            request.approved_protocol_ref,
            expected_type=EXPERIMENT_PROTOCOL,
        )
        proposal = ExperimentProtocolProposal.from_dict(proposal_record.payload)
        protocol = ExperimentProtocol.from_dict(protocol_record.payload)
        expected_protocol = apply_experiment_protocol_approvals(
            proposal,
            protocol.approvals,
        )
        if expected_protocol.to_dict() != dict(protocol_record.payload):
            raise ValueError("approved experiment protocol drifted from proposal")
        revalidate_experiment_protocol_inputs(
            proposal,
            artifact_store=self.artifact_store,
        )

        outcome = await self.producer.execute(
            request,
            protocol,
            run_id=run_id,
            progress=progress,
        )
        _validate_producer_outcome(self.artifact_store, outcome, run_id=run_id)
        if outcome.status == "succeeded" and not any(
            ref.artifact_type == BACKTEST_RUN
            for ref in outcome.produced_artifact_refs
        ):
            return ResearchJobExecutionOutcome(
                status="partial",
                produced_artifact_refs=outcome.produced_artifact_refs,
                warnings=outcome.warnings,
                blockers=(
                    ResearchIssue(
                        code="backtest_run_receipt_missing",
                        message="A successful producer must retain a canonical backtest run receipt.",
                        details={"job_id": job.job_id, "run_id": run_id},
                    ),
                ),
            )
        return outcome


def _primary_dataset(datasets: Sequence[ProtocolDataset]) -> ProtocolDataset:
    """Select the approved baseline or selection dataset for a backtest."""
    candidates = [item for item in datasets if getattr(item.role, "value", item.role) in {"baseline", "selection"}]
    if len(candidates) != 1:
        raise ValueError("approved backtest requires exactly one baseline or selection dataset")
    return candidates[0]


def _runner_asset_class(value: str) -> str:
    """Normalize governance asset-class vocabulary to the core runner values."""
    normalized = value.strip().lower()
    if normalized in {"stocks", "stock", "equities", "equity"}:
        return "stocks"
    if normalized in {"crypto", "cryptocurrency"}:
        return "crypto"
    raise ValueError(f"unsupported approved experiment asset class: {value}")


def _dataset_window(
    payload: Mapping[str, Any],
    fallback_start: str,
    fallback_end: str,
) -> tuple[datetime, datetime]:
    """Read the exact replay window from the retained manifest."""
    window = payload.get("time_range") or payload.get("requested_window")
    if not isinstance(window, Mapping):
        raise ValueError("approved dataset manifest has no replay window")
    start = _parse_datetime(window.get("start") or fallback_start, "dataset.start")
    end = _parse_datetime(window.get("end") or fallback_end, "dataset.end")
    if end <= start:
        raise ValueError("approved dataset replay window must have positive duration")
    return start, end


def _parse_datetime(value: object, label: str) -> datetime:
    """Parse one UTC-aware ISO timestamp at the worker boundary."""
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value or "").strip()
        if not text:
            raise ValueError(f"{label} is required")
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"{label} must include a timezone")
    return parsed


def _protocol_assumptions(
    execution_assumptions: Mapping[str, Any],
    costs: Sequence[Any],
) -> dict[str, Any]:
    """Map explicit protocol assumptions and costs to core backtest inputs."""
    values = dict(execution_assumptions)
    fees: dict[str, float] = {}
    slippage: dict[str, float] = {}
    for cost in costs:
        name = str(cost.name).strip().lower()
        unit = str(cost.unit).strip().lower()
        target = slippage if "slippage" in name else fees
        if "bps" in unit or "basis" in unit or "bps" in name:
            target["bps"] = float(cost.value)
        elif "slippage" in name:
            target["bps"] = float(cost.value)
        else:
            target["fixed_per_order"] = float(cost.value)
    values.setdefault("fill_model", "full_fill")
    values.setdefault("latency_ms", 0.0)
    values.setdefault("fees", fees)
    values.setdefault("slippage", slippage)
    values.setdefault("data", {})
    return values


def _safe_config_snapshot(config: Config) -> dict[str, Any]:
    """Build a redacted runtime snapshot for the canonical run receipt."""
    snapshot = asdict(config)
    for secret in ("alpaca_api_key", "alpaca_secret_key", "pg_dsn", "pg_password"):
        snapshot.pop(secret, None)
    return snapshot


def _backtest_run_payload(
    *,
    request: ExperimentJobRequest,
    protocol: ExperimentProtocol,
    run_id: str,
    result: BacktestResult,
    risk_manager: RiskManager,
    status: str,
) -> dict[str, Any]:
    """Build the canonical research run payload from one core result."""
    dataset = _primary_dataset(protocol.datasets)
    dataset_id = dataset.dataset_manifest_ref.artifact_id
    symbol_metrics = _symbol_metrics(result)
    summary = _result_summary(result)
    summary["run_id"] = run_id
    return {
        "artifact_type": BACKTEST_RUN,
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "backtest_kind": "portfolio",
        "status": status,
        "experiment_id": protocol.protocol_id,
        "proposal_id": request.proposal_ref.artifact_id,
        "dataset_id": dataset_id,
        "backtest_specification_id": protocol.protocol_id,
        "strategy_specification_id": protocol.strategy.implementation_ref.artifact_id,
        "risk_stack_specification_id": protocol.protocol_id,
        "selection_origin_ref": None,
        "parent_specification_ref": None,
        "variant_reason": None,
        "summary": summary,
        "warnings": list(result.warnings),
        "blockers": [] if status == "passed" else ["backtest did not complete all replay cycles"],
        "bundle": {
            "result": serialize_backtest_result(result),
            "metrics": summary,
            "equity_curve": _build_equity_curve_csv_rows(result),
            "trades": _build_trade_csv_rows(result.trades),
            "positions": [asdict(position) for position in result.positions],
            "symbol_metrics": symbol_metrics,
            "exposure_summary": _exposure_summary(result, symbol_metrics),
            "risk_decisions": _risk_decisions(risk_manager),
            "risk_limit_breaches": _risk_breaches(_risk_decisions(risk_manager)),
            "risk_measure_summary": {
                "available_telemetry": _available_risk_telemetry(result, symbol_metrics),
                "missing_required_telemetry": [],
                "var": None,
                "cvar": None,
            },
            "provenance": {
                "experiment_job_request": request.to_dict(),
                "experiment_protocol": protocol.to_dict(),
                "strategy_implementation_ref": protocol.strategy.implementation_ref.to_dict(),
                "risk_implementation_refs": [item.implementation_ref.to_dict() for item in protocol.risk_managers],
                "dataset_manifest_ref": dataset.dataset_manifest_ref.to_dict(),
                "data_quality_report_ref": dataset.data_quality_report_ref.to_dict(),
            },
        },
    }


def _load_uri_record(
    store: ResearchArtifactStore,
    uri: str,
    *,
    expected_type: str,
):
    """Load one canonical record and require its URI type and identity."""
    artifact_type, artifact_id = parse_research_artifact_uri(uri)
    if artifact_type != expected_type:
        raise ResearchArtifactStoreError(
            f"expected {expected_type} reference, received {artifact_type}"
        )
    record = store.load_artifact_record(artifact_type, artifact_id)
    if record.uri != uri or record.artifact_type != expected_type:
        raise ResearchArtifactStoreError("canonical artifact URI identity drifted")
    return record


def _load_pinned_record(
    store: ResearchArtifactStore,
    reference: ArtifactReportRef,
    *,
    expected_type: str,
):
    """Load a typed reference and verify its authority and payload digest."""
    if reference.artifact_type != expected_type:
        raise ValueError(f"reference must point to {expected_type}")
    record = _load_uri_record(store, reference.uri, expected_type=expected_type)
    if record.artifact_id != reference.artifact_id:
        raise ValueError("canonical artifact ID drifted")
    if record.domain_owner != reference.domain_owner:
        raise ValueError("canonical artifact owner drifted")
    expected_digest = reference.metadata.get("payload_sha256")
    if expected_digest != json_payload_hash(record.payload):
        raise ValueError("canonical artifact payload drifted")
    return record


def _validate_producer_outcome(
    store: ResearchArtifactStore,
    outcome: ResearchJobExecutionOutcome,
    *,
    run_id: str,
) -> None:
    """Reject child references that do not resolve to canonical records."""
    for reference in outcome.produced_artifact_refs:
        record = _load_uri_record(
            store,
            reference.uri,
            expected_type=reference.artifact_type,
        )
        if record.artifact_id != reference.artifact_id:
            raise ValueError("producer artifact ID drifted")
        if record.domain_owner != reference.domain_owner:
            raise ValueError("producer artifact owner drifted")
        if reference.metadata.get("payload_sha256") != json_payload_hash(record.payload):
            raise ValueError("producer artifact payload drifted")
        if reference.artifact_type == BACKTEST_RUN and (
            record.payload.get("run_id") != run_id
            or record.artifact_id != run_id
        ):
            raise ValueError("producer backtest run identity does not match the admitted job")


__all__ = [
    "ApprovedExperimentBacktestExecutor",
    "ApprovedExperimentBacktestProducer",
    "BacktestRunnerResearchProducer",
]
