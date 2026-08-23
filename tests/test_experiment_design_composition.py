"""Exercise proposal, approval, and fixed workflow composition end to end."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import anyio
from langgraph.checkpoint.memory import InMemorySaver

from tests.support.duckdb_store import DuckDBEventStore
from tests.test_orchestration_execution import (
    SAMPLE_CSV,
    _config,
    _register_risk,
    _register_strategy,
)
from trader.market_data.sample import load_sample_market_data_csv
from trader_agents import (
    ResearchCompositionRequest,
    build_experiment_design_task,
    run_research_composition,
)
from trader_mcp.constants import (
    DATA_CREATE_RESEARCH_SNAPSHOT_TOOL,
    RESEARCH_CREATE_EXPERIMENT_PROTOCOL_PROPOSAL_TOOL,
)
from trader_mcp.environment import load_local_environment
from trader_mcp.server import create_server
from trader_research.foundation import (
    InMemoryResearchArtifactStore,
    parse_research_artifact_uri,
)
from trader_research.governance import (
    DATASET_MANIFEST,
    DATA_QUALITY_REPORT,
    EXPERIMENT_PROTOCOL,
    EXPERIMENT_PROTOCOL_PROPOSAL,
    ApprovalStatus,
    CostAssumption,
    DataRequirement,
    DatasetRole,
    ExperimentDesignRequest,
    ExperimentProtocolProposal,
    InitialPortfolio,
    MaterialAssumption,
    ProtocolDataset,
    ProtocolRiskManager,
    ProtocolStrategy,
    ResearchObjective,
    ResearchObjectiveStatus,
    apply_experiment_protocol_approvals,
    artifact_report_ref,
)


@dataclass
class _RecordingClient:
    """Adapt an in-process MCP server and record composition tool calls."""

    server: Any
    calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

    async def call_tool(
        self,
        tool_name: str,
        arguments: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        """Call one tool and retain only its public request mapping."""
        args = dict(arguments)
        self.calls.append((tool_name, args))
        result = await self.server.call_tool(tool_name, args)
        return {
            "content": [],
            "structuredContent": dict(result.structuredContent or {}),
            "isError": bool(result.isError),
        }


def test_design_proposal_pauses_for_approval_then_enters_fixed_workflow(
    tmp_path: Path,
) -> None:
    async def _run() -> None:
        store = InMemoryResearchArtifactStore()
        event_store = DuckDBEventStore(str(tmp_path / "events.duckdb"))
        load_sample_market_data_csv(event_store, SAMPLE_CSV)
        server = create_server(
            replace(load_local_environment("env.template"), allow_backtests=True),
            event_store_provider=lambda: event_store,
            backtest_config_provider=lambda: _config(tmp_path),
            research_artifact_store_provider=lambda: store,
        )
        strategy_ref = await _register_strategy(server)
        risk_ref = await _register_risk(server)
        requirement = _requirement()
        manifest_ref, quality_ref = await _snapshot_refs(server, requirement)
        objective = ResearchObjective(
            objective_id="objective_design_composition",
            statement="Evaluate the supplied deterministic implementation.",
            success_criteria=("Produce canonical baseline evidence.",),
            supplied_artifact_refs=(strategy_ref, risk_ref),
            requested_by="operator:jared",
            actor="operator:jared",
            status=ResearchObjectiveStatus.APPROVED,
        )
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
            costs=(CostAssumption(name="fees.bps", value=0.0, unit="bps"),),
            initial_portfolio=InitialPortfolio(cash=100_000.0, currency="USD"),
            robustness_requirements=(),
            evaluation_questions=("Does baseline evidence support execution?",),
            falsification_criteria=("Block on invalid canonical evidence.",),
            material_assumptions=(
                MaterialAssumption(
                    assumption_id="fixture_costs",
                    category="cost",
                    statement="Use zero fees for the checked-in fixture.",
                    value={"fees.bps": 0.0},
                ),
            ),
            requested_approver="operator:jared",
            deterministic_seed=7,
            max_runs=3,
            log_cycle_details=False,
            runtime_limits={"max_bars": 1_000},
            optimizer_profile="builtin_random",
        )
        composition_id = "composition_with_design"
        task = build_experiment_design_task(
            request=design,
            objective=objective,
            requested_by=composition_id,
            actor="research_coordinator",
            permit_local_mutation=True,
        )
        request = ResearchCompositionRequest(
            composition_id=composition_id,
            objective=objective,
            specialist_tasks=(task,),
            requested_by="operator:jared",
            actor="research_coordinator",
        )
        client = _RecordingClient(server)
        checkpointer = InMemorySaver()

        paused = await run_research_composition(
            request=request,
            protocol=None,
            tool_client=client,
            artifact_store=store,
            checkpointer=checkpointer,
        )
        assert paused["status"] == "awaiting_approval"
        assert paused["protocol_proposal_ref"]["artifact_type"] == (
            EXPERIMENT_PROTOCOL_PROPOSAL
        )
        assert [name for name, _ in client.calls] == [
            RESEARCH_CREATE_EXPERIMENT_PROTOCOL_PROPOSAL_TOOL
        ]
        proposal_ref = paused["protocol_proposal_ref"]
        proposal = ExperimentProtocolProposal.from_dict(
            store.load_artifact(
                EXPERIMENT_PROTOCOL_PROPOSAL,
                proposal_ref["artifact_id"],
            )
        )
        decisions = tuple(
            replace(
                item,
                status=ApprovalStatus.APPROVED,
                decided_by="operator:jared",
                rationale="Approved for the bounded fixture run.",
            )
            for item in proposal.protocol.approvals
        )
        approved = apply_experiment_protocol_approvals(proposal, decisions)

        terminal = await run_research_composition(
            request=request,
            protocol=approved,
            tool_client=client,
            artifact_store=store,
            checkpointer=checkpointer,
        )
        assert terminal["status"] == "completed"
        assert sum(
            name == RESEARCH_CREATE_EXPERIMENT_PROTOCOL_PROPOSAL_TOOL
            for name, _ in client.calls
        ) == 1
        assert store.load_artifact(
            EXPERIMENT_PROTOCOL_PROPOSAL,
            proposal.proposal_id,
        )["status"] == "proposed"
        assert store.load_artifact(
            EXPERIMENT_PROTOCOL,
            approved.protocol_id,
        )["status"] == "approved"

    anyio.run(_run)


async def _snapshot_refs(
    server: Any,
    requirement: DataRequirement,
):
    result = await server.call_tool(
        DATA_CREATE_RESEARCH_SNAPSHOT_TOOL,
        {
            "symbols": list(requirement.symbols),
            "asset_class": requirement.asset_class,
            "timeframe": requirement.timeframe,
            "start": requirement.start,
            "end": requirement.end,
            "requested_by": "design_data_setup",
            "actor": "Data Agent",
        },
    )
    artifacts = dict((result.structuredContent or {})["artifacts"])
    return (
        _artifact_ref(artifacts["dataset_manifest"]["uri"], DATASET_MANIFEST),
        _artifact_ref(
            artifacts["data_quality_report"]["uri"],
            DATA_QUALITY_REPORT,
        ),
    )


def _artifact_ref(uri: str, expected_type: str):
    artifact_type, artifact_id = parse_research_artifact_uri(uri)
    assert artifact_type == expected_type
    return artifact_report_ref(artifact_type, artifact_id)


def _requirement() -> DataRequirement:
    return DataRequirement(
        symbols=("DEMO",),
        asset_class="stocks",
        timeframe="1Min",
        start="2026-01-20T12:00:00Z",
        end="2026-01-20T12:11:00Z",
    )
