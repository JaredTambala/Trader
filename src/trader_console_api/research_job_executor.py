"""Fail-closed adapter from an admitted ResearchJob to a backtest producer.

The durable worker owns leases and terminal state. This adapter owns the
research-to-producer boundary: it reloads the immutable job request, proposal,
and approved protocol, revalidates their pinned inputs, and only then invokes
the injected canonical backtest producer. No copied protocol payload or stale
worker memory can authorize execution.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from trader_research.experiments import ExperimentJobRequest
from trader_research.foundation import (
    ResearchArtifactStore,
    ResearchArtifactStoreError,
    json_payload_hash,
    parse_research_artifact_uri,
)
from trader_research.governance import (
    BACKTEST_RUN,
    EXPERIMENT_JOB_REQUEST,
    EXPERIMENT_PROTOCOL,
    EXPERIMENT_PROTOCOL_PROPOSAL,
    ArtifactReportRef,
    ExperimentProtocol,
    ExperimentProtocolProposal,
    ResearchJob,
    ResearchIssue,
    apply_experiment_protocol_approvals,
    revalidate_experiment_protocol_inputs,
)

from .worker import (
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
        _validate_producer_outcome(self.artifact_store, outcome)
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


__all__ = [
    "ApprovedExperimentBacktestExecutor",
    "ApprovedExperimentBacktestProducer",
]
