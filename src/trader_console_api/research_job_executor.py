"""Resolve approved durable jobs into canonical validated backtest execution.

The worker owns leases and outcomes. This adapter rereads approval and pinned
inputs, builds real strategy/risk/backtest specifications, and delegates to the
research-owned runner service. It never fabricates specification identities.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from trader.config import Config
from trader.event_store import EventStore
from trader_research.experiments import (
    ExperimentJobRequest,
    create_backtest_specification,
    create_risk_stack_specification,
    create_strategy_specification,
    run_backtest_specification,
    validate_backtest_specification,
    validate_risk_manager_implementation,
    validate_risk_stack_specification,
    validate_strategy_implementation,
    validate_strategy_specification,
)
from trader_research.foundation import (
    ApplicationResult,
    ContextualResearchArtifactStore,
    ResearchArtifactStore,
    ResearchArtifactStoreError,
    json_payload_hash,
    parse_research_artifact_uri,
)
from trader_research.governance import (
    BACKTEST_RUN,
    DATASET_MANIFEST,
    DATA_QUALITY_REPORT,
    EXPERIMENT_JOB_REQUEST,
    EXPERIMENT_PROTOCOL,
    EXPERIMENT_PROTOCOL_PROPOSAL,
    ArtifactReportRef,
    CostAssumption,
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
    """Producer invoked only after request, approval, and input rereads."""

    async def execute(
        self,
        request: ExperimentJobRequest,
        protocol: ExperimentProtocol,
        *,
        run_id: str,
        progress: ResearchJobProgressSink,
    ) -> ResearchJobExecutionOutcome:
        """Run an approved backtest and return canonical child references."""


@dataclass(frozen=True)
class BacktestRunnerResearchProducer:
    """Compile pinned inputs into validated specifications and execute them.

    Attributes:
        artifact_store: Canonical input and evidence persistence.
        config: Core configuration supplied by worker composition.
        event_store: Qualified replay bars supplied by worker composition.
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
        """Execute passed specifications under the worker's stable run ID."""
        store = ContextualResearchArtifactStore(
            self.artifact_store, requested_by=request.requested_by, actor=request.actor
        )
        validation_id = await asyncio.to_thread(
            _compile_backtest, store, request, protocol
        )
        await progress(None)
        loop = asyncio.get_running_loop()

        def emit_progress(processed: int, total: int, last_ts: datetime | None) -> None:
            """Renew the durable lease from the synchronous runner thread."""
            del processed, total

            async def notify() -> None:
                await progress(last_ts)

            asyncio.run_coroutine_threadsafe(notify(), loop).result()

        try:
            result = await asyncio.to_thread(
                run_backtest_specification,
                event_store=self.event_store,
                config=self.config,
                backtest_specification_validation_ref=validation_id,
                artifact_store=store,
                run_id=run_id,
                progress_callback=emit_progress,
            )
        except Exception as exc:
            raise AmbiguousExecutionError(
                "The canonical backtest service returned no trustworthy execution outcome"
            ) from exc
        if not result.ok and not result.artifacts:
            codes = {issue["code"] for issue in result.errors}
            if codes.intersection(
                {
                    "backtest_run_persistence_failed",
                    "backtest_specification_execution_ambiguous",
                }
            ):
                raise AmbiguousExecutionError(str(result.errors))
            raise ValueError(str(result.errors))
        try:
            record = store.load_artifact_record(BACKTEST_RUN, run_id)
        except ResearchArtifactStoreError as exc:
            raise AmbiguousExecutionError(
                "The canonical backtest receipt cannot be reloaded after execution"
            ) from exc
        reference = ArtifactReportRef(
            artifact_id=record.artifact_id,
            artifact_type=record.artifact_type,
            domain_owner=record.domain_owner,
            uri=record.uri,
            metadata={"payload_sha256": json_payload_hash(record.payload)},
        )
        return ResearchJobExecutionOutcome(
            status="succeeded" if result.ok else "partial",
            produced_artifact_refs=(reference,),
            warnings=tuple(
                ResearchIssue(code="backtest_warning", message=str(warning))
                for warning in record.payload.get("warnings", ())
            ),
            blockers=()
            if result.ok
            else (
                ResearchIssue(
                    code="backtest_replay_incomplete",
                    message="The canonical runner did not complete every replay cycle.",
                    details={"run_id": run_id},
                ),
            ),
        )


def _result_data(result: ApplicationResult, name: str) -> Mapping[str, Any]:
    """Require a successful canonical producer result before consuming it."""
    if not result.ok:
        raise ValueError(f"{result.operation}: {result.errors}")
    value = result.data[name]
    if not isinstance(value, Mapping):
        raise ValueError(f"{result.operation} returned invalid {name}")
    return value


def _compile_backtest(
    store: ResearchArtifactStore,
    request: ExperimentJobRequest,
    protocol: ExperimentProtocol,
) -> str:
    """Build genuine passed specification lineage from exact approved inputs."""
    dataset = _primary_dataset(protocol.datasets)
    manifest = _load_pinned_record(
        store, dataset.dataset_manifest_ref, expected_type=DATASET_MANIFEST
    )
    quality = _load_pinned_record(
        store, dataset.data_quality_report_ref, expected_type=DATA_QUALITY_REPORT
    )
    strategy = protocol.strategy
    _load_pinned_record(
        store, strategy.implementation_ref, expected_type="implementation_version"
    )
    implementation = _result_data(
        validate_strategy_implementation(
            implementation_version_id=strategy.implementation_ref.artifact_id,
            fixture_parameters=strategy.parameters,
            artifact_store=store,
        ),
        "implementation_validation_report",
    )
    specification = _result_data(
        create_strategy_specification(
            implementation_validation_ref=str(implementation["validation_id"]),
            parameters=strategy.parameters,
            sizing=strategy.sizing,
            portfolio_mode=strategy.portfolio_mode,
            required_runtime_context=strategy.required_runtime_context,
            execution_assumptions=strategy.execution_assumptions,
            tunable_fields=list(strategy.tunable_fields),
            provenance_refs=(
                *strategy.provenance_refs,
                request.approved_protocol_ref.to_dict(),
            ),
            prediction_bindings=strategy.prediction_bindings,
            artifact_store=store,
        ),
        "strategy_specification",
    )
    strategy_validation = _result_data(
        validate_strategy_specification(
            strategy_specification_id=str(specification["strategy_specification_id"]),
            artifact_store=store,
        ),
        "strategy_specification_validation_report",
    )
    managers = []
    for manager in protocol.risk_managers:
        _load_pinned_record(
            store, manager.implementation_ref, expected_type="implementation_version"
        )
        validation = _result_data(
            validate_risk_manager_implementation(
                implementation_version_id=manager.implementation_ref.artifact_id,
                fixture_parameters=manager.parameters,
                artifact_store=store,
            ),
            "implementation_validation_report",
        )
        managers.append(
            {
                "implementation_validation_ref": validation["validation_id"],
                "parameters": dict(manager.parameters),
                "tunable_fields": list(manager.tunable_fields),
            }
        )
    risk_validation_id = None
    if managers:
        risk = _result_data(
            create_risk_stack_specification(
                risk_managers=managers,
                provenance_refs=(request.approved_protocol_ref.to_dict(),),
                artifact_store=store,
            ),
            "risk_stack_specification",
        )
        risk_validation = _result_data(
            validate_risk_stack_specification(
                risk_stack_specification_id=str(risk["risk_stack_specification_id"]),
                artifact_store=store,
            ),
            "risk_stack_specification_validation_report",
        )
        risk_validation_id = str(risk_validation["validation_id"])
    specification = _result_data(
        create_backtest_specification(
            strategy_specification_validation_ref=str(
                strategy_validation["validation_id"]
            ),
            risk_stack_specification_validation_ref=risk_validation_id,
            dataset_manifest=manifest.payload,
            data_quality_report=quality.payload,
            assumptions=_protocol_assumptions(
                strategy.execution_assumptions, protocol.costs
            ),
            initial_cash=protocol.initial_portfolio.cash,
            initial_positions=[
                {
                    "symbol": item.symbol,
                    "qty": item.quantity,
                    "avg_price": item.avg_price,
                }
                for item in protocol.initial_portfolio.positions
            ],
            deterministic_seed=protocol.deterministic_seed,
            max_runs=protocol.max_runs,
            log_cycle_details=protocol.log_cycle_details,
            runtime_limits={
                **protocol.runtime_limits,
                "experiment_job_request_ref": f"research://postgres/experiment_job_request/{request.request_id}",
                "experiment_job_request_sha256": json_payload_hash(request.to_dict()),
            },
            artifact_store=store,
        ),
        "backtest_specification",
    )
    validated = _result_data(
        validate_backtest_specification(
            backtest_specification_id=str(specification["backtest_specification_id"]),
            artifact_store=store,
        ),
        "backtest_specification_validation_report",
    )
    return str(validated["validation_id"])


def _primary_dataset(datasets: Sequence[ProtocolDataset]) -> ProtocolDataset:
    """Require one declared baseline or selection scope for this producer."""
    candidates = [
        item for item in datasets if item.role.value in {"baseline", "selection"}
    ]
    if len(candidates) != 1:
        raise ValueError(
            "approved backtest requires exactly one baseline or selection dataset"
        )
    return candidates[0]


def _protocol_assumptions(
    execution_assumptions: Mapping[str, Any], costs: Sequence[CostAssumption]
) -> dict[str, Any]:
    """Reject cost semantics that cannot be represented by the core runner."""
    values = dict(execution_assumptions)
    for cost in costs:
        supported = {
            ("commission", "USD"): ("fees", "fixed_per_order"),
            ("commission", "bps"): ("fees", "bps"),
            ("slippage", "bps"): ("slippage", "bps"),
        }
        target = supported.get((cost.name, cost.unit))
        if target is None:
            raise ValueError(f"unsupported approved cost: {cost.name} ({cost.unit})")
        group, field = target
        existing = dict(values.get(group) or {})
        if field in existing and float(existing[field]) != float(cost.value):
            raise ValueError(
                f"approved cost conflicts with execution_assumptions.{group}.{field}"
            )
        existing[field] = float(cost.value)
        values[group] = existing
    return values


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
        try:
            _validate_producer_outcome(self.artifact_store, outcome, run_id=run_id)
        except (ValueError, ResearchArtifactStoreError) as exc:
            raise AmbiguousExecutionError(
                "Producer returned evidence that cannot be independently resolved"
            ) from exc
        if outcome.status == "succeeded" and not any(
            ref.artifact_type == BACKTEST_RUN for ref in outcome.produced_artifact_refs
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
        if reference.metadata.get("payload_sha256") != json_payload_hash(
            record.payload
        ):
            raise ValueError("producer artifact payload drifted")
        if reference.artifact_type == BACKTEST_RUN and (
            record.payload.get("run_id") != run_id or record.artifact_id != run_id
        ):
            raise ValueError(
                "producer backtest run identity does not match the admitted job"
            )


__all__ = [
    "ApprovedExperimentBacktestExecutor",
    "ApprovedExperimentBacktestProducer",
    "BacktestRunnerResearchProducer",
]
