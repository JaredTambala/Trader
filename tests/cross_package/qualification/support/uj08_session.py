"""Real session lifecycle and fresh-process pause recovery for UJ-08."""

from __future__ import annotations

import asyncio
from dataclasses import replace
import json
import os
import sys
from typing import Any

from trader_agents import (
    OperatorInterruption,
    OperatorResponse,
    StaticJsonLlmClient,
    StdioMcpToolClient,
    StructuredModelRunner,
    open_postgres_checkpointer,
)
from tests.trader_agents.application_runtime.test_interrupt import _runtime
from tests.cross_package.qualification.support.uj08_campaign import (
    REPO_ROOT,
    checkout_commit,
)
from tests.cross_package.qualification.support.realistic_optimization_fixture import (
    build_realistic_optimization_fixture,
)


class PausedModelClient:
    """Hold a model call so the public operator command pauses real active work."""

    def __init__(self) -> None:
        self.entered = asyncio.Event()

    async def complete_json(self, llm_request: Any) -> Any:
        """Expose the active call and wait until the owning runtime cancels it."""
        del llm_request
        self.entered.set()
        await asyncio.Event().wait()


def campaign_runtime(
    dsn: str, saver: Any, *, model: Any | None = None
) -> tuple[Any, Any]:
    """Compose the current Coordinator graph with real MCP and Postgres checkpoints."""
    runtime, base_session = _runtime("workflow-uj08-real")
    fixture_scope = dict(base_session.scope_envelope["data_scope"])
    fixture_scope["scope_id"] = "uj08-session-scope"
    selection = build_realistic_optimization_fixture().selection
    fixture_scope["items"] = [
        {
            **fixture_scope["items"][0],
            "symbols": ["ALPHA", "BETA", "GAMMA"],
            "asset_class": "stocks",
            "timeframe": "1Hour",
            "start": selection.start.isoformat(),
            "end": selection.end.isoformat(),
            "permitted_providers": ["fixture"],
            "requirement_sources": ["UJ-08 retained operator brief"],
        }
    ]
    session = replace(
        base_session,
        operator_id="operator:jared",
        objective="Review the approved experiment and its independent-evidence blockers.",
        success_definition="Retain exact evidence and ask the human when independent review is unavailable.",
        scope_envelope={"data_scope": fixture_scope},
        implementation_specification={
            **base_session.implementation_specification,
            "repository_revision": checkout_commit(),
        },
    )
    runtime.checkpointer = saver
    runtime.coordinator.mcp_client = StdioMcpToolClient(
        command=sys.executable,
        args=["-m", "tests.cross_package.qualification.support.mcp_uj08_server"],
        cwd=REPO_ROOT,
        env={**os.environ, "UJ08_DSN": dsn},
        read_timeout_seconds=60,
    )
    if model is None:
        model = StaticJsonLlmClient(
            (
                {
                    "objective_summary": session.objective,
                    "material_ambiguities": [
                        "Independent review of the approved single-backtest scope is unavailable."
                    ],
                    "tasks": [],
                },
                {
                    "action": "ask_operator",
                    "summary": "Independent review is required before a stronger claim.",
                    "reviewed_delegation_ids": [],
                    "cited_evidence_refs": [],
                    "criteria_applied": ["Preserve independent evidence blockers."],
                    "affected_task_ids": [],
                    "operator_question": "Review the retained blocked outcome before authorising more research.",
                    "blockers": [],
                    "permitted_next_actions": ["answer or cancel"],
                },
            )
        )
    runtime.coordinator.model_runner = StructuredModelRunner(model)
    return runtime, session


async def pause_session(dsn: str, client: Any) -> dict[str, Any]:
    """Interrupt real active work and leave a durable operator-owned pause."""
    from tests.cross_package.qualification.support.uj08_campaign import call

    async with open_postgres_checkpointer(dsn=dsn, setup=True) as saver:
        gate = PausedModelClient()
        runtime, session = campaign_runtime(dsn, saver, model=gate)
        await call(
            client, "research_create_agent_session", {"session": session.to_dict()}
        )
        running = asyncio.create_task(runtime.start(session))
        try:
            await asyncio.wait_for(gate.entered.wait(), timeout=30)
            paused = await runtime.interrupt(
                session,
                OperatorInterruption(
                    operator_id=session.operator_id,
                    reason="Review the exact approved experiment before continuing.",
                ),
            )
            assert paused.kind == "operator_pause"
            assert running.cancelled()
            inspected = await runtime.inspect(session)
            assert inspected["status"] == "awaiting_operator"
            return {
                "session_id": session.session_id,
                "branch_id": inspected["branch_id"],
                "kind": paused.kind,
            }
        finally:
            if not running.done():
                running.cancel()


async def resume_session(dsn: str) -> dict[str, Any]:
    """Resume the same paused graph from a new process using public authority."""
    async with open_postgres_checkpointer(dsn=dsn) as saver:
        runtime, session = campaign_runtime(dsn, saver)
        prior = await runtime.inspect(session)
        assert prior["pending_interrupt"]["kind"] == "operator_pause"
        try:
            await runtime.resume(
                session,
                response=OperatorResponse(
                    approved=True,
                    answer="Unauthorized continuation",
                    operator_id="foreign-operator",
                ),
            )
        except ValueError as exc:
            assert "operator response identity" in str(exc)
        else:
            raise AssertionError("Foreign resume authority must fail closed")
        resumed = await runtime.resume(
            session,
            response=OperatorResponse(
                approved=True,
                answer="Continue only within the existing approved protocol.",
                operator_id=session.operator_id,
            ),
        )
        after = await runtime.inspect(session)
        assert after["branch_id"] == prior["branch_id"]
        assert after["operator_response"] == {}  # Accepted input is consumed once.
        assert after["status"] == "awaiting_operator"
        assert resumed.kind == "operator_clarification_required"
        return {
            "session_id": session.session_id,
            "branch_id": after["branch_id"],
            "status": after["status"],
            "decision_receipt_ref": after["decision_receipt_ref"],
            "model_calls": len(runtime.coordinator.model_runner.client.requests),
        }


def main() -> None:
    """Apply one real fresh-process resume without retaining private model data."""
    from tests.cross_package.qualification.support.mcp_uj08_server import campaign_dsn

    print(json.dumps(asyncio.run(resume_session(campaign_dsn())), sort_keys=True))


if __name__ == "__main__":
    main()
