"""Governance contracts for experiment protocol design and approval.

Subject: Strict design requests, immutable protocol proposals, approvals, and canonical-input authority.
Level: In-process governance and artifact contract.
Collaborators: Governance domain values and the in-memory canonical research artifact store.
Guarantees: Proposals pin exact inputs, replay idempotently, and reject approval or evidence drift.
Non-goals: Experiment execution, parameter optimisation, implementation catalogues, Postgres, or agents.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from trader_research.foundation import (
    EXPERIMENTS_DOMAIN_OWNER,
    InMemoryResearchArtifactStore,
    json_payload_hash,
)
from trader_research.governance import (
    DATASET_MANIFEST,
    DATA_QUALITY_REPORT,
    EXPERIMENT_DESIGN_AGENT_OWNER,
    EXPERIMENT_PROTOCOL_PROPOSAL,
    ApprovalStatus,
    CostAssumption,
    DataRequirement,
    DatasetRole,
    ExperimentDesignRequest,
    ExperimentProtocolProposal,
    ExperimentProtocolStatus,
    InitialPortfolio,
    MaterialAssumption,
    ProtocolDataset,
    ProtocolRiskManager,
    ProtocolStrategy,
    ResearchObjective,
    ResearchObjectiveStatus,
    apply_experiment_protocol_approvals,
    artifact_report_ref,
    create_experiment_protocol_proposal,
)
from trader_research.governance.artifacts import IMPLEMENTATION_VERSION


def test_design_request_is_strict_and_requires_explicit_material_choices() -> None:
    """Design requests reject unknown fields and require every material execution choice."""
    store, objective, design = _prepared_design()
    del store, objective
    payload = design.to_dict()
    payload["unexpected"] = True
    with pytest.raises(ValueError, match="unknown fields"):
        ExperimentDesignRequest.from_dict(payload)

    without_costs = {**design.to_dict(), "costs": []}
    with pytest.raises(ValueError, match="costs must be explicit"):
        ExperimentDesignRequest.from_dict(without_costs)

    missing_limit = design.to_dict()
    missing_limit.pop("max_runs")
    with pytest.raises(ValueError, match="missing fields: max_runs"):
        ExperimentDesignRequest.from_dict(missing_limit)


def test_proposal_persistence_pins_inputs_and_replays_idempotently() -> None:
    """Protocol proposals pin canonical inputs and replay with stable identity."""
    store, objective, design = _prepared_design()
    first = create_experiment_protocol_proposal(
        objective=objective.to_dict(),
        design_request=design.to_dict(),
        task_id="design_task_1",
        requested_by="composition_1",
        actor=EXPERIMENT_DESIGN_AGENT_OWNER,
        artifact_store=store,
    )
    second = create_experiment_protocol_proposal(
        objective=objective.to_dict(),
        design_request=design.to_dict(),
        task_id="design_task_1",
        requested_by="composition_1",
        actor=EXPERIMENT_DESIGN_AGENT_OWNER,
        artifact_store=store,
    )

    assert first.ok is True
    assert second.ok is True
    assert first.data == second.data
    proposal = ExperimentProtocolProposal.from_dict(
        first.data["experiment_protocol_proposal"]
    )
    assert proposal.protocol.status is ExperimentProtocolStatus.PROPOSED
    assert {item.status for item in proposal.protocol.approvals} == {
        ApprovalStatus.REQUESTED
    }
    assert all(item.metadata["payload_sha256"] for item in proposal.input_refs)
    record = store.load_artifact_record(
        EXPERIMENT_PROTOCOL_PROPOSAL,
        proposal.proposal_id,
    )
    assert record.requested_by == "composition_1"
    assert record.actor == EXPERIMENT_DESIGN_AGENT_OWNER


def test_operator_approval_cannot_change_proposal_identity() -> None:
    """Approval transitions cannot change the protocol subject selected for review."""
    store, objective, design = _prepared_design()
    result = create_experiment_protocol_proposal(
        objective=objective.to_dict(),
        design_request=design.to_dict(),
        task_id="design_task_approval",
        requested_by="composition_approval",
        actor=EXPERIMENT_DESIGN_AGENT_OWNER,
        artifact_store=store,
    )
    proposal = ExperimentProtocolProposal.from_dict(
        result.data["experiment_protocol_proposal"]
    )
    requested = proposal.protocol.approvals[0]
    decision = replace(
        requested,
        status=ApprovalStatus.APPROVED,
        decided_by="operator:jared",
        rationale="The declared zero-cost fixture is acceptable for this test.",
    )

    approved = apply_experiment_protocol_approvals(proposal, (decision,))
    assert approved.status is ExperimentProtocolStatus.APPROVED

    changed_subject = replace(decision, subject_id="another_protocol")
    with pytest.raises(ValueError, match="changed proposal subject_id"):
        apply_experiment_protocol_approvals(proposal, (changed_subject,))


def test_proposal_rejects_canonical_data_scope_drift() -> None:
    """Proposal creation rejects canonical dataset evidence whose declared scope has drifted."""
    store, objective, design = _prepared_design()
    manifest_ref = design.datasets[0].dataset_manifest_ref
    record = store.load_artifact_record(
        manifest_ref.artifact_type,
        manifest_ref.artifact_id,
    )
    store.save_artifact(
        artifact_type=record.artifact_type,
        artifact_id=record.artifact_id,
        domain_owner=record.domain_owner,
        producer_tool=record.producer_tool,
        requested_by=record.requested_by,
        actor=record.actor,
        status=record.status,
        metadata=record.metadata,
        payload={**record.payload, "symbols": ["DRIFT"]},
    )

    result = create_experiment_protocol_proposal(
        objective=objective.to_dict(),
        design_request=design.to_dict(),
        task_id="design_task_drift",
        requested_by="composition_drift",
        actor=EXPERIMENT_DESIGN_AGENT_OWNER,
        artifact_store=store,
    )
    assert result.ok is False
    assert "symbols do not match" in result.errors[0]["message"]


def test_proposal_rejects_canonical_input_producer_drift() -> None:
    """Proposal creation rejects canonical inputs persisted by an unauthorized producer."""
    store, objective, design = _prepared_design()
    strategy_ref = design.strategy.implementation_ref
    record = store.load_artifact_record(
        strategy_ref.artifact_type,
        strategy_ref.artifact_id,
    )
    store.save_artifact(
        artifact_type=record.artifact_type,
        artifact_id=record.artifact_id,
        domain_owner=record.domain_owner,
        producer_tool="forged_registration",
        status=record.status,
        payload=record.payload,
    )

    result = create_experiment_protocol_proposal(
        objective=objective.to_dict(),
        design_request=design.to_dict(),
        task_id="design_task_producer_drift",
        requested_by="composition_producer_drift",
        actor=EXPERIMENT_DESIGN_AGENT_OWNER,
        artifact_store=store,
    )

    assert result.ok is False
    assert "wrong producer" in result.errors[0]["message"]


def _prepared_design() -> tuple[
    InMemoryResearchArtifactStore,
    ResearchObjective,
    ExperimentDesignRequest,
]:
    store = InMemoryResearchArtifactStore()
    strategy_ref = _implementation(store, "strategy_v1", "strategy")
    risk_ref = _implementation(store, "risk_v1", "risk_manager")
    manifest_ref, quality_ref = _data_evidence(store)
    objective = ResearchObjective(
        objective_id="objective_design",
        statement="Evaluate supplied deterministic behavior.",
        success_criteria=("Produce reproducible evidence.",),
        supplied_artifact_refs=(strategy_ref, risk_ref),
        requested_by="operator:jared",
        actor="operator:jared",
        status=ResearchObjectiveStatus.APPROVED,
    )
    requirement = _requirement()
    design = ExperimentDesignRequest(
        strategy=ProtocolStrategy(
            implementation_ref=strategy_ref,
            parameters={"period": 2},
        ),
        risk_managers=(
            ProtocolRiskManager(
                implementation_ref=risk_ref,
                parameters={"max_orders": 10},
            ),
        ),
        datasets=(
            ProtocolDataset(
                requirement_id="baseline",
                role=DatasetRole.BASELINE,
                requirement=requirement,
                dataset_manifest_ref=manifest_ref,
                data_quality_report_ref=quality_ref,
            ),
        ),
        costs=(CostAssumption(name="commission", value=0.0, unit="USD"),),
        initial_portfolio=InitialPortfolio(cash=100_000.0, currency="USD"),
        robustness_requirements=(),
        evaluation_questions=("Does the supplied behavior remain valid?",),
        falsification_criteria=("Block on invalid canonical evidence.",),
        material_assumptions=(
            MaterialAssumption(
                assumption_id="zero_commission",
                category="cost",
                statement="Use zero commission for the bounded fixture.",
                value={"commission": 0.0, "unit": "USD"},
            ),
        ),
        requested_approver="operator:jared",
        deterministic_seed=7,
        max_runs=3,
        log_cycle_details=False,
        runtime_limits={"max_bars": 1_000},
        optimizer_profile="builtin_random",
    )
    return store, objective, design


def _implementation(
    store: InMemoryResearchArtifactStore,
    artifact_id: str,
    kind: str,
):
    payload = {
        "artifact_type": IMPLEMENTATION_VERSION,
        "implementation_version_id": artifact_id,
        "implementation_kind": kind,
        "status": "registered",
    }
    store.save_artifact(
        artifact_type=IMPLEMENTATION_VERSION,
        artifact_id=artifact_id,
        domain_owner=EXPERIMENTS_DOMAIN_OWNER,
        producer_tool=f"research_register_{kind}_implementation",
        payload=payload,
        status="registered",
    )
    return artifact_report_ref(IMPLEMENTATION_VERSION, artifact_id)


def _data_evidence(store: InMemoryResearchArtifactStore):
    requirement = _requirement()
    base = {
        "symbols": list(requirement.symbols),
        "asset_class": requirement.asset_class,
        "timeframe": requirement.timeframe,
        "source_filter": requirement.source,
        "requested_window": {
            "start": requirement.start,
            "end": requirement.end,
        },
        "dataset_id": "dataset_design",
        "complete": True,
        "status": "captured",
    }
    manifest = store.save_artifact(
        artifact_type=DATASET_MANIFEST,
        artifact_id="manifest_design",
        domain_owner="Data",
        producer_tool="data_create_research_snapshot",
        requested_by="data_snapshot",
        actor="Data Agent",
        payload={"artifact_type": DATASET_MANIFEST, **base},
        status="captured",
    )
    quality = store.save_artifact(
        artifact_type=DATA_QUALITY_REPORT,
        artifact_id="quality_design",
        domain_owner="Data",
        producer_tool="data_create_research_snapshot",
        requested_by="data_snapshot",
        actor="Data Agent",
        payload={"artifact_type": DATA_QUALITY_REPORT, **base},
        status="captured",
        metadata={"dataset_manifest_artifact_id": manifest.artifact_id},
    )
    manifest_ref = artifact_report_ref(DATASET_MANIFEST, manifest.artifact_id)
    quality_ref = artifact_report_ref(DATA_QUALITY_REPORT, quality.artifact_id)
    assert json_payload_hash(manifest.payload)
    return manifest_ref, quality_ref


def _requirement() -> DataRequirement:
    return DataRequirement(
        symbols=("DEMO",),
        asset_class="stocks",
        timeframe="1Min",
        start="2026-01-20T12:00:00Z",
        end="2026-01-20T12:11:00Z",
    )
