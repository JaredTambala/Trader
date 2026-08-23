"""Postgres restart evidence for specialist-to-workflow composition."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import cast

import anyio
from langchain_core.runnables import RunnableConfig
from psycopg.conninfo import make_conninfo
import pytest

from tests.test_research_composition import _prepare_composition, _protocol
from trader_agents import (
    AcceptedSpecialistResult,
    open_postgres_checkpointer,
    research_composition_thread_config,
    run_research_composition,
    specialist_thread_config,
)
from trader_mcp.constants import (
    DATA_CREATE_RESEARCH_SNAPSHOT_TOOL,
    RESEARCH_RECORD_WORKFLOW_OUTCOME_TOOL,
    RESEARCH_REGISTER_EXPERIMENT_WORKFLOW_TOOL,
)
from trader_research.governance import (
    DATASET_MANIFEST,
    DATA_QUALITY_REPORT,
    ExperimentProtocolStatus,
)


pytestmark = pytest.mark.postgres


def test_fresh_savers_resume_composition_without_replaying_children(
    postgres_settings: dict[str, object],
    tmp_path: Path,
) -> None:
    """Restart after Data and during workflow execution without accepted replay."""
    dsn = make_conninfo(
        "", **cast(dict[str, str | int | None], postgres_settings)
    )

    async def _run() -> None:
        prepared = await _prepare_composition(tmp_path)
        request = prepared.request
        client = prepared.client
        composition_config = cast(
            RunnableConfig,
            research_composition_thread_config(request.composition_id),
        )
        specialist_config = cast(
            RunnableConfig,
            specialist_thread_config(request.specialist_tasks[0]),
        )
        composition_thread = str(
            composition_config["configurable"]["thread_id"]
        )
        specialist_thread = str(
            specialist_config["configurable"]["thread_id"]
        )

        async with open_postgres_checkpointer(dsn=dsn, setup=True) as first_saver:
            old_checkpoint = await first_saver.aget_tuple(composition_config)
            if old_checkpoint is not None:
                old_workflow_id = str(
                    old_checkpoint.checkpoint["channel_values"].get(
                        "workflow_id",
                        "",
                    )
                )
                if old_workflow_id:
                    await first_saver.adelete_thread(old_workflow_id)
            await first_saver.adelete_thread(composition_thread)
            await first_saver.adelete_thread(specialist_thread)
            awaiting_protocol = await run_research_composition(
                request=request,
                protocol=None,
                tool_client=client,
                artifact_store=prepared.store,
                checkpointer=first_saver,
            )
            assert awaiting_protocol["status"] == "awaiting_prerequisite"
            assert [name for name, _ in client.calls].count(
                DATA_CREATE_RESEARCH_SNAPSHOT_TOOL
            ) == 1

        receipt = AcceptedSpecialistResult.from_dict(
            awaiting_protocol["accepted_specialist_results"][0]
        )
        refs = {item.artifact_type: item for item in receipt.artifact_refs}
        approved = _protocol(
            objective=prepared.objective,
            strategy_ref=prepared.strategy_ref,
            risk_ref=prepared.risk_ref,
            manifest_ref=refs[DATASET_MANIFEST],
            quality_ref=refs[DATA_QUALITY_REPORT],
            status=ExperimentProtocolStatus.APPROVED,
        )

        async with open_postgres_checkpointer(dsn=dsn) as second_saver:
            interrupted = await run_research_composition(
                request=request,
                protocol=approved,
                tool_client=client,
                artifact_store=prepared.store,
                checkpointer=second_saver,
                max_workflow_tool_calls=4,
            )
            assert interrupted["status"] == "interrupted"
            calls_after_interruption = [name for name, _ in client.calls]
            accepted_workflow_tools = calls_after_interruption[3:]
            assert interrupted["workflow_id"]

        async with open_postgres_checkpointer(dsn=dsn) as third_saver:
            completed = await run_research_composition(
                request=request,
                protocol=approved,
                tool_client=client,
                artifact_store=prepared.store,
                checkpointer=third_saver,
            )
            assert completed["status"] == "completed"
            all_tools = [name for name, _ in client.calls]
            assert all_tools.count(DATA_CREATE_RESEARCH_SNAPSHOT_TOOL) == 1
            assert all_tools.count(RESEARCH_REGISTER_EXPERIMENT_WORKFLOW_TOOL) == 1
            assert all_tools.count(RESEARCH_RECORD_WORKFLOW_OUTCOME_TOOL) == 1
            for tool_name in accepted_workflow_tools:
                assert all_tools.count(tool_name) == accepted_workflow_tools.count(
                    tool_name
                )
            checkpoint = await third_saver.aget_tuple(composition_config)
            assert checkpoint is not None
            checkpoint_text = str(checkpoint.checkpoint["channel_values"])
            assert "structuredContent" not in checkpoint_text
            assert "source_code" not in checkpoint_text

        call_count = len(client.calls)
        async with open_postgres_checkpointer(dsn=dsn) as fourth_saver:
            replay = await run_research_composition(
                request=request,
                protocol=replace(
                    approved,
                    status=ExperimentProtocolStatus.APPROVED,
                ),
                tool_client=client,
                artifact_store=prepared.store,
                checkpointer=fourth_saver,
            )
            assert replay["outcome_ref"] == completed["outcome_ref"]
            assert len(client.calls) == call_count
            await fourth_saver.adelete_thread(composition_thread)
            await fourth_saver.adelete_thread(specialist_thread)
            await fourth_saver.adelete_thread(str(completed["workflow_id"]))

    anyio.run(_run)
