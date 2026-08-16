"""End-to-end evidence for deterministic implementation-to-evidence workflows."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Mapping

import anyio
from langgraph.checkpoint.memory import InMemorySaver

from tests.support.duckdb_store import DuckDBEventStore
from trader.config import Config
from trader.market_data.sample import load_sample_market_data_csv
from trader_agents import (
    WORKFLOW_EXECUTOR_ACTOR,
    WorkflowExecutionInterrupted,
    compile_supplied_implementation_workflow,
    execute_compiled_research_workflow,
)
from trader_mcp.constants import (
    DATA_CREATE_RESEARCH_SNAPSHOT_TOOL,
    RESEARCH_RECORD_WORKFLOW_OUTCOME_TOOL,
    RESEARCH_REGISTER_EXPERIMENT_WORKFLOW_TOOL,
    RESEARCH_REGISTER_OPTIMIZATION_OBJECTIVE_TOOL,
    RESEARCH_REGISTER_RISK_MANAGER_IMPLEMENTATION_TOOL,
    RESEARCH_REGISTER_STRATEGY_IMPLEMENTATION_TOOL,
    RESEARCH_RUN_BACKTEST_SPECIFICATION_TOOL,
    RESEARCH_RUN_PARAMETER_OPTIMIZATION_TOOL,
    RESEARCH_VALIDATE_OPTIMIZATION_OBJECTIVE_TOOL,
    RESEARCH_VALIDATE_STRATEGY_IMPLEMENTATION_TOOL,
)
from trader_mcp.environment import load_local_environment
from trader_mcp.server import create_server
from trader_research.foundation import (
    DATA_DOMAIN_OWNER,
    InMemoryResearchArtifactStore,
    parse_research_artifact_uri,
)
from trader_research.governance import (
    DATASET_MANIFEST,
    DATA_QUALITY_REPORT,
    WORKFLOW_OUTCOME,
    ArtifactReportRef,
    DataRequirement,
    DatasetRole,
    ExperimentProtocol,
    ExperimentProtocolStatus,
    InitialPortfolio,
    OptimizationDirection,
    OptimizationProtocol,
    ProtocolDataset,
    ProtocolRiskManager,
    ProtocolStrategy,
    RESEARCH_OBJECTIVE,
    ResearchObjective,
    ResearchObjectiveStatus,
    RobustnessRequirement,
    TunableDimension,
    TunableValueType,
    WorkflowOutcomeStatus,
)
from trader_research.governance.artifacts import (
    IMPLEMENTATION_VERSION,
    IMPLEMENTATION_VALIDATION_REPORT,
    PARAMETER_OPTIMIZATION_EVALUATION_REPORT,
    PARAMETER_OPTIMIZATION_ROBUSTNESS_REPORT,
)
from trader_research.governance.handoffs import artifact_report_ref


STRATEGY_SOURCE = """
from trader.strategies import Strategy

class EmptyStrategy(Strategy):
    def __init__(self, period=2):
        self.period = period

    @property
    def strategy_id(self):
        return "orchestration-empty"

    def generate_orders(self, **kwargs):
        return ()

def build_strategy(period=2, **kwargs):
    return EmptyStrategy(period=period)
"""

RISK_SOURCE = """
from trader.risk import RiskManager

class BoundedRiskManager(RiskManager):
    def __init__(self, max_orders=10):
        self.max_orders = max_orders

    def validate(self, orders, context):
        return list(orders)[:self.max_orders]

def build_risk_manager(max_orders=10):
    return BoundedRiskManager(max_orders=max_orders)
"""

OBJECTIVE_SOURCE = """
def objective(observation):
    return {"value": observation["metrics"]["total_return"]}
"""

SAMPLE_CSV = Path("examples/data/demo_stock_1min.csv")


@dataclass
class RecordingMcpClient:
    """In-process MCP client that records the public execution graph."""

    server: Any
    calls: list[tuple[str, Mapping[str, Any]]] = field(default_factory=list)
    fail_tool: str | None = None

    async def call_tool(
        self,
        tool_name: str,
        arguments: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        """Call one FastMCP tool and retain only its public request."""
        self.calls.append((tool_name, dict(arguments)))
        if tool_name == self.fail_tool:
            raise RuntimeError("simulated MCP transport failure")
        result = await self.server.call_tool(tool_name, dict(arguments))
        return {
            "content": [
                (
                    item.model_dump(mode="json")
                    if hasattr(item, "model_dump")
                    else {"type": "unknown", "text": str(item)}
                )
                for item in result.content
            ],
            "structuredContent": dict(result.structuredContent or {}),
            "isError": bool(result.isError),
        }


@dataclass(frozen=True)
class PreparedWorkflow:
    """Fixture state required to compile one approved workflow."""

    store: InMemoryResearchArtifactStore
    server: Any
    objective: ResearchObjective
    protocol: ExperimentProtocol


def test_data_snapshot_identity_preserves_request_lineage(
    tmp_path: Path,
) -> None:
    async def _run() -> None:
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

        first = await _snapshot(
            server,
            start="2026-01-20T12:00:00Z",
            end="2026-01-20T12:05:00Z",
            requested_by="workflow_snapshot_one",
        )
        repeated = await _snapshot(
            server,
            start="2026-01-20T12:00:00Z",
            end="2026-01-20T12:05:00Z",
            requested_by="workflow_snapshot_one",
        )
        second = await _snapshot(
            server,
            start="2026-01-20T12:00:00Z",
            end="2026-01-20T12:05:00Z",
            requested_by="workflow_snapshot_two",
        )

        assert repeated == first
        assert second != first
        for reference in first:
            record = store.load_artifact_record(
                reference.artifact_type,
                reference.artifact_id,
            )
            assert record.requested_by == "workflow_snapshot_one"
            assert record.actor == "Data Agent"
        for reference in second:
            record = store.load_artifact_record(
                reference.artifact_type,
                reference.artifact_id,
            )
            assert record.requested_by == "workflow_snapshot_two"
            assert record.actor == "Data Agent"

    anyio.run(_run)


def test_compiled_workflow_executes_full_mcp_evidence_graph(
    tmp_path: Path,
) -> None:
    async def _run() -> None:
        prepared = await _prepare_workflow(
            tmp_path,
            optimization=True,
            allow_backtests=True,
        )
        compiled = compile_supplied_implementation_workflow(
            objective=prepared.objective,
            protocol=prepared.protocol,
            artifact_store=prepared.store,
        )
        repeated = compile_supplied_implementation_workflow(
            objective=prepared.objective,
            protocol=prepared.protocol,
            artifact_store=prepared.store,
        )
        assert repeated.plan.plan_id == compiled.plan.plan_id
        assert repeated.plan == compiled.plan
        client = RecordingMcpClient(prepared.server)
        execution = await execute_compiled_research_workflow(
            compiled=compiled,
            workflow_id="workflow_full_evidence",
            tool_client=client,
            checkpointer=InMemorySaver(),
            artifact_store=prepared.store,
        )

        assert execution.outcome.status is WorkflowOutcomeStatus.COMPLETED
        assert {
            item.artifact_type for item in execution.outcome.review_verdict_refs
        } == {
            PARAMETER_OPTIMIZATION_EVALUATION_REPORT,
            PARAMETER_OPTIMIZATION_ROBUSTNESS_REPORT,
        }
        assert execution.outcome.next_permitted_actions == (
            "request_human_review",
        )
        assert prepared.store.load_artifact(
            WORKFLOW_OUTCOME,
            execution.outcome.outcome_id,
        )["status"] == "completed"
        tool_names = [name for name, _ in client.calls]
        assert tool_names[0] == RESEARCH_REGISTER_EXPERIMENT_WORKFLOW_TOOL
        assert RESEARCH_RUN_BACKTEST_SPECIFICATION_TOOL in tool_names
        assert RESEARCH_RUN_PARAMETER_OPTIMIZATION_TOOL in tool_names
        assert tool_names[-1] == RESEARCH_RECORD_WORKFLOW_OUTCOME_TOOL

        workflow_tools = {
            capability.producer_tool for capability in compiled.plan.capabilities
        } | {
            RESEARCH_REGISTER_EXPERIMENT_WORKFLOW_TOOL,
            RESEARCH_RECORD_WORKFLOW_OUTCOME_TOOL,
        }
        workflow_records = tuple(
            record
            for record in prepared.store.list_artifacts()
            if record.producer_tool in workflow_tools
        )
        assert workflow_records
        assert all(
            record.requested_by == "workflow_full_evidence"
            and record.actor == WORKFLOW_EXECUTOR_ACTOR
            for record in workflow_records
        )
        invalid_outcome = replace(
            execution.outcome,
            outcome_id="workflow_outcome_invalid_lineage",
            objective_ref=artifact_report_ref(
                RESEARCH_OBJECTIVE,
                "different_objective",
            ),
        )
        rejected = await prepared.server.call_tool(
            RESEARCH_RECORD_WORKFLOW_OUTCOME_TOOL,
            {
                "outcome": invalid_outcome.to_dict(),
                "requested_by": "workflow_full_evidence",
                "actor": WORKFLOW_EXECUTOR_ACTOR,
            },
        )
        rejected_payload = dict(rejected.structuredContent or {})
        assert rejected_payload["ok"] is False
        assert rejected_payload["errors"][0]["code"] == (
            "workflow_outcome_recording_failed"
        )

    anyio.run(_run)


def test_compiled_workflow_blocks_on_pinned_data_payload_drift(
    tmp_path: Path,
) -> None:
    async def _run() -> None:
        prepared = await _prepare_workflow(
            tmp_path,
            optimization=False,
            allow_backtests=True,
        )
        compiled = compile_supplied_implementation_workflow(
            objective=prepared.objective,
            protocol=prepared.protocol,
            artifact_store=prepared.store,
        )
        manifest_ref = prepared.protocol.datasets[0].dataset_manifest_ref
        drifted = dict(
            prepared.store.load_artifact(
                manifest_ref.artifact_type,
                manifest_ref.artifact_id,
            )
        )
        drifted["total_rows"] = int(drifted["total_rows"]) + 1
        prepared.store.save_artifact(
            artifact_type=manifest_ref.artifact_type,
            artifact_id=manifest_ref.artifact_id,
            domain_owner=DATA_DOMAIN_OWNER,
            producer_tool="test_data_drift",
            payload=drifted,
            status="captured",
        )
        client = RecordingMcpClient(prepared.server)

        execution = await execute_compiled_research_workflow(
            compiled=compiled,
            workflow_id="workflow_data_drift",
            tool_client=client,
            checkpointer=InMemorySaver(),
            artifact_store=prepared.store,
        )

        assert execution.outcome.status is WorkflowOutcomeStatus.BLOCKED
        assert any(
            item.code == "workflow_input_revalidation_failed"
            for item in execution.outcome.blockers
        )
        assert RESEARCH_RUN_BACKTEST_SPECIFICATION_TOOL not in {
            name for name, _ in client.calls
        }

    anyio.run(_run)


def test_compiled_workflow_stops_when_backtests_are_disabled(
    tmp_path: Path,
) -> None:
    async def _run() -> None:
        prepared = await _prepare_workflow(
            tmp_path,
            optimization=True,
            allow_backtests=False,
        )
        compiled = compile_supplied_implementation_workflow(
            objective=prepared.objective,
            protocol=prepared.protocol,
            artifact_store=prepared.store,
        )
        client = RecordingMcpClient(prepared.server)
        execution = await execute_compiled_research_workflow(
            compiled=compiled,
            workflow_id="workflow_policy_blocked",
            tool_client=client,
            checkpointer=InMemorySaver(),
            artifact_store=prepared.store,
        )

        assert execution.outcome.status is WorkflowOutcomeStatus.BLOCKED
        assert any(
            item.code == "backtests_not_allowed"
            for item in execution.outcome.blockers
        ), [item.to_dict() for item in execution.outcome.blockers]
        tool_names = [name for name, _ in client.calls]
        assert tool_names.count(RESEARCH_RUN_BACKTEST_SPECIFICATION_TOOL) == 1
        assert RESEARCH_RUN_PARAMETER_OPTIMIZATION_TOOL not in tool_names
        assert tool_names[-1] == RESEARCH_RECORD_WORKFLOW_OUTCOME_TOOL

    anyio.run(_run)


def test_compiled_workflow_bounds_transport_retries(
    tmp_path: Path,
) -> None:
    async def _run() -> None:
        prepared = await _prepare_workflow(
            tmp_path,
            optimization=False,
            allow_backtests=True,
        )
        compiled = compile_supplied_implementation_workflow(
            objective=prepared.objective,
            protocol=prepared.protocol,
            artifact_store=prepared.store,
        )
        client = RecordingMcpClient(
            prepared.server,
            fail_tool=RESEARCH_VALIDATE_STRATEGY_IMPLEMENTATION_TOOL,
        )

        execution = await execute_compiled_research_workflow(
            compiled=compiled,
            workflow_id="workflow_transport_failure",
            tool_client=client,
            checkpointer=InMemorySaver(),
            artifact_store=prepared.store,
        )

        assert execution.outcome.status is WorkflowOutcomeStatus.BLOCKED
        assert any(
            item.code == "tool_transport_error"
            for item in execution.outcome.blockers
        )
        assert [
            name for name, _ in client.calls
        ].count(RESEARCH_VALIDATE_STRATEGY_IMPLEMENTATION_TOOL) == 3
        assert RESEARCH_RUN_BACKTEST_SPECIFICATION_TOOL not in {
            name for name, _ in client.calls
        }

    anyio.run(_run)


def test_compiled_workflow_resumes_without_replaying_accepted_steps(
    tmp_path: Path,
) -> None:
    async def _run() -> None:
        prepared = await _prepare_workflow(
            tmp_path,
            optimization=False,
            allow_backtests=True,
        )
        compiled = compile_supplied_implementation_workflow(
            objective=prepared.objective,
            protocol=prepared.protocol,
            artifact_store=prepared.store,
        )
        client = RecordingMcpClient(prepared.server)
        saver = InMemorySaver()
        try:
            await execute_compiled_research_workflow(
                compiled=compiled,
                workflow_id="workflow_resume",
                tool_client=client,
                checkpointer=saver,
                artifact_store=prepared.store,
                max_tool_calls=4,
            )
        except WorkflowExecutionInterrupted as exc:
            assert exc.public_state["status"] == "awaiting_result"
        else:
            raise AssertionError("workflow did not stop at the requested boundary")

        accepted_tools = [name for name, _ in client.calls[1:]]
        execution = await execute_compiled_research_workflow(
            compiled=compiled,
            workflow_id="workflow_resume",
            tool_client=client,
            checkpointer=saver,
            artifact_store=prepared.store,
        )

        assert execution.outcome.status is WorkflowOutcomeStatus.COMPLETED
        all_names = [name for name, _ in client.calls]
        assert all_names.count(RESEARCH_REGISTER_EXPERIMENT_WORKFLOW_TOOL) == 2
        for tool_name in accepted_tools:
            assert all_names.count(tool_name) == accepted_tools.count(tool_name)
        assert all_names.count(RESEARCH_RUN_BACKTEST_SPECIFICATION_TOOL) == 1
        assert all_names.count(RESEARCH_RECORD_WORKFLOW_OUTCOME_TOOL) == 1

    anyio.run(_run)


async def _prepare_workflow(
    tmp_path: Path,
    *,
    optimization: bool,
    allow_backtests: bool,
) -> PreparedWorkflow:
    store = InMemoryResearchArtifactStore()
    event_store = DuckDBEventStore(str(tmp_path / "events.duckdb"))
    load_sample_market_data_csv(event_store, SAMPLE_CSV)
    environment = replace(
        load_local_environment("env.template"),
        allow_backtests=allow_backtests,
        allow_optimization=True,
    )
    server = create_server(
        environment,
        event_store_provider=lambda: event_store,
        backtest_config_provider=lambda: _config(tmp_path),
        research_artifact_store_provider=lambda: store,
    )
    strategy_ref = await _register_strategy(server)
    risk_ref = await _register_risk(server)
    selection = await _snapshot(
        server,
        start="2026-01-20T12:00:00Z",
        end="2026-01-20T12:05:00Z",
        requested_by="prepare_selection",
    )
    objective_validation_ref: ArtifactReportRef | None = None
    datasets: tuple[ProtocolDataset, ...] = (
        ProtocolDataset(
            requirement_id="selection" if optimization else "baseline",
            role=DatasetRole.SELECTION if optimization else DatasetRole.BASELINE,
            requirement=_data_requirement(
                start="2026-01-20T12:00:00Z",
                end="2026-01-20T12:05:00Z",
            ),
            dataset_manifest_ref=selection[0],
            data_quality_report_ref=selection[1],
        ),
    )
    optimization_protocol = None
    robustness: tuple[RobustnessRequirement, ...] = ()
    if optimization:
        holdout = await _snapshot(
            server,
            start="2026-01-20T12:06:00Z",
            end="2026-01-20T12:11:00Z",
            requested_by="prepare_holdout",
        )
        datasets = (
            *datasets,
            ProtocolDataset(
                requirement_id="holdout",
                role=DatasetRole.HOLDOUT,
                requirement=_data_requirement(
                    start="2026-01-20T12:06:00Z",
                    end="2026-01-20T12:11:00Z",
                ),
                dataset_manifest_ref=holdout[0],
                data_quality_report_ref=holdout[1],
                sealed=True,
            ),
        )
        objective_validation_ref = await _register_objective(server)
        optimization_protocol = OptimizationProtocol(
            objective_validation_ref=objective_validation_ref.uri,
            direction=OptimizationDirection.MAXIMIZE,
            trial_budget=2,
            seed=7,
            dimensions=(
                TunableDimension(
                    dimension_id="period",
                    target_path="/strategy/parameters/period",
                    value_type=TunableValueType.INTEGER,
                    lower=2,
                    upper=3,
                    step=1,
                ),
            ),
        )
        robustness = (
            RobustnessRequirement(
                requirement_id="seed",
                attack_type="seed_sensitivity",
                claim="Selection does not depend on one random seed.",
            ),
            RobustnessRequirement(
                requirement_id="concentration",
                attack_type="concentration",
                claim="The selected result exposes concentration evidence.",
            ),
            RobustnessRequirement(
                requirement_id="multiple_testing",
                attack_type="multiple_testing",
                claim="The review accounts for the declared trial count.",
            ),
        )

    objective = ResearchObjective(
        objective_id=f"objective_{'optimization' if optimization else 'baseline'}",
        statement="Evaluate the supplied strategy and risk implementation.",
        success_criteria=("Produce canonical research evidence.",),
        requested_by="operator:test",
        actor="operator:test",
        supplied_artifact_refs=(strategy_ref, risk_ref),
        status=ResearchObjectiveStatus.APPROVED,
    )
    protocol = ExperimentProtocol(
        protocol_id=f"protocol_{'optimization' if optimization else 'baseline'}",
        objective_id=objective.objective_id,
        strategy=ProtocolStrategy(
            implementation_ref=strategy_ref,
            parameters={"period": 2},
            tunable_fields=(
                ("/strategy/parameters/period",) if optimization else ()
            ),
        ),
        risk_managers=(
            ProtocolRiskManager(
                implementation_ref=risk_ref,
                parameters={"max_orders": 10},
                tunable_fields=("/risk/0/parameters/max_orders",),
            ),
        ),
        datasets=datasets,
        costs=(),
        initial_portfolio=InitialPortfolio(
            cash=100_000.0,
            currency="USD",
        ),
        optimization=optimization_protocol,
        optimizer_profile="builtin_grid",
        max_runs=3,
        robustness_requirements=robustness,
        evaluation_questions=("Does the evidence support the supplied code?",),
        falsification_criteria=("Block on invalid or unavailable evidence.",),
        material_assumptions=(),
        approvals=(),
        requested_by=objective.objective_id,
        proposed_by="experiment_design_agent",
        status=ExperimentProtocolStatus.APPROVED,
    )
    return PreparedWorkflow(
        store=store,
        server=server,
        objective=objective,
        protocol=protocol,
    )


async def _register_strategy(server: Any) -> ArtifactReportRef:
    result = await server.call_tool(
        RESEARCH_REGISTER_STRATEGY_IMPLEMENTATION_TOOL,
        {
            "name": "orchestration-empty-strategy",
            "version": "1",
            "source_code": STRATEGY_SOURCE,
            "factory_name": "build_strategy",
            "class_name": "EmptyStrategy",
            "parameter_schema": {
                "type": "object",
                "properties": {
                    "period": {
                        "type": "integer",
                        "minimum": 2,
                        "maximum": 3,
                        "default": 2,
                    }
                },
            },
            "authoring_origin": "handwritten_test_fixture",
        },
    )
    return _ref(result, "implementation_version", IMPLEMENTATION_VERSION)


async def _register_risk(server: Any) -> ArtifactReportRef:
    result = await server.call_tool(
        RESEARCH_REGISTER_RISK_MANAGER_IMPLEMENTATION_TOOL,
        {
            "name": "orchestration-bounded-risk",
            "version": "1",
            "source_code": RISK_SOURCE,
            "factory_name": "build_risk_manager",
            "class_name": "BoundedRiskManager",
            "parameter_schema": {
                "type": "object",
                "properties": {
                    "max_orders": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 100,
                    }
                },
                "required": ["max_orders"],
            },
            "authoring_origin": "handwritten_test_fixture",
        },
    )
    return _ref(result, "implementation_version", IMPLEMENTATION_VERSION)


async def _register_objective(server: Any) -> ArtifactReportRef:
    registered = await server.call_tool(
        RESEARCH_REGISTER_OPTIMIZATION_OBJECTIVE_TOOL,
        {
            "name": "orchestration-total-return",
            "version": "1",
            "source_code": OBJECTIVE_SOURCE,
            "factory_name": "objective",
        },
    )
    implementation = _ref(
        registered,
        "implementation_version",
        IMPLEMENTATION_VERSION,
    )
    validated = await server.call_tool(
        RESEARCH_VALIDATE_OPTIMIZATION_OBJECTIVE_TOOL,
        {"implementation_version_uri": implementation.uri},
    )
    return _ref(
        validated,
        "implementation_validation_report",
        IMPLEMENTATION_VALIDATION_REPORT,
    )


async def _snapshot(
    server: Any,
    *,
    start: str,
    end: str,
    requested_by: str,
) -> tuple[ArtifactReportRef, ArtifactReportRef]:
    result = await server.call_tool(
        DATA_CREATE_RESEARCH_SNAPSHOT_TOOL,
        {
            "symbols": ["DEMO"],
            "asset_class": "stocks",
            "timeframe": "1Min",
            "start": start,
            "end": end,
            "requested_by": requested_by,
            "actor": "Data Agent",
        },
    )
    return (
        _ref(result, "dataset_manifest", DATASET_MANIFEST),
        _ref(result, "data_quality_report", DATA_QUALITY_REPORT),
    )


def _ref(result: Any, key: str, artifact_type: str) -> ArtifactReportRef:
    payload = dict(result.structuredContent or {})
    assert payload.get("ok") is True, payload.get("errors")
    artifact = payload["artifacts"][key]
    assert artifact["artifact_type"] == artifact_type
    parsed_type, artifact_id = parse_research_artifact_uri(artifact["uri"])
    assert parsed_type == artifact_type
    return artifact_report_ref(artifact_type, artifact_id)


def _data_requirement(*, start: str, end: str) -> DataRequirement:
    return DataRequirement(
        symbols=("DEMO",),
        asset_class="stocks",
        timeframe="1Min",
        start=start,
        end=end,
    )


def _config(tmp_path: Path) -> Config:
    return Config(
        mode="once",
        strategy_type="research",
        strategy_id="research",
        strategy_timeframe="1Min",
        sma_short_window=2,
        sma_long_window=3,
        db_path=str(tmp_path / "events.duckdb"),
        event_store="postgres",
        market_data_source="noop",
        market_data_asset_class="stocks",
        market_data_stock_feed="iex",
        market_data_symbols=("DEMO",),
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
