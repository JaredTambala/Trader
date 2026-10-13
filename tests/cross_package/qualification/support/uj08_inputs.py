"""Real Data/implementation inputs for the governed experiment campaign."""

from __future__ import annotations
from datetime import datetime
from typing import Any
from trader_research.experiments import (
    register_risk_manager_implementation,
    register_strategy_implementation,
    validate_risk_manager_implementation,
    validate_strategy_implementation,
)
from trader_research.data import (
    DataInventoryRequest,
    DataQualityRequest,
    create_data_research_snapshot,
)
from trader_research.foundation import json_payload_hash
from trader_research.governance import (
    CostAssumption,
    DataRequirement,
    DatasetRole,
    ExperimentDesignRequest,
    InitialPortfolio,
    MaterialAssumption,
    ProtocolDataset,
    ProtocolRiskManager,
    ProtocolStrategy,
    ResearchObjective,
    ResearchObjectiveStatus,
    ArtifactReportRef,
)

from tests.cross_package.qualification.support.realistic_optimization_fixture import (
    BASE_STRATEGY_PARAMETERS,
    RISK_PARAMETERS,
    RISK_PARAMETER_SCHEMA,
    RISK_SOURCE,
    STRATEGY_PARAMETER_SCHEMA,
    STRATEGY_SOURCE,
)


def realistic_design(
    artifacts,
    event_store,
    manifest: dict[str, Any],
    quality: dict[str, Any],
) -> tuple[ResearchObjective, ExperimentDesignRequest]:
    """Build a fully admitted protocol over the deterministic replay fixture."""
    strategy_result = register_strategy_implementation(
        name="uj08-real-trailing-return",
        version="1",
        source_code=STRATEGY_SOURCE,
        factory_name="build_strategy",
        class_name="TrailingReturnTransitionStrategy",
        parameter_schema=STRATEGY_PARAMETER_SCHEMA,
        authoring_origin="uj08_qualification",
        capabilities=["multi_asset", "event_store_bars"],
        artifact_store=artifacts,
    )
    assert strategy_result.ok is True, strategy_result.errors
    strategy = artifacts.load_artifact_record(
        "implementation_version",
        strategy_result.data["implementation_version"]["implementation_version_id"],
    )
    strategy_validation = validate_strategy_implementation(
        implementation_version_id=strategy.artifact_id,
        fixture_parameters=BASE_STRATEGY_PARAMETERS,
        artifact_store=artifacts,
    )
    assert strategy_validation.ok is True, strategy_validation.errors

    risk_result = register_risk_manager_implementation(
        name="uj08-real-entry-limit",
        version="1",
        source_code=RISK_SOURCE,
        factory_name="build_risk_manager",
        class_name="EntryQuantityLimitRiskManager",
        parameter_schema=RISK_PARAMETER_SCHEMA,
        authoring_origin="uj08_qualification",
        capabilities=["entry_quantity_limit"],
        artifact_store=artifacts,
    )
    assert risk_result.ok is True, risk_result.errors
    risk = artifacts.load_artifact_record(
        "implementation_version",
        risk_result.data["implementation_version"]["implementation_version_id"],
    )
    risk_validation = validate_risk_manager_implementation(
        implementation_version_id=risk.artifact_id,
        fixture_parameters=RISK_PARAMETERS,
        artifact_store=artifacts,
    )
    assert risk_validation.ok is True, risk_validation.errors

    manifest_window = manifest.get("time_range") or manifest.get("requested_window")
    if not isinstance(manifest_window, dict):
        raise AssertionError(
            "fixture manifest must publish its qualified replay window"
        )
    snapshot_start = datetime.fromisoformat(
        str(manifest_window["start"]).replace("Z", "+00:00")
    )
    snapshot_end = datetime.fromisoformat(
        str(manifest_window["end"]).replace("Z", "+00:00")
    )
    snapshot = create_data_research_snapshot(
        event_store=event_store,
        inventory_request=DataInventoryRequest(
            symbols=tuple(str(item) for item in manifest["symbols"]),
            asset_class=str(manifest["asset_class"]),
            timeframe=str(manifest["timeframe"]),
            start=snapshot_start,
            end=snapshot_end,
        ),
        quality_request=DataQualityRequest(
            symbols=tuple(str(item) for item in manifest["symbols"]),
            asset_class=str(manifest["asset_class"]),
            timeframe=str(manifest["timeframe"]),
            start=snapshot_start,
            end=snapshot_end,
        ),
        requested_by="uj08-data-snapshot",
        actor="Data Agent",
        artifact_store=artifacts,
    )
    assert snapshot.ok is True, snapshot.errors
    manifest_record = artifacts.load_artifact_record(
        "dataset_manifest", snapshot.artifacts["dataset_manifest"]["metadata"]["id"]
    )
    quality_record = artifacts.load_artifact_record(
        "data_quality_report",
        snapshot.artifacts["data_quality_report"]["metadata"]["id"],
    )
    requirement = DataRequirement(
        symbols=tuple(str(item) for item in manifest["symbols"]),
        asset_class=str(manifest["asset_class"]),
        timeframe=str(manifest["timeframe"]),
        start=str(manifest_window["start"]),
        end=str(manifest_window["end"]),
        source=str(manifest.get("source_filter"))
        if manifest.get("source_filter")
        else None,
    )
    strategy_ref = _pinned_ref(strategy)
    risk_ref = _pinned_ref(risk)
    design = ExperimentDesignRequest(
        strategy=ProtocolStrategy(
            implementation_ref=strategy_ref,
            parameters=BASE_STRATEGY_PARAMETERS,
            portfolio_mode="multi_asset",
        ),
        risk_managers=(
            ProtocolRiskManager(
                implementation_ref=risk_ref,
                parameters=RISK_PARAMETERS,
            ),
        ),
        datasets=(
            ProtocolDataset(
                requirement_id="baseline",
                role=DatasetRole.BASELINE,
                requirement=requirement,
                dataset_manifest_ref=_pinned_ref(manifest_record),
                data_quality_report_ref=_pinned_ref(quality_record),
            ),
        ),
        costs=(CostAssumption(name="commission", value=0.25, unit="USD"),),
        initial_portfolio=InitialPortfolio(cash=100_000.0, currency="USD"),
        robustness_requirements=(),
        evaluation_questions=("Does the admitted strategy replay deterministically?",),
        falsification_criteria=(
            "Reject when the qualified replay cannot be completed.",
        ),
        material_assumptions=(
            MaterialAssumption(
                assumption_id="commission",
                category="cost",
                statement="Use the declared fixed commission.",
                value={"fixed_per_order": 0.25, "unit": "USD"},
            ),
        ),
        requested_approver="operator:jared",
        deterministic_seed=5701,
        max_runs=48,
        log_cycle_details=False,
        runtime_limits={"fixture": "uj08-real", "bounded": True},
        optimizer_profile="builtin_random",
    )
    objective = ResearchObjective(
        objective_id="uj08-real-objective",
        statement="Qualify the approved strategy against the retained replay fixture.",
        success_criteria=("Retain deterministic runner evidence.",),
        requested_by="operator:jared",
        actor="operator:jared",
        supplied_artifact_refs=(strategy_ref, risk_ref),
        status=ResearchObjectiveStatus.APPROVED,
    )
    return objective, design


def _pinned_ref(record) -> ArtifactReportRef:
    """Build an exact digest-pinned research reference."""
    return ArtifactReportRef(
        artifact_id=record.artifact_id,
        artifact_type=record.artifact_type,
        domain_owner=record.domain_owner,
        uri=record.uri,
        metadata={"payload_sha256": json_payload_hash(record.payload)},
    )
