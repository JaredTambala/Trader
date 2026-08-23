"""Contract and integration evidence for resumable research composition."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, cast

import anyio
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver
import pytest

from tests.support.duckdb_store import DuckDBEventStore
from tests.test_orchestration_execution import (
    RecordingMcpClient,
    SAMPLE_CSV,
    _config,
    _register_risk,
    _register_strategy,
)
from trader.market_data.sample import load_sample_market_data_csv
from trader_agents import (
    DATA_SPECIALIST_AUTHORITY,
    AcceptedSpecialistResult,
    CoordinationDecision,
    CoordinatorAction,
    DataSpecialistRequest,
    RegisteredSpecialistRoute,
    ResearchCompositionConflictError,
    ResearchCompositionRequest,
    SpecialistResult,
    SpecialistRouteCatalog,
    SpecialistRouteDescriptor,
    SpecialistTask,
    build_data_specialist_task,
    coordinate_research,
    research_composition_thread_config,
    run_research_composition,
    specialist_task_digest,
    validate_protocol_consumes_specialist_outputs,
)
from trader_mcp.constants import (
    DATA_CREATE_RESEARCH_SNAPSHOT_TOOL,
    DATA_DISCOVER_SYMBOLS_TOOL,
    RESEARCH_RECORD_WORKFLOW_OUTCOME_TOOL,
    RESEARCH_REGISTER_EXPERIMENT_WORKFLOW_TOOL,
)
from trader_mcp.environment import load_local_environment
from trader_mcp.server import create_server
from trader_research.foundation import InMemoryResearchArtifactStore
from trader_research.governance import (
    DATASET_MANIFEST,
    DATA_QUALITY_REPORT,
    ArtifactReportRef,
    DataRequirement,
    DatasetRole,
    ExperimentProtocol,
    ExperimentProtocolStatus,
    InitialPortfolio,
    ProtocolDataset,
    ProtocolRiskManager,
    ProtocolStrategy,
    ResearchObjective,
    ResearchObjectiveStatus,
    artifact_report_ref,
)


@dataclass(frozen=True)
class _UnusedRunner:
    async def run(self, task: SpecialistTask) -> SpecialistResult:
        raise AssertionError(f"route unexpectedly executed task {task.task_id}")


@dataclass(frozen=True)
class _UnusedMcpClient:
    async def call_tool(
        self,
        tool_name: str,
        arguments: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        raise AssertionError(f"unexpected MCP call: {tool_name} {arguments}")


@dataclass(frozen=True)
class PreparedComposition:
    """Real in-process dependencies for one composition acceptance path."""

    store: InMemoryResearchArtifactStore
    client: RecordingMcpClient
    request: ResearchCompositionRequest
    objective: ResearchObjective
    strategy_ref: ArtifactReportRef
    risk_ref: ArtifactReportRef


def test_coordinator_selects_only_one_registered_specialist_route() -> None:
    objective = _objective()
    task = _data_task(objective)
    catalog = SpecialistRouteCatalog((_route("1"),))

    coordination = coordinate_research(
        objective=objective,
        protocol=None,
        artifact_store=InMemoryResearchArtifactStore(),
        specialist_tasks=(task,),
        specialist_catalog=catalog,
    )

    assert (
        coordination.decision.action
        is CoordinatorAction.EXECUTE_REGISTERED_SPECIALIST_TASK
    )
    assert coordination.specialist_task == task
    assert coordination.decision.specialist_task_id == task.task_id
    assert coordination.decision.specialist_authority == DATA_SPECIALIST_AUTHORITY
    assert coordination.decision.specialist_task_digest == specialist_task_digest(task)
    assert coordination.decision.specialist_route_version == "1"
    assert coordination.compiled_workflow is None


def test_coordinator_reports_unavailable_and_ambiguous_specialist_routes() -> None:
    objective = _objective()
    task = _data_task(objective)

    unavailable = coordinate_research(
        objective=objective,
        protocol=None,
        artifact_store=InMemoryResearchArtifactStore(),
        specialist_tasks=(task,),
        specialist_catalog=SpecialistRouteCatalog(()),
    )
    ambiguous = coordinate_research(
        objective=objective,
        protocol=None,
        artifact_store=InMemoryResearchArtifactStore(),
        specialist_tasks=(task,),
        specialist_catalog=SpecialistRouteCatalog((_route("1"), _route("2"))),
    )

    assert unavailable.decision.action is CoordinatorAction.REQUEST_PREREQUISITE
    assert unavailable.decision.prerequisites[0].target == DATA_SPECIALIST_AUTHORITY
    assert ambiguous.decision.action is CoordinatorAction.BLOCK
    assert ambiguous.decision.blockers[0].code == "ambiguous_specialist_route"


def test_specialist_route_rejects_unknown_and_foreign_output_types() -> None:
    with pytest.raises(ValueError, match="unsupported artifact types"):
        SpecialistRouteDescriptor(
            authority_key=DATA_SPECIALIST_AUTHORITY,
            version="1",
            supported_output_types=("invented_artifact",),
        )
    with pytest.raises(ValueError, match="another domain"):
        SpecialistRouteDescriptor(
            authority_key=DATA_SPECIALIST_AUTHORITY,
            version="1",
            supported_output_types=("workflow_plan",),
        )


def test_specialist_coordination_decision_is_strict_and_mutually_exclusive() -> None:
    with pytest.raises(ValueError, match="unknown fields: tool_name"):
        CoordinationDecision.from_dict(
            {
                "action": "execute_registered_specialist_task",
                "objective_id": "objective_demo",
                "specialist_task_id": "task_demo",
                "specialist_authority": DATA_SPECIALIST_AUTHORITY,
                "specialist_task_digest": "digest",
                "specialist_route_version": "1",
                "tool_name": DATA_DISCOVER_SYMBOLS_TOOL,
            }
        )
    with pytest.raises(ValueError, match="cannot select a template"):
        CoordinationDecision(
            action=CoordinatorAction.EXECUTE_REGISTERED_SPECIALIST_TASK,
            objective_id="objective_demo",
            specialist_task_id="task_demo",
            specialist_authority=DATA_SPECIALIST_AUTHORITY,
            specialist_task_digest="digest",
            specialist_route_version="1",
            template_id="invented_template",
        )


def test_composition_request_rejects_unknown_fields_and_task_attribution() -> None:
    objective = _objective()
    task = _data_task(objective)
    payload = ResearchCompositionRequest(
        composition_id="composition_demo",
        objective=objective,
        specialist_tasks=(task,),
        requested_by="operator:test",
        actor="research_coordinator",
    ).to_dict()
    payload["tool_arguments"] = {"symbols": ["DEMO"]}

    with pytest.raises(ValueError, match="unknown fields: tool_arguments"):
        ResearchCompositionRequest.from_dict(payload)
    with pytest.raises(ValueError, match="requester must be composition_id"):
        ResearchCompositionRequest(
            composition_id="different_composition",
            objective=objective,
            specialist_tasks=(task,),
            requested_by="operator:test",
            actor="research_coordinator",
        )


def test_protocol_must_consume_accepted_data_refs() -> None:
    objective = _objective()
    task = _data_task(objective)
    missing_manifest = _ref(DATASET_MANIFEST, "missing_manifest")
    missing_quality = _ref(DATA_QUALITY_REPORT, "missing_quality")
    receipt = AcceptedSpecialistResult(
        task_id=task.task_id,
        authority_key=task.authority_key,
        task_digest=specialist_task_digest(task),
        route_version="1",
        result_digest="result_digest",
        artifact_refs=(missing_manifest, missing_quality),
        output_bindings={
            "dataset_manifest": (missing_manifest.uri,),
            "data_quality_report": (missing_quality.uri,),
        },
    )
    other_manifest = _ref(DATASET_MANIFEST, "other_manifest")
    other_quality = _ref(DATA_QUALITY_REPORT, "other_quality")
    protocol = _protocol(
        objective=objective,
        strategy_ref=_ref("implementation_version", "strategy"),
        risk_ref=_ref("implementation_version", "risk"),
        manifest_ref=other_manifest,
        quality_ref=other_quality,
        status=ExperimentProtocolStatus.APPROVED,
    )

    with pytest.raises(ValueError, match="does not consume required Data"):
        validate_protocol_consumes_specialist_outputs(
            protocol=protocol,
            accepted_results=(receipt,),
        )


def test_composition_fails_when_resumed_beyond_transition_budget() -> None:
    async def _run() -> None:
        objective = _objective()
        request = ResearchCompositionRequest(
            composition_id="composition_transition_limit",
            objective=objective,
            specialist_tasks=(),
            requested_by="operator:test",
            actor="research_coordinator",
        )
        saver = InMemorySaver()
        store = InMemoryResearchArtifactStore()
        client = _UnusedMcpClient()
        awaiting_protocol = await run_research_composition(
            request=request,
            protocol=None,
            tool_client=client,
            artifact_store=store,
            checkpointer=saver,
            max_transitions=1,
        )
        assert awaiting_protocol["status"] == "awaiting_prerequisite"

        over_budget = await run_research_composition(
            request=request,
            protocol=_protocol(
                objective=objective,
                strategy_ref=_ref("implementation_version", "strategy"),
                risk_ref=_ref("implementation_version", "risk"),
                manifest_ref=_ref(DATASET_MANIFEST, "manifest"),
                quality_ref=_ref(DATA_QUALITY_REPORT, "quality"),
                status=ExperimentProtocolStatus.PROPOSED,
            ),
            tool_client=client,
            artifact_store=store,
            checkpointer=saver,
            max_transitions=1,
        )

        assert over_budget["status"] == "failed"
        assert over_budget["errors"][0]["code"] == (
            "composition_transition_limit_exceeded"
        )

    anyio.run(_run)


def test_real_data_to_protocol_to_terminal_workflow_replays_nothing(
    tmp_path: Path,
) -> None:
    async def _run() -> None:
        prepared = await _prepare_composition(tmp_path)
        store = prepared.store
        client = prepared.client
        request = prepared.request
        saver = InMemorySaver()

        awaiting_protocol = await run_research_composition(
            request=request,
            protocol=None,
            tool_client=client,
            artifact_store=store,
            checkpointer=saver,
        )

        assert awaiting_protocol["status"] == "awaiting_prerequisite"
        assert awaiting_protocol["prerequisites"][0]["target"] == (
            "experiment_protocol"
        )
        assert [name for name, _ in client.calls] == [
            DATA_DISCOVER_SYMBOLS_TOOL,
            DATA_CREATE_RESEARCH_SNAPSHOT_TOOL,
        ]
        receipt = AcceptedSpecialistResult.from_dict(
            awaiting_protocol["accepted_specialist_results"][0]
        )
        refs = {item.artifact_type: item for item in receipt.artifact_refs}
        with pytest.raises(
            ResearchCompositionConflictError,
            match="checkpoint evidence drift",
        ):
            await run_research_composition(
                request=request,
                protocol=None,
                tool_client=client,
                artifact_store=store,
                checkpointer=saver,
                specialist_catalog=SpecialistRouteCatalog((_route("2"),)),
            )
        proposed = _protocol(
            objective=prepared.objective,
            strategy_ref=prepared.strategy_ref,
            risk_ref=prepared.risk_ref,
            manifest_ref=refs[DATASET_MANIFEST],
            quality_ref=refs[DATA_QUALITY_REPORT],
            status=ExperimentProtocolStatus.PROPOSED,
        )
        approved = replace(proposed, status=ExperimentProtocolStatus.APPROVED)
        awaiting_approval = await run_research_composition(
            request=request,
            protocol=proposed,
            tool_client=client,
            artifact_store=store,
            checkpointer=saver,
        )
        assert awaiting_approval["status"] == "awaiting_approval"
        assert len(client.calls) == 2

        completed = await run_research_composition(
            request=request,
            protocol=approved,
            tool_client=client,
            artifact_store=store,
            checkpointer=saver,
        )

        assert completed["status"] == "completed"
        assert completed["decision"]["action"] == "report_terminal_state"
        assert completed["outcome_ref"]["artifact_type"] == "workflow_outcome"
        tool_names = [name for name, _ in client.calls]
        assert tool_names.count(DATA_CREATE_RESEARCH_SNAPSHOT_TOOL) == 1
        assert tool_names.count(RESEARCH_REGISTER_EXPERIMENT_WORKFLOW_TOOL) == 1
        assert tool_names.count(RESEARCH_RECORD_WORKFLOW_OUTCOME_TOOL) == 1
        record_count = len(store.list_artifacts())

        replay = await run_research_composition(
            request=request,
            protocol=approved,
            tool_client=client,
            artifact_store=store,
            checkpointer=saver,
        )

        assert replay == completed
        assert [name for name, _ in client.calls] == tool_names
        assert len(store.list_artifacts()) == record_count
        checkpoint = await saver.aget_tuple(
            cast(
                RunnableConfig,
                research_composition_thread_config(request.composition_id),
            )
        )
        assert checkpoint is not None
        checkpoint_text = str(checkpoint.checkpoint["channel_values"])
        assert "structuredContent" not in checkpoint_text
        assert "source_code" not in checkpoint_text
        assert "tool_arguments" not in checkpoint_text

        changed_request = replace(request, requested_by="operator:changed")
        with pytest.raises(ResearchCompositionConflictError):
            await run_research_composition(
                request=changed_request,
                protocol=approved,
                tool_client=client,
                artifact_store=store,
                checkpointer=saver,
            )
        with pytest.raises(
            ResearchCompositionConflictError,
            match="protocol design drift",
        ):
            await run_research_composition(
                request=request,
                protocol=replace(approved, max_runs=4),
                tool_client=client,
                artifact_store=store,
                checkpointer=saver,
            )

        manifest_record = store.load_artifact_record(
            DATASET_MANIFEST,
            refs[DATASET_MANIFEST].artifact_id,
        )
        store.save_artifact(
            artifact_type=manifest_record.artifact_type,
            artifact_id=manifest_record.artifact_id,
            domain_owner=manifest_record.domain_owner,
            producer_tool=manifest_record.producer_tool,
            payload={**manifest_record.payload, "drifted": True},
            requested_by=manifest_record.requested_by,
            actor=manifest_record.actor,
            status=manifest_record.status,
            metadata=manifest_record.metadata,
            source_hash=manifest_record.source_hash,
        )
        with pytest.raises(
            ResearchCompositionConflictError,
            match="canonical composition ref payload drift",
        ):
            await run_research_composition(
                request=request,
                protocol=approved,
                tool_client=client,
                artifact_store=store,
                checkpointer=saver,
            )

    anyio.run(_run)


async def _prepare_composition(tmp_path: Path) -> PreparedComposition:
    store = InMemoryResearchArtifactStore()
    event_store = DuckDBEventStore(str(tmp_path / "events.duckdb"))
    load_sample_market_data_csv(event_store, SAMPLE_CSV)
    server = create_server(
        replace(
            load_local_environment("env.template"),
            allow_backtests=True,
        ),
        event_store_provider=lambda: event_store,
        backtest_config_provider=lambda: _config(tmp_path),
        research_artifact_store_provider=lambda: store,
    )
    strategy_ref = await _register_strategy(server)
    risk_ref = await _register_risk(server)
    objective = _objective(supplied_refs=(strategy_ref, risk_ref))
    request = ResearchCompositionRequest(
        composition_id="composition_full_path",
        objective=objective,
        specialist_tasks=(_data_task(objective, "composition_full_path"),),
        requested_by="operator:test",
        actor="research_coordinator",
    )
    return PreparedComposition(
        store=store,
        client=RecordingMcpClient(server),
        request=request,
        objective=objective,
        strategy_ref=strategy_ref,
        risk_ref=risk_ref,
    )


def _objective(
    *,
    supplied_refs: tuple[ArtifactReportRef, ...] = (),
) -> ResearchObjective:
    return ResearchObjective(
        objective_id="objective_composition_demo",
        statement="Evaluate the supplied strategy and risk implementation.",
        success_criteria=("Produce canonical research evidence.",),
        requested_by="operator:test",
        actor="operator:test",
        supplied_artifact_refs=supplied_refs,
        status=ResearchObjectiveStatus.APPROVED,
    )


def _data_task(
    objective: ResearchObjective,
    composition_id: str = "composition_demo",
) -> SpecialistTask:
    return build_data_specialist_task(
        request=DataSpecialistRequest(data_requirement=_data_requirement()),
        objective=objective,
        requested_by=composition_id,
        actor="research_coordinator",
        permit_local_mutation=True,
    )


def _route(version: str) -> RegisteredSpecialistRoute:
    return RegisteredSpecialistRoute(
        descriptor=SpecialistRouteDescriptor(
            authority_key=DATA_SPECIALIST_AUTHORITY,
            version=version,
            supported_output_types=(DATASET_MANIFEST, DATA_QUALITY_REPORT),
        ),
        runner=_UnusedRunner(),
    )


def _protocol(
    *,
    objective: ResearchObjective,
    strategy_ref: ArtifactReportRef,
    risk_ref: ArtifactReportRef,
    manifest_ref: ArtifactReportRef,
    quality_ref: ArtifactReportRef,
    status: ExperimentProtocolStatus,
) -> ExperimentProtocol:
    return ExperimentProtocol(
        protocol_id="protocol_composition_demo",
        objective_id=objective.objective_id,
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
                requirement=_data_requirement(),
                dataset_manifest_ref=manifest_ref,
                data_quality_report_ref=quality_ref,
            ),
        ),
        costs=(),
        initial_portfolio=InitialPortfolio(cash=100_000.0, currency="USD"),
        robustness_requirements=(),
        evaluation_questions=("Does the evidence support the supplied code?",),
        falsification_criteria=("Block on invalid evidence.",),
        material_assumptions=(),
        approvals=(),
        requested_by=objective.objective_id,
        proposed_by="experiment_design_agent",
        max_runs=3,
        status=status,
    )


def _data_requirement() -> DataRequirement:
    return DataRequirement(
        symbols=("DEMO",),
        asset_class="stocks",
        timeframe="1Min",
        start="2026-01-20T12:00:00Z",
        end="2026-01-20T12:11:00Z",
    )


def _ref(artifact_type: str, artifact_id: str) -> ArtifactReportRef:
    return artifact_report_ref(artifact_type, artifact_id)
