from __future__ import annotations

import anyio
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
import pytest

from trader_agents.checkpointing import (
    OperationalHandoffSummary,
    build_resumable_workflow_graph,
    build_workflow_checkpoint_state,
    checkpoint_dsn_from_env,
    checkpoint_runtime_summary,
    workflow_public_state,
    workflow_thread_config,
)
from trader_agents.checkpointing.postgres import CheckpointConfigurationError
from trader_research.governance import (
    DATA_QUALITY_REPORT,
    DATASET_MANIFEST,
    RetryDisposition,
    SpecialistHandoff,
    WorkflowStepStatus,
)
from trader_research.governance.handoffs import artifact_report_ref
from tests.support.workflow_checkpoint_fixture import (
    checkpoint_step_result as _result,
)
from tests.support.workflow_checkpoint_fixture import (
    checkpoint_workflow_plan as _plan,
)


def test_checkpoint_graph_interrupts_resumes_and_excludes_raw_result_data() -> None:
    saver = InMemorySaver()
    plan = _plan()
    graph = build_resumable_workflow_graph(plan=plan, checkpointer=saver)
    workflow_id = "workflow_run_demo"
    config = workflow_thread_config(workflow_id)
    initial = build_workflow_checkpoint_state(
        workflow_id=workflow_id,
        plan=plan,
    )

    async def _run() -> None:
        first = await graph.ainvoke(initial, config)
        assert first["status"] == "awaiting_result"
        assert first["pending_step_id"] == "inventory"
        assert first["__interrupt__"][0].value["producer_tool"] == (
            "data_get_inventory"
        )

        inventory_result = _result(
            workflow_id=workflow_id,
            step_id="inventory",
            public_data={
                "raw_tool_payload": {"api_key": "must-not-persist"},
                "feature_matrix": [[1.0, 2.0]],
            },
        )
        second = await graph.ainvoke(
            Command(resume=inventory_result.to_dict()),
            config,
        )
        assert second["status"] == "awaiting_result"
        assert second["pending_step_id"] == "quality"
        assert len(second["step_attempts"]) == 1

        snapshot = await graph.aget_state(config)
        checkpoint_text = repr(snapshot.values)
        assert "must-not-persist" not in checkpoint_text
        assert "raw_tool_payload" not in checkpoint_text
        assert "feature_matrix" not in checkpoint_text
        assert "public_data" not in checkpoint_text

        final = await graph.ainvoke(
            Command(
                resume=_result(
                    workflow_id=workflow_id,
                    step_id="quality",
                ).to_dict()
            ),
            config,
        )
        assert final["status"] == "completed"
        assert final["pending_step_id"] == ""
        assert len(final["step_attempts"]) == 2
        public = workflow_public_state(final)
        assert set(public) == {
            "workflow_id",
            "plan_id",
            "status",
            "public_status",
            "pending_step_id",
            "next_attempt",
            "step_attempts",
            "handoff_summaries",
            "warnings",
            "blockers",
            "errors",
        }
        assert "processed_result_digests" not in public
        assert "plan_digest" not in public

    anyio.run(_run)


def test_checkpoint_graph_ignores_exact_duplicate_and_blocks_conflict() -> None:
    saver = InMemorySaver()
    plan = _plan()
    graph = build_resumable_workflow_graph(plan=plan, checkpointer=saver)
    workflow_id = "workflow_run_idempotency"
    config = workflow_thread_config(workflow_id)
    result = _result(
        workflow_id=workflow_id,
        step_id="inventory",
        idempotency_key="inventory-key",
    )

    async def _run() -> None:
        await graph.ainvoke(
            build_workflow_checkpoint_state(
                workflow_id=workflow_id,
                plan=plan,
            ),
            config,
        )
        next_step = await graph.ainvoke(Command(resume=result.to_dict()), config)
        assert next_step["pending_step_id"] == "quality"
        assert len(next_step["step_attempts"]) == 1

        duplicate = await graph.ainvoke(
            Command(resume=result.to_dict()),
            config,
        )
        assert duplicate["pending_step_id"] == "quality"
        assert len(duplicate["step_attempts"]) == 1
        assert duplicate["warnings"][-1]["code"] == (
            "duplicate_step_result_ignored"
        )

        conflicting = _result(
            workflow_id=workflow_id,
            step_id="inventory",
            idempotency_key="inventory-key",
            public_data={"changed": True},
        )
        failed = await graph.ainvoke(
            Command(resume=conflicting.to_dict()),
            config,
        )
        assert failed["status"] == "failed"
        assert failed["errors"][-1]["code"] == "idempotency_conflict"
        assert len(failed["step_attempts"]) == 1

    anyio.run(_run)


def test_checkpoint_graph_retries_and_rejects_plan_drift() -> None:
    saver = InMemorySaver()
    plan = _plan()
    workflow_id = "workflow_run_retry"
    config = workflow_thread_config(workflow_id)
    graph = build_resumable_workflow_graph(plan=plan, checkpointer=saver)

    async def _run() -> None:
        await graph.ainvoke(
            build_workflow_checkpoint_state(
                workflow_id=workflow_id,
                plan=plan,
            ),
            config,
        )
        retry = await graph.ainvoke(
            Command(
                resume=_result(
                    workflow_id=workflow_id,
                    step_id="inventory",
                    status=WorkflowStepStatus.BLOCKED,
                    retry=RetryDisposition.RETRYABLE,
                ).to_dict()
            ),
            config,
        )
        assert retry["pending_step_id"] == "inventory"
        assert retry["next_attempt"] == 2
        assert retry["public_status"] == "awaiting_step_result"

        drifted_graph = build_resumable_workflow_graph(
            plan=_plan(quality_threshold=0.95),
            checkpointer=saver,
        )
        with pytest.raises(ValueError, match="plan digest"):
            await drifted_graph.ainvoke(
                Command(
                    resume=_result(
                        workflow_id=workflow_id,
                        step_id="inventory",
                        attempt=2,
                    ).to_dict()
                ),
                config,
            )

    anyio.run(_run)


def test_checkpoint_graph_rejects_undeclared_and_excess_outputs() -> None:
    plan = _plan()

    async def _execute(payload: dict[str, object]) -> dict[str, object]:
        workflow_id = str(payload["requested_by"])
        graph = build_resumable_workflow_graph(
            plan=plan,
            checkpointer=InMemorySaver(),
        )
        config = workflow_thread_config(workflow_id)
        await graph.ainvoke(
            build_workflow_checkpoint_state(
                workflow_id=workflow_id,
                plan=plan,
            ),
            config,
        )
        return await graph.ainvoke(Command(resume=payload), config)

    undeclared = _result(
        workflow_id="workflow_undeclared_output",
        step_id="inventory",
    ).to_dict()
    undeclared["produced_artifact_refs"].append(
        artifact_report_ref(
            DATA_QUALITY_REPORT,
            "unexpected_quality",
        ).to_dict()
    )
    undeclared_result = anyio.run(_execute, undeclared)
    assert undeclared_result["status"] == "failed"
    assert "undeclared artifact types" in undeclared_result["errors"][-1]["message"]

    excess = _result(
        workflow_id="workflow_excess_output",
        step_id="inventory",
    ).to_dict()
    excess["produced_artifact_refs"].append(
        artifact_report_ref(
            DATASET_MANIFEST,
            "unexpected_second_manifest",
        ).to_dict()
    )
    excess_result = anyio.run(_execute, excess)
    assert excess_result["status"] == "failed"
    assert "exceeds cardinality" in excess_result["errors"][-1]["message"]


def test_checkpoint_handoffs_require_canonical_refs_and_drop_payloads() -> None:
    canonical = SpecialistHandoff(
        handoff_id="handoff_dataset",
        domain_owner="Data",
        producer_tool="data_get_inventory",
        requested_by="workflow_run",
        actor="Data Agent",
        artifact_type=DATASET_MANIFEST,
        artifact_uri=(
            "research://postgres/dataset_manifest/dataset_manifest_demo"
        ),
        payload={"must_not_checkpoint": True},
        source_request={"symbols": ["EURUSD"]},
    )
    summary = OperationalHandoffSummary.from_handoff(canonical).to_dict()

    assert summary["artifact_ref"]["artifact_id"] == "dataset_manifest_demo"
    assert "payload" not in summary
    assert "source_request" not in summary
    with pytest.raises(ValueError, match="payload-only handoffs"):
        OperationalHandoffSummary.from_handoff(
            SpecialistHandoff(
                handoff_id="payload_only",
                domain_owner="Data",
                producer_tool="data_get_inventory",
                requested_by="workflow_run",
                actor="Data Agent",
                artifact_type=DATASET_MANIFEST,
                payload={"dataset_id": "dataset_demo"},
            )
        )


def test_checkpoint_runtime_configuration_is_explicit_and_credential_free() -> None:
    with pytest.raises(CheckpointConfigurationError, match="is required"):
        checkpoint_dsn_from_env({})
    dsn = "postgresql://user:secret@localhost:5432/trader_test"
    assert checkpoint_dsn_from_env({"TRADER_AGENTS_CHECKPOINT_DSN": dsn}) == dsn
    summary = checkpoint_runtime_summary(
        {"TRADER_AGENTS_CHECKPOINT_DSN": dsn}
    )

    assert summary == {
        "backend": "postgres",
        "configured": True,
        "persistent": True,
        "canonical_research_evidence": False,
    }
    assert "secret" not in repr(summary)
