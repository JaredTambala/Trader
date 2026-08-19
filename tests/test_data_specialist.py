"""Focused contract, policy, handler, and integration tests for the Data specialist."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import anyio
from langgraph.checkpoint.memory import InMemorySaver
import pytest

from tests.support.duckdb_store import DuckDBEventStore
from trader.market_data.sample import load_sample_market_data_csv
from trader_agents import (
    DataLoadingIntent,
    DataLoadingMode,
    DataSpecialistRequest,
    SpecialistResult,
    SpecialistResultStatus,
    SpecialistTask,
    SpecialistTaskConflictError,
    build_data_specialist_graph,
    build_data_specialist_task,
    build_specialist_initial_state,
    run_specialist_task,
    specialist_public_state,
)
from trader_mcp.constants import (
    DATA_CREATE_RESEARCH_SNAPSHOT_TOOL,
    DATA_DISCOVER_SYMBOLS_TOOL,
    DATA_ENSURE_LOADED_TOOL,
)
from trader_mcp.environment import load_local_environment
from trader_mcp.server import create_server
from trader_research.foundation import (
    DATA_DOMAIN_OWNER,
    InMemoryResearchArtifactStore,
    stable_research_id,
)
from trader_research.governance import (
    CapabilitySideEffect,
    DataRequirement,
    ResearchObjective,
    ResearchObjectiveStatus,
)


SAMPLE_CSV = Path("examples/data/demo_stock_1min.csv")


@dataclass
class RecordingDataMcpClient:
    """Return deterministic Data envelopes and persist fake canonical snapshots."""

    artifact_store: InMemoryResearchArtifactStore
    complete: bool = True
    missing_symbols: tuple[str, ...] = ()
    forged_command: str | None = None
    forged_owner: str | None = None
    forged_side_effect: str | None = None
    omit_quality_ref: bool = False
    drift_symbols: bool = False
    calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

    async def call_tool(
        self,
        tool_name: str,
        arguments: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        """Return one MCP-style result for the requested Data operation."""
        args = dict(arguments)
        self.calls.append((tool_name, args))
        if tool_name == DATA_DISCOVER_SYMBOLS_TOOL:
            return self._result(
                tool_name,
                CapabilitySideEffect.READ_ONLY,
                data={
                    "symbol_discovery_report": {
                        "requested_symbols": list(args["symbols"]),
                        "asset_class": args["asset_class"],
                        "source": args["source"],
                        "requested_provider": args.get("provider"),
                        "all_requested_symbols_exist": not self.missing_symbols,
                        "missing_symbols": list(self.missing_symbols),
                    }
                },
            )
        if tool_name == DATA_ENSURE_LOADED_TOOL:
            return self._result(
                tool_name,
                CapabilitySideEffect.LOCAL_MUTATING,
                data={"load_result": {"mode": args["mode"], "status": "loaded"}},
            )
        if tool_name == DATA_CREATE_RESEARCH_SNAPSHOT_TOOL:
            artifacts = self._save_snapshot(args)
            if self.omit_quality_ref:
                artifacts.pop("data_quality_report")
            return self._result(
                tool_name,
                CapabilitySideEffect.LOCAL_MUTATING,
                artifacts=artifacts,
            )
        raise AssertionError(f"unexpected tool call: {tool_name}")

    def _save_snapshot(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        symbols = ["DRIFT"] if self.drift_symbols else list(arguments["symbols"])
        dataset_id = stable_research_id(
            "dataset",
            {
                "symbols": symbols,
                "start": arguments["start"],
                "end": arguments["end"],
            },
        )
        common = {
            "symbols": symbols,
            "asset_class": arguments["asset_class"],
            "timeframe": arguments["timeframe"],
            "requested_window": {
                "start": arguments["start"],
                "end": arguments["end"],
            },
            "source_filter": arguments.get("source"),
            "provider_context": {"requested_provider": arguments.get("provider")},
            "instrument_type": arguments.get("instrument_type"),
            "bar_type": arguments.get("bar_type"),
            "snapshot_request_id": arguments["requested_by"],
            "snapshot_actor": arguments["actor"],
            "status": "captured",
            "dataset_id": dataset_id,
            "complete": self.complete,
        }
        manifest_id = stable_research_id("dataset_manifest", common)
        manifest = self.artifact_store.save_artifact(
            artifact_type="dataset_manifest",
            artifact_id=manifest_id,
            domain_owner=DATA_DOMAIN_OWNER,
            producer_tool=DATA_CREATE_RESEARCH_SNAPSHOT_TOOL,
            payload={"artifact_type": "dataset_manifest", **common},
            requested_by=str(arguments["requested_by"]),
            actor=str(arguments["actor"]),
            status="captured",
        )
        quality_id = stable_research_id("data_quality_report", common)
        quality = self.artifact_store.save_artifact(
            artifact_type="data_quality_report",
            artifact_id=quality_id,
            domain_owner=DATA_DOMAIN_OWNER,
            producer_tool=DATA_CREATE_RESEARCH_SNAPSHOT_TOOL,
            payload={"artifact_type": "data_quality_report", **common},
            requested_by=str(arguments["requested_by"]),
            actor=str(arguments["actor"]),
            status="captured",
            metadata={"dataset_manifest_artifact_id": manifest_id},
        )
        return {
            "dataset_manifest": manifest.reference().to_dict(),
            "data_quality_report": quality.reference().to_dict(),
        }

    def _result(
        self,
        tool_name: str,
        side_effect: CapabilitySideEffect,
        *,
        data: Mapping[str, Any] | None = None,
        artifacts: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "content": [],
            "structuredContent": {
                "ok": True,
                "command": self.forged_command or tool_name,
                "agent_owner": self.forged_owner or "Data Agent",
                "side_effect": self.forged_side_effect or side_effect.value,
                "data": dict(data or {}),
                "artifacts": dict(artifacts or {}),
                "warnings": [],
                "errors": [],
            },
            "isError": False,
        }


@dataclass
class InProcessMcpClient:
    """Adapt an in-process FastMCP server to the agent tool-client protocol."""

    server: Any
    calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

    async def call_tool(
        self,
        tool_name: str,
        arguments: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        """Call one FastMCP tool and return its public result mapping."""
        args = dict(arguments)
        self.calls.append((tool_name, args))
        result = await self.server.call_tool(tool_name, args)
        return {
            "content": [],
            "structuredContent": dict(result.structuredContent or {}),
            "isError": bool(result.isError),
        }


def test_data_specialist_request_is_strict_and_normalized() -> None:
    request = DataSpecialistRequest.from_dict(
        {
            "data_requirement": {
                "symbols": ["demo"],
                "asset_class": "STOCKS",
                "timeframe": "1Min",
                "start": "2026-01-20T12:00:00Z",
                "end": "2026-01-20T12:11:00Z",
            },
            "provider": "ALPACA",
            "instrument_type": "Stock",
            "bar_type": "Trade-Bar",
        }
    )

    assert request.data_requirement.symbols == ("DEMO",)
    assert request.data_requirement.asset_class == "stocks"
    assert request.data_requirement.start == "2026-01-20T12:00:00+00:00"
    assert request.provider == "alpaca"
    assert request.instrument_type == "stock"
    assert request.bar_type == "trade_bar"

    payload = request.to_dict()
    payload["tool_name"] = DATA_DISCOVER_SYMBOLS_TOOL
    with pytest.raises(ValueError, match="unknown fields: tool_name"):
        DataSpecialistRequest.from_dict(payload)
    with pytest.raises(ValueError, match="loading mode must be sample"):
        DataSpecialistRequest.from_dict(
            {
                **request.to_dict(),
                "loading_intent": {"mode": "backfill"},
            }
        )
    with pytest.raises(ValueError, match="must include a timezone"):
        DataSpecialistRequest(
            data_requirement=replace(
                request.data_requirement,
                start="2026-01-20T12:00:00",
            )
        )


def test_data_task_factory_rejects_contradictory_loading_approval() -> None:
    with pytest.raises(ValueError, match="requires an explicit loading intent"):
        build_data_specialist_task(
            request=_request(),
            objective=_objective(),
            requested_by="workflow_demo",
            actor="research_coordinator",
            permit_local_mutation=True,
            approve_sample_loading=True,
        )


def test_data_policy_requests_permissions_before_mcp_calls() -> None:
    store = InMemoryResearchArtifactStore()
    client = RecordingDataMcpClient(store)
    task = _task(permit_local_mutation=False)
    graph = build_data_specialist_graph(tool_client=client, artifact_store=store)

    output = anyio.run(lambda: graph.ainvoke(build_specialist_initial_state(task)))
    result = SpecialistResult.from_dict(output["result"])

    assert result.status is SpecialistResultStatus.AWAITING_PREREQUISITE
    assert result.prerequisites[0].prerequisite_id == "permit_data_evidence_persistence"
    assert client.calls == []


def test_data_policy_requires_separate_sample_loading_approval() -> None:
    store = InMemoryResearchArtifactStore()
    client = RecordingDataMcpClient(store)
    task = _task(loading=True, approve_sample_loading=False)
    graph = build_data_specialist_graph(tool_client=client, artifact_store=store)

    output = anyio.run(lambda: graph.ainvoke(build_specialist_initial_state(task)))
    result = SpecialistResult.from_dict(output["result"])

    assert result.status is SpecialistResultStatus.AWAITING_PREREQUISITE
    assert result.prerequisites[0].prerequisite_id == "approve_sample_data_loading"
    assert client.calls == []


def test_data_specialist_returns_verified_canonical_handoffs() -> None:
    store = InMemoryResearchArtifactStore()
    client = RecordingDataMcpClient(store)
    task = _task()
    graph = build_data_specialist_graph(tool_client=client, artifact_store=store)

    output = anyio.run(lambda: graph.ainvoke(build_specialist_initial_state(task)))
    result = SpecialistResult.from_dict(output["result"])
    public = specialist_public_state(output)

    assert result.status is SpecialistResultStatus.COMPLETED
    assert [call[0] for call in client.calls] == [
        DATA_DISCOVER_SYMBOLS_TOOL,
        DATA_CREATE_RESEARCH_SNAPSHOT_TOOL,
    ]
    assert {handoff.artifact_type for handoff in result.handoffs} == {
        "dataset_manifest",
        "data_quality_report",
    }
    assert all(not handoff.payload for handoff in result.handoffs)
    assert all(
        "payload_sha256" in handoff.provenance_refs for handoff in result.handoffs
    )
    serialized = str(public)
    assert "structuredContent" not in serialized
    assert "symbols_detail" not in serialized


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"forged_command": "data_get_inventory"}, "wrong command identity"),
        ({"forged_owner": "Research Coordinator"}, "wrong agent owner"),
        ({"forged_side_effect": "broker_mutating"}, "wrong side-effect class"),
    ],
)
def test_data_specialist_rejects_forged_mcp_envelopes(
    overrides: Mapping[str, Any],
    message: str,
) -> None:
    store = InMemoryResearchArtifactStore()
    client = RecordingDataMcpClient(store, **overrides)
    graph = build_data_specialist_graph(tool_client=client, artifact_store=store)

    output = anyio.run(lambda: graph.ainvoke(build_specialist_initial_state(_task())))

    assert output["status"] == "failed"
    assert output["errors"][0]["code"] == "invalid_data_tool_envelope"
    assert message in output["errors"][0]["message"]


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"omit_quality_ref": True}, "invalid_data_snapshot_refs"),
        ({"drift_symbols": True}, "invalid_canonical_data_evidence"),
    ],
)
def test_data_specialist_rejects_missing_or_drifted_canonical_evidence(
    overrides: Mapping[str, Any],
    code: str,
) -> None:
    store = InMemoryResearchArtifactStore()
    client = RecordingDataMcpClient(store, **overrides)
    graph = build_data_specialist_graph(tool_client=client, artifact_store=store)

    output = anyio.run(lambda: graph.ainvoke(build_specialist_initial_state(_task())))

    assert output["status"] == "failed"
    assert output["errors"][0]["code"] == code


def test_incomplete_quality_blocks_but_retains_canonical_refs() -> None:
    store = InMemoryResearchArtifactStore()
    client = RecordingDataMcpClient(store, complete=False)
    graph = build_data_specialist_graph(tool_client=client, artifact_store=store)

    output = anyio.run(lambda: graph.ainvoke(build_specialist_initial_state(_task())))
    result = SpecialistResult.from_dict(output["result"])

    assert result.status is SpecialistResultStatus.BLOCKED
    assert len(result.handoffs) == 2
    assert {item.code for item in result.blockers} == {
        "dataset_manifest_incomplete",
        "data_quality_incomplete",
    }


def test_data_specialist_enforces_action_budget() -> None:
    store = InMemoryResearchArtifactStore()
    client = RecordingDataMcpClient(store)
    graph = build_data_specialist_graph(
        tool_client=client,
        artifact_store=store,
        max_action_attempts=1,
    )

    output = anyio.run(lambda: graph.ainvoke(build_specialist_initial_state(_task())))

    assert output["status"] == "failed"
    assert output["errors"][0]["code"] == "specialist_action_limit_exceeded"
    assert [call[0] for call in client.calls] == [DATA_DISCOVER_SYMBOLS_TOOL]


def test_checkpointed_data_specialist_reuses_terminal_result_and_rejects_task_drift() -> (
    None
):
    store = InMemoryResearchArtifactStore()
    client = RecordingDataMcpClient(store)
    task = _task()
    graph = build_data_specialist_graph(
        tool_client=client,
        artifact_store=store,
        checkpointer=InMemorySaver(),
    )

    async def _run() -> None:
        first = await run_specialist_task(graph=graph, task=task)
        replay = await run_specialist_task(graph=graph, task=task)
        assert replay["result"] == first["result"]
        assert len(client.calls) == 2

        changed_request = replace(
            _request(),
            data_requirement=replace(
                _request().data_requirement,
                end="2026-01-20T12:10:00Z",
            ),
        )
        changed_task = SpecialistTask(
            **{
                **task.__dict__,
                "specialist_input": changed_request.to_dict(),
            }
        )
        with pytest.raises(SpecialistTaskConflictError, match="does not match"):
            await run_specialist_task(graph=graph, task=changed_task)

    anyio.run(_run)


def test_in_process_mcp_existing_data_completes_with_verified_evidence(
    tmp_path: Path,
) -> None:
    event_store = DuckDBEventStore(str(tmp_path / "events.duckdb"))
    load_sample_market_data_csv(event_store, SAMPLE_CSV)
    artifact_store = InMemoryResearchArtifactStore()
    server = create_server(
        load_local_environment("env.template"),
        event_store_provider=lambda: event_store,
        research_artifact_store_provider=lambda: artifact_store,
    )
    client = InProcessMcpClient(server)
    task = _task(request=replace(_request(), discovery_source="local"))
    graph = build_data_specialist_graph(
        tool_client=client,
        artifact_store=artifact_store,
    )

    output = anyio.run(lambda: graph.ainvoke(build_specialist_initial_state(task)))

    assert output["status"] == "completed"
    assert len(artifact_store.list_artifacts()) == 2
    assert [call[0] for call in client.calls] == [
        DATA_DISCOVER_SYMBOLS_TOOL,
        DATA_CREATE_RESEARCH_SNAPSHOT_TOOL,
    ]


def test_in_process_sample_loading_is_replay_safe(tmp_path: Path) -> None:
    event_store = DuckDBEventStore(str(tmp_path / "events.duckdb"))
    artifact_store = InMemoryResearchArtifactStore()
    environment = replace(
        load_local_environment("env.template"),
        allow_data_loading=True,
        trader_config_path=Path("configs/reproducible_backtest.yaml"),
    )
    server = create_server(
        environment,
        event_store_provider=lambda: event_store,
        research_artifact_store_provider=lambda: artifact_store,
    )
    client = InProcessMcpClient(server)
    task = _task(
        request=replace(
            _request(),
            discovery_source="configured_source",
            loading_intent=DataLoadingIntent(DataLoadingMode.SAMPLE),
        ),
        loading=True,
        approve_sample_loading=True,
    )
    graph = build_data_specialist_graph(
        tool_client=client,
        artifact_store=artifact_store,
        checkpointer=InMemorySaver(),
    )

    async def _run() -> None:
        first = await run_specialist_task(graph=graph, task=task)
        replay = await run_specialist_task(graph=graph, task=task)
        assert first["status"] == "completed"
        assert replay["result"] == first["result"]

    anyio.run(_run)

    row_count = (
        event_store.connection()
        .execute("SELECT COUNT(*) FROM stock_bar_events WHERE symbol = 'DEMO'")
        .fetchone()[0]
    )
    assert row_count == 12
    assert len(artifact_store.list_artifacts()) == 2
    assert [call[0] for call in client.calls] == [
        DATA_DISCOVER_SYMBOLS_TOOL,
        DATA_ENSURE_LOADED_TOOL,
        DATA_CREATE_RESEARCH_SNAPSHOT_TOOL,
    ]


def _request() -> DataSpecialistRequest:
    return DataSpecialistRequest(
        data_requirement=DataRequirement(
            symbols=("DEMO",),
            asset_class="stocks",
            timeframe="1Min",
            start="2026-01-20T12:00:00Z",
            end="2026-01-20T12:11:00Z",
        )
    )


def _objective() -> ResearchObjective:
    return ResearchObjective(
        objective_id="research_objective_data_demo",
        statement="Determine whether the requested market data is fit for research.",
        success_criteria=("Return canonical Data evidence.",),
        requested_by="operator_demo",
        actor="operator_demo",
        status=ResearchObjectiveStatus.APPROVED,
    )


def _task(
    *,
    request: DataSpecialistRequest | None = None,
    permit_local_mutation: bool = True,
    loading: bool = False,
    approve_sample_loading: bool = False,
) -> SpecialistTask:
    selected_request = request or _request()
    if loading and selected_request.loading_intent is None:
        selected_request = replace(
            selected_request,
            loading_intent=DataLoadingIntent(DataLoadingMode.SAMPLE),
        )
    return build_data_specialist_task(
        request=selected_request,
        objective=_objective(),
        requested_by="workflow_demo",
        actor="research_coordinator",
        permit_local_mutation=permit_local_mutation,
        approve_sample_loading=approve_sample_loading,
    )
