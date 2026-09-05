"""Runtime tests for role-scoped Agent access to MCP transport.

Subject: Envelope normalization, persistent-client cleanup, and terminal tracing at the Agent MCP boundary.
Level: In-process adapter contract.
Collaborators: Real role-scoped runtime and persistent-client lifecycle with deterministic fake transports.
Guarantees: Malformed results fail closed, primary failures survive cleanup, and interrupted calls receive terminal evidence.
Non-goals: Live stdio servers, tool-policy scope admission, specialist reasoning, and research persistence."""

from __future__ import annotations
from contextlib import AsyncExitStack
import json
from pathlib import Path
from typing import Any
import anyio
import pytest
from trader_agents import (
    AgentPhase,
    AgentRole,
    BudgetLedger,
    PolicyContext,
    PersistentStdioMcpToolClient,
    RecordingTraceSink,
    RoleScopedMcpRuntime,
    ToolCallProposal,
    build_delegation,
    composite_data_scope_from_session,
    first_slice_tool_catalogue,
)
from trader_research.foundation import json_payload_hash
from tests.trader_agents.support.runtime_contracts import _correlation, _session, _task
from tests.trader_agents.support.runtime_faults import (
    _FakeMcpClient,
    _InterruptingMcpClient,
    _TestProcessFault,
)


def test_role_scoped_mcp_runtime_validates_transport_envelope() -> None:
    """Only the code-owned schema, owner, and side effect reach the model."""
    session = _session()
    scope = composite_data_scope_from_session(session)
    delegation = build_delegation(
        session_id=session.session_id,
        branch_id="data-branch",
        task=_task("data", "data_research", mutation_requested=True),
        required_input_refs=[],
        permitted_side_effects=["read_only"],
        reserved_model_calls=4,
        reserved_tool_calls=8,
        reserved_tokens=4_000,
        attempt=1,
    )
    ledger = BudgetLedger(session.budget)
    client = _FakeMcpClient()
    traces = RecordingTraceSink()
    runtime = RoleScopedMcpRuntime(
        client=client,
        catalogue=first_slice_tool_catalogue(),
        ledger=ledger,
        trace_sink=traces,
    )
    context = PolicyContext(
        session=session,
        role=AgentRole.DATA_RESEARCH,
        phase=AgentPhase.INVESTIGATE,
        program_id="data-research-v6",
        tool_catalogue=runtime.catalogue,
        usage=ledger.usage,
        runtime_state={},
        loop_fingerprints={},
        delegation=delegation,
        data_scope=scope,
    )
    proposal = ToolCallProposal(
        call_id="inventory-1",
        tool_name="data_get_inventory",
        arguments={
            "symbols": ["BTC/USD", "ETH/USD"],
            "asset_class": "crypto",
            "timeframe": "1h",
            "start": "2024-01-01T00:00:00Z",
            "end": "2024-06-30T23:00:00Z",
        },
        purpose="Inspect exact requested coverage.",
        expected_evidence=["coverage gaps"],
    )

    async def _run() -> Any:
        return await runtime.execute(
            proposal,
            context=context,
            correlation=_correlation("data-research-v6"),
        )

    result = anyio.run(_run)
    assert result.observation.ok is True
    assert result.observation.summary["coverage"] == "complete"
    assert ledger.usage.tool_calls == 1
    assert [span["name"] for span in traces.spans] == [
        "agent.mcp.data_get_inventory",
        "agent.mcp_result.data_get_inventory",
    ]
    assert traces.spans[-1]["attributes"]["trader.result_ok"] is True
    assert traces.spans[0]["attributes"]["trader.argument.scope_digest"] == (
        json_payload_hash(proposal.arguments)
    )
    assert "BTC/USD" not in json.dumps(traces.spans[0]["attributes"])
    assert all("source_code" not in str(span) for span in traces.spans)


def test_persistent_stdio_clients_preserve_primary_exception_on_close() -> None:
    """Close nested MCP task groups without masking the caller's failure."""

    async def _run() -> None:
        with pytest.raises(ValueError, match="primary runtime failure"):
            async with AsyncExitStack() as stack:
                clients = [
                    await stack.enter_async_context(
                        PersistentStdioMcpToolClient(
                            command="uv",
                            args=("run", "python", "-m", "trader_mcp.runtime.server"),
                            cwd=Path.cwd(),
                        )
                    )
                    for _ in range(3)
                ]
                assert await clients[0].list_tools()
                raise ValueError("primary runtime failure")

    anyio.run(_run)


def test_role_scoped_runtime_traces_interrupted_transport_terminally() -> None:
    """Pair an authorized call with a redacted result when its response is lost."""
    session = _session()
    scope = composite_data_scope_from_session(session)
    delegation = build_delegation(
        session_id=session.session_id,
        branch_id="data-transport-fault",
        task=_task("data-fault", "data_research"),
        required_input_refs=[],
        permitted_side_effects=["read_only"],
        reserved_model_calls=2,
        reserved_tool_calls=2,
        reserved_tokens=2_000,
        attempt=1,
    )
    ledger = BudgetLedger(session.budget)
    traces = RecordingTraceSink()
    runtime = RoleScopedMcpRuntime(
        client=_InterruptingMcpClient(),
        catalogue=first_slice_tool_catalogue(),
        ledger=ledger,
        trace_sink=traces,
    )
    context = PolicyContext(
        session=session,
        role=AgentRole.DATA_RESEARCH,
        phase=AgentPhase.INVESTIGATE,
        program_id="data-research-v6",
        tool_catalogue=runtime.catalogue,
        usage=ledger.usage,
        runtime_state={},
        loop_fingerprints={},
        delegation=delegation,
        data_scope=scope,
    )
    proposal = ToolCallProposal(
        call_id="lost-response",
        tool_name="data_get_inventory",
        arguments={
            "symbols": ["BTC/USD", "ETH/USD"],
            "asset_class": "crypto",
            "timeframe": "1h",
            "start": "2024-01-01T00:00:00Z",
            "end": "2024-06-30T23:00:00Z",
        },
        purpose="Exercise a lost transport response.",
        expected_evidence=["terminal transport trace"],
    )

    async def _run() -> None:
        with pytest.raises(_TestProcessFault):
            await runtime.execute(
                proposal,
                context=context,
                correlation=_correlation("data-research-v6"),
            )

    anyio.run(_run)

    assert ledger.usage.tool_calls == 1
    assert [span["name"] for span in traces.spans] == [
        "agent.mcp.data_get_inventory",
        "agent.mcp_result.data_get_inventory",
    ]
    result = traces.spans[-1]["attributes"]
    assert result["trader.result_ok"] is False
    assert result["trader.error_codes"] == ["mcp_transport_interrupted"]
