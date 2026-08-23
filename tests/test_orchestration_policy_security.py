"""Fail-closed and bounded-evidence checks for orchestration qualification."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
import json
from typing import Any

import anyio
import pytest

from tests.support.orchestration_qualification import (
    RecordingMcpToolClient,
    prepare_qualification_request,
)
from tests.support.realistic_optimization_fixture import (
    build_realistic_optimization_fixture,
)
from tests.test_research_composition import _data_task, _objective
from trader_agents import ResearchCompositionRequest, build_agent_identity
from trader_mcp.constants import CAPABILITY_REGISTRATION_FLAGS
from trader_research.governance.ownership import AGENT_DEFINITIONS


@dataclass(frozen=True)
class _SensitiveResultClient:
    """Return a representative result containing data that must not be retained."""

    async def call_tool(
        self,
        tool_name: str,
        arguments: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        """Return public identifiers alongside deliberately sensitive payload fields."""
        return {
            "content": [{"type": "text", "text": "raw-response-body"}],
            "structuredContent": {
                "result": {
                    "artifact_id": "artifact_demo",
                    "artifact_uri": "research://postgres/workflow_plan/artifact_demo",
                    "status": "created",
                    "source_code": "do_not_persist = True",
                    "approval_rationale": "operator private rationale",
                    "credentials": "secret-token",
                }
            },
            "isError": False,
        }


@dataclass
class _PreparationClient:
    """Return bounded canonical identities needed to build a qualification request."""

    snapshot_count: int = 0

    async def call_tool(
        self,
        tool_name: str,
        arguments: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        """Return deterministic artifacts for each setup operation."""
        del arguments
        artifacts: dict[str, Any] = {}
        if tool_name == "research_register_strategy_implementation":
            artifacts["implementation_version"] = _artifact(
                "implementation_version", "strategy_implementation"
            )
        elif tool_name == "research_register_risk_manager_implementation":
            artifacts["implementation_version"] = _artifact(
                "implementation_version", "risk_implementation"
            )
        elif tool_name == "research_register_optimization_objective":
            artifacts["implementation_version"] = _artifact(
                "implementation_version", "objective_implementation"
            )
        elif tool_name == "research_validate_optimization_objective":
            artifacts["implementation_validation_report"] = _artifact(
                "implementation_validation_report", "objective_validation"
            )
        elif tool_name == "data_create_research_snapshot":
            self.snapshot_count += 1
            suffix = str(self.snapshot_count)
            artifacts["dataset_manifest"] = _artifact(
                "dataset_manifest", f"manifest_{suffix}"
            )
            artifacts["data_quality_report"] = _artifact(
                "data_quality_report", f"quality_{suffix}"
            )
        return {
            "content": [],
            "structuredContent": {
                "ok": True,
                "command": tool_name,
                "data": {},
                "artifacts": artifacts,
                "warnings": [],
                "errors": [],
            },
            "isError": False,
        }


def test_call_evidence_retains_digests_and_identities_only() -> None:
    """Prove the qualification ledger projection excludes request/result payloads."""

    async def _run() -> None:
        client = RecordingMcpToolClient(_SensitiveResultClient())
        result = await client.call_tool(
            "research_register_experiment_workflow",
            {
                "workflow": {"source_code": "secret implementation"},
                "credential": "secret-token",
            },
        )
        assert result["structuredContent"]["result"]["artifact_id"] == (
            "artifact_demo"
        )
        assert len(client.calls) == 1
        call = client.calls[0]
        assert len(call.argument_digest) == 64
        assert call.result_identity["result.result.artifact_id"] == "artifact_demo"
        serialized = json.dumps(
            {
                "command": call.command,
                "argument_digest": call.argument_digest,
                "result_identity": call.result_identity,
                "retry_disposition": call.retry_disposition,
            },
            sort_keys=True,
        )
        assert "source_code" not in serialized
        assert "secret-token" not in serialized
        assert "private rationale" not in serialized
        assert "raw-response-body" not in serialized

    anyio.run(_run)


def test_controlled_fixture_builds_explicit_data_then_design_tasks() -> None:
    """Prove the realistic fixture creates no inferred or dynamically bound task."""

    async def _run() -> None:
        request = await prepare_qualification_request(
            tool_client=_PreparationClient(),
            fixture=build_realistic_optimization_fixture(),
        )
        assert len(request.specialist_tasks) == 3
        assert [task.authority_key for task in request.specialist_tasks] == [
            "data_agent",
            "data_agent",
            "experiment_design_agent",
        ]
        design = request.specialist_tasks[-1].specialist_input
        assert design["optimization"]["trial_budget"] == 4
        assert design["optimization"]["dimensions"][0]["choices"] == [2, 3, 4, 5]

    anyio.run(_run)


def test_ninth_explicit_specialist_task_is_rejected_before_execution() -> None:
    """Prove composition task bounds apply at the immutable request boundary."""
    objective = _objective()
    tasks = tuple(
        replace(
            _data_task(objective, "composition_task_limit"),
            task_id=f"data_task_{index}",
        )
        for index in range(9)
    )
    with pytest.raises(ValueError, match="specialist task limit"):
        ResearchCompositionRequest(
            composition_id="composition_task_limit",
            objective=objective,
            specialist_tasks=tasks,
            requested_by="operator:test",
            actor="research_coordinator",
        )


def test_research_agent_catalogs_expose_no_runtime_control_capability() -> None:
    """Prove registered identities cannot acquire prohibited operator authority."""
    assert CAPABILITY_REGISTRATION_FLAGS["broker_mutating_tools_registered"] is False
    assert CAPABILITY_REGISTRATION_FLAGS["raw_sql_tools_registered"] is False
    forbidden_fragments = (
        "broker",
        "raw_sql",
        "halt",
        "order_reconcile",
        "reconcile_orders",
    )
    for definition in AGENT_DEFINITIONS:
        identity = build_agent_identity(definition.key)
        assert not {
            tool_name
            for tool_name in identity.tool_allowlist
            if any(fragment in tool_name for fragment in forbidden_fragments)
        }


def _artifact(artifact_type: str, artifact_id: str) -> Mapping[str, str]:
    return {
        "artifact_type": artifact_type,
        "artifact_id": artifact_id,
        "uri": f"research://postgres/{artifact_type}/{artifact_id}",
    }
