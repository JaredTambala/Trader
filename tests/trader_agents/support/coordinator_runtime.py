"""MCP double for Research Coordinator lifecycle and recovery tests.

Subject: Canonical session, evidence resolution, and decision-receipt behavior observed by the Coordinator.
Level: Test support.
Collaborators: In-memory MCP behavior returning real public observations and deterministic evidence payloads.
Guarantees: Coordinator tests can distinguish accepted canonical writes, lost responses, and replay-safe reads.
Non-goals: Real MCP transport, Postgres persistence, specialist model behavior, and research correctness."""

from __future__ import annotations
import asyncio
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any
from trader_agents import (
    AgentPhase,
    AgentRole,
    McpToolDescription,
    first_slice_tool_catalogue,
)
from tests.trader_agents.support.runtime_contracts import _mcp_artifacts
from tests.trader_agents.support.runtime_contracts import _evidence_payload


@dataclass
class _CoordinatorMcpClient:
    """Coordinator MCP fake with canonical reads and decision receipts."""

    session_ref: Mapping[str, Any]
    artifacts: Mapping[str, Mapping[str, Any]]
    read_calls: int = 0
    interrupt_decision_once: bool = False
    decision_payloads: list[dict[str, Any]] = field(default_factory=list)

    async def list_tools(self) -> Sequence[McpToolDescription]:
        """Expose every coordinator capability with permissive test schemas."""
        catalogue = first_slice_tool_catalogue()
        names = {
            definition.name
            for phase in AgentPhase
            for definition in catalogue.available(
                role=AgentRole.RESEARCH_COORDINATOR,
                phase=phase,
                approval_policy={},
            )
        }
        return tuple(
            McpToolDescription(
                name=name,
                description=f"Test schema for {name}.",
                input_schema={"type": "object", "additionalProperties": True},
            )
            for name in sorted(names)
        )

    async def call_tool(
        self,
        tool_name: str,
        arguments: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        """Persist session/receipt identities and verify exact test refs."""
        side_effect = "read_only"
        data: dict[str, Any]
        artifacts: Mapping[str, Any]
        if tool_name == "research_create_agent_session":
            side_effect = "local_mutating"
            data = {"research_session": arguments["session"]}
            artifacts = {"research_session": self.session_ref}
        elif tool_name == "research_read_artifact":
            self.read_calls += 1
            reference = self.artifacts[str(arguments["artifact_ref"])]
            data = {
                "record": {
                    "artifact_type": reference["artifact_type"],
                    "artifact_id": reference["artifact_id"],
                    "domain_owner": reference["domain_owner"],
                    "producer_tool": "test_fixture",
                    "status": "passed",
                    "payload_hash": "a" * 64,
                    "source_hash": None,
                }
            }
            artifacts = {"artifact": reference}
        elif tool_name == "research_record_agent_decision":
            side_effect = "local_mutating"
            receipt = arguments["receipt"]
            assert isinstance(receipt, Mapping)
            self.decision_payloads.append(dict(receipt))
            if self.interrupt_decision_once and len(self.decision_payloads) == 1:
                raise asyncio.CancelledError
            receipt_id = str(receipt["receipt_id"])
            reference = _evidence_payload(
                "agent_decision_receipt",
                receipt_id,
                domain_owner="Orchestration",
            )
            data = {"agent_decision_receipt": receipt}
            artifacts = {"agent_decision_receipt": reference}
        else:
            raise AssertionError(f"unexpected coordinator tool: {tool_name}")
        return {
            "structuredContent": {
                "ok": True,
                "command": tool_name,
                "agent_owner": "Research Coordinator",
                "side_effect": side_effect,
                "data": data,
                "artifacts": _mcp_artifacts(artifacts),
                "warnings": [],
                "errors": [],
            },
            "isError": False,
        }
