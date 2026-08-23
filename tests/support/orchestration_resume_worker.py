"""Fresh-process driver for one controlled composition resume stage."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
import json
import os
import sys
from typing import Any

import anyio

from trader_agents import (
    PersistentStdioMcpToolClient,
    ResearchCompositionRequest,
    open_postgres_checkpointer,
    research_composition_thread_config,
    run_research_composition,
    specialist_thread_config,
)
from trader_agents.tool_client import McpToolClient
from trader_research.governance import ExperimentProtocol
from trader_research.infrastructure.postgres import PostgresResearchArtifactStore
from tests.support.orchestration_qualification import (
    CallEvidence,
    RecordingMcpToolClient,
    persist_call_evidence,
)
from tests.support.postgres_verification import (
    REPO_ROOT,
    checkpoint_test_conninfo,
    load_test_settings,
)


@dataclass
class _LoseOneResponseClient:
    """Raise once after a selected public call has returned successfully."""

    delegate: RecordingMcpToolClient
    tool_name: str
    lost: bool = False

    async def call_tool(
        self,
        tool_name: str,
        arguments: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        """Delegate the call, then simulate one transport response loss."""
        result = await self.delegate.call_tool(tool_name, arguments)
        if tool_name == self.tool_name and not self.lost:
            self.lost = True
            latest = self.delegate.calls[-1]
            self.delegate.calls[-1] = replace(
                latest,
                retry_disposition="response_lost",
            )
            raise RuntimeError("controlled response-loss fault")
        return result


async def _run_stage(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    request_payload = _mapping(payload.get("request"), "request")
    request = ResearchCompositionRequest.from_dict(request_payload)
    raw_protocol = payload.get("protocol")
    protocol = (
        ExperimentProtocol.from_dict(_mapping(raw_protocol, "protocol"))
        if raw_protocol is not None
        else None
    )
    phase = _required_text(payload.get("phase"), "phase")
    setup = payload.get("setup", False)
    if not isinstance(setup, bool):
        raise ValueError("setup must be a boolean")
    reset = payload.get("reset", False)
    if not isinstance(reset, bool):
        raise ValueError("reset must be a boolean")
    max_calls_value = payload.get("max_workflow_tool_calls")
    max_calls = None
    if max_calls_value is not None:
        if isinstance(max_calls_value, bool) or not isinstance(max_calls_value, int):
            raise ValueError("max_workflow_tool_calls must be an integer")
        if max_calls_value <= 0:
            raise ValueError("max_workflow_tool_calls must be positive")
        max_calls = max_calls_value
    lose_response_after_tool = str(payload.get("lose_response_after_tool") or "").strip()
    settings = load_test_settings(required=True)
    if settings is None:  # pragma: no cover - required=True fails first
        raise RuntimeError("PG_TEST settings are required")
    artifact_store = PostgresResearchArtifactStore(**settings.connect_kwargs())
    server_env = dict(os.environ)
    persistent = PersistentStdioMcpToolClient(
        command=sys.executable,
        args=("-m", "tests.support.mcp_postgres_orchestration_server"),
        cwd=REPO_ROOT,
        env=server_env,
        read_timeout_seconds=300,
    )
    recording = RecordingMcpToolClient(persistent)
    tool_client: McpToolClient = recording
    if lose_response_after_tool:
        tool_client = _LoseOneResponseClient(
            delegate=recording,
            tool_name=lose_response_after_tool,
        )
    try:
        async with open_postgres_checkpointer(
            dsn=checkpoint_test_conninfo(),
            setup=setup,
        ) as checkpointer:
            if reset:
                await _reset_composition_threads(checkpointer, request)
            async with persistent:
                result = await run_research_composition(
                    request=request,
                    protocol=protocol,
                    tool_client=tool_client,
                    artifact_store=artifact_store,
                    checkpointer=checkpointer,
                    max_workflow_tool_calls=max_calls,
                )
        return {
            "result": result,
            "calls": [_call_to_dict(call) for call in recording.calls],
        }
    finally:
        try:
            if recording.calls:
                persist_call_evidence(
                    phase=phase,
                    composition_id=request.composition_id,
                    calls=recording.calls,
                )
        finally:
            artifact_store.close()


def _call_to_dict(call: CallEvidence) -> Mapping[str, Any]:
    return {
        "command": call.command,
        "argument_digest": call.argument_digest,
        "result_identity": dict(call.result_identity),
        "retry_disposition": call.retry_disposition,
    }


async def _reset_composition_threads(
    checkpointer: Any,
    request: ResearchCompositionRequest,
) -> None:
    """Delete only the exact qualification threads before a controlled rerun."""
    composition_config = research_composition_thread_config(request.composition_id)
    existing = await checkpointer.aget_tuple(
        composition_config,
    )
    if existing is not None:
        workflow_id = str(
            existing.checkpoint["channel_values"].get("workflow_id") or ""
        )
        if workflow_id:
            await checkpointer.adelete_thread(workflow_id)
    composition_thread = str(
        composition_config["configurable"]["thread_id"]
    )
    await checkpointer.adelete_thread(composition_thread)
    for task in request.specialist_tasks:
        specialist_config = specialist_thread_config(task)
        specialist_thread = str(
            specialist_config["configurable"]["thread_id"]
        )
        await checkpointer.adelete_thread(specialist_thread)


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be a mapping")
    return value


def _required_text(value: object, label: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{label} is required")
    return normalized


def main() -> None:
    """Read one strict stage request from stdin and emit bounded JSON output."""
    payload = json.load(sys.stdin)
    if not isinstance(payload, Mapping):
        raise SystemExit("worker input must be a mapping")
    allowed = {
        "request",
        "protocol",
        "phase",
        "setup",
        "reset",
        "max_workflow_tool_calls",
        "lose_response_after_tool",
    }
    unknown = sorted(set(payload).difference(allowed))
    if unknown:
        raise SystemExit(f"worker input contains unknown fields: {unknown}")
    result = anyio.run(_run_stage, payload)
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
