"""Coordination contracts for controlled Agent MCP fault injection.

Subject: Role-aware fault placement around Data mutation, Strategy custody, admission, repair, and Coordinator review.
Level: In-process coordination contract.
Collaborators: Real fault decorators over a deterministic in-memory MCP client; no subprocess or external service.
Guarantees: Each configured fault fires only at its exact pre- or post-acceptance boundary.
Non-goals: Fresh-process recovery, real MCP transport, canonical persistence, and specialist model behavior.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import anyio
import pytest

from tests.trader_agents.coordination.support.agentic_faults import (
    AFTER_DATA_MUTATION,
    AFTER_STRATEGY_ADMISSION_FAILURE,
    AFTER_STRATEGY_ADMISSION_SUCCESS,
    AFTER_STRATEGY_PACKAGE,
    AFTER_STRATEGY_REGISTRATION,
    BEFORE_DATA_MUTATION,
    BEFORE_RETURN_RECONCILIATION,
    BEFORE_STRATEGY_ADMISSION,
    BEFORE_STRATEGY_PACKAGE,
    BEFORE_STRATEGY_REGISTRATION,
    BEFORE_STRATEGY_REPAIR_WRITE,
    InjectedProcessFault,
    NO_FAULT,
    recovery_mcp_client_decorator,
)
from trader_agents.contracts.domain import AgentRole
from trader_agents.mcp.client import McpToolDescription


@dataclass
class _Client:
    """Record bounded calls and return successful MCP envelopes."""

    calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    next_ok: bool = True

    async def list_tools(self) -> Sequence[McpToolDescription]:
        """Return an empty schema catalogue for wrapper tests."""
        return ()

    async def call_tool(
        self,
        tool_name: str,
        arguments: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        """Record one call and report a successful accepted result."""
        self.calls.append((tool_name, dict(arguments)))
        return {
            "structuredContent": {"ok": self.next_ok},
            "isError": not self.next_ok,
        }


def test_faults_fire_before_and_after_only_the_actual_data_mutation() -> None:
    """Leave dry runs intact and distinguish unaccepted from accepted work."""
    before_client = _Client()
    before = recovery_mcp_client_decorator(BEFORE_DATA_MUTATION)(
        AgentRole.DATA_RESEARCH,
        before_client,
    )
    after_client = _Client()
    after = recovery_mcp_client_decorator(AFTER_DATA_MUTATION)(
        AgentRole.DATA_RESEARCH,
        after_client,
    )
    dry_run = {"mode": "backfill", "dry_run": True}
    mutation = {"mode": "backfill", "dry_run": False}

    async def _run() -> None:
        await before.call_tool("data_ensure_loaded", dry_run)
        with pytest.raises(InjectedProcessFault) as before_fault:
            await before.call_tool("data_ensure_loaded", mutation)
        assert before_fault.value.mode == BEFORE_DATA_MUTATION

        await after.call_tool("data_ensure_loaded", dry_run)
        with pytest.raises(InjectedProcessFault) as after_fault:
            await after.call_tool("data_ensure_loaded", mutation)
        assert after_fault.value.mode == AFTER_DATA_MUTATION

    anyio.run(_run)

    assert [item[1]["dry_run"] for item in before_client.calls] == [True]
    assert [item[1]["dry_run"] for item in after_client.calls] == [True, False]


def test_reconciliation_fault_is_coordinator_scoped_and_none_is_transparent() -> None:
    """Interrupt canonical review only on the coordinator-labelled client."""
    data_client = _Client()
    data = recovery_mcp_client_decorator(BEFORE_RETURN_RECONCILIATION)(
        AgentRole.DATA_RESEARCH,
        data_client,
    )
    coordinator_client = _Client()
    coordinator = recovery_mcp_client_decorator(BEFORE_RETURN_RECONCILIATION)(
        AgentRole.RESEARCH_COORDINATOR,
        coordinator_client,
    )
    transparent_client = _Client()
    transparent = recovery_mcp_client_decorator(NO_FAULT)(
        AgentRole.RESEARCH_COORDINATOR,
        transparent_client,
    )

    async def _run() -> None:
        await data.call_tool("research_read_artifact", {})
        with pytest.raises(InjectedProcessFault) as fault:
            await coordinator.call_tool("research_read_artifact", {})
        assert fault.value.role is AgentRole.RESEARCH_COORDINATOR
        result = await transparent.call_tool("research_read_artifact", {})
        structured = result["structuredContent"]
        assert isinstance(structured, Mapping)
        assert structured["ok"] is True

    anyio.run(_run)

    assert len(data_client.calls) == 1
    assert coordinator_client.calls == []
    assert len(transparent_client.calls) == 1


@pytest.mark.parametrize(
    ("mode", "tool_name", "result_ok"),
    (
        (BEFORE_STRATEGY_PACKAGE, "coding_package_candidate", True),
        (AFTER_STRATEGY_PACKAGE, "coding_package_candidate", True),
        (
            BEFORE_STRATEGY_REGISTRATION,
            "research_register_strategy_implementation",
            True,
        ),
        (
            AFTER_STRATEGY_REGISTRATION,
            "research_register_strategy_implementation",
            True,
        ),
        (
            BEFORE_STRATEGY_ADMISSION,
            "research_validate_strategy_implementation",
            True,
        ),
        (
            AFTER_STRATEGY_ADMISSION_FAILURE,
            "research_validate_strategy_implementation",
            False,
        ),
        (
            AFTER_STRATEGY_ADMISSION_SUCCESS,
            "research_validate_strategy_implementation",
            True,
        ),
    ),
)
def test_strategy_faults_fire_at_exact_package_registration_and_admission_edges(
    mode: str,
    tool_name: str,
    result_ok: bool,
) -> None:
    """Inject each Strategy fault at its exact pre-dispatch or observed-result boundary."""
    client = _Client(next_ok=result_ok)
    wrapped = recovery_mcp_client_decorator(mode)(
        AgentRole.STRATEGY_ENGINEERING,
        client,
    )

    async def _run() -> None:
        with pytest.raises(InjectedProcessFault) as fault:
            await wrapped.call_tool(tool_name, {})
        assert fault.value.mode == mode
        assert fault.value.tool_name == tool_name

    anyio.run(_run)

    expected_dispatches = 0 if mode.startswith("before_") else 1
    assert len(client.calls) == expected_dispatches


def test_strategy_repair_fault_requires_an_observed_failed_admission() -> None:
    """Fire a repair-write fault only after actionable admission failure."""
    client = _Client(next_ok=False)
    wrapped = recovery_mcp_client_decorator(BEFORE_STRATEGY_REPAIR_WRITE)(
        AgentRole.STRATEGY_ENGINEERING,
        client,
    )

    async def _run() -> None:
        await wrapped.call_tool("coding_write_candidate_file", {})
        await wrapped.call_tool("research_validate_strategy_implementation", {})
        with pytest.raises(InjectedProcessFault) as fault:
            await wrapped.call_tool("coding_write_candidate_file", {})
        assert fault.value.mode == BEFORE_STRATEGY_REPAIR_WRITE

    anyio.run(_run)

    assert [name for name, _ in client.calls] == [
        "coding_write_candidate_file",
        "research_validate_strategy_implementation",
    ]
