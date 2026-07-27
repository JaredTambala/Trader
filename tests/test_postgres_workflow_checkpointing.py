from __future__ import annotations

import anyio
from langgraph.types import Command
from psycopg.conninfo import make_conninfo
import pytest

from trader_agents.checkpointing import (
    build_resumable_workflow_graph,
    build_workflow_checkpoint_state,
    open_postgres_checkpointer,
    workflow_thread_config,
)
from tests.support.workflow_checkpoint_fixture import (
    checkpoint_step_result as _result,
)
from tests.support.workflow_checkpoint_fixture import (
    checkpoint_workflow_plan as _plan,
)


pytestmark = pytest.mark.postgres


def test_fresh_postgres_saver_resumes_checkpointed_workflow(
    postgres_settings: dict[str, object],
) -> None:
    dsn = make_conninfo(**postgres_settings)
    plan = _plan()
    workflow_id = "workflow_postgres_resume"
    config = workflow_thread_config(workflow_id)

    async def _run() -> None:
        async with open_postgres_checkpointer(
            dsn=dsn,
            setup=True,
        ) as first_saver:
            await first_saver.adelete_thread(workflow_id)
            first_graph = build_resumable_workflow_graph(
                plan=plan,
                checkpointer=first_saver,
            )
            interrupted = await first_graph.ainvoke(
                build_workflow_checkpoint_state(
                    workflow_id=workflow_id,
                    plan=plan,
                ),
                config,
            )
            assert interrupted["pending_step_id"] == "inventory"

        async with open_postgres_checkpointer(dsn=dsn) as resumed_saver:
            resumed_graph = build_resumable_workflow_graph(
                plan=plan,
                checkpointer=resumed_saver,
            )
            resumed = await resumed_graph.ainvoke(
                Command(
                    resume=_result(
                        workflow_id=workflow_id,
                        step_id="inventory",
                    ).to_dict()
                ),
                config,
            )
            assert resumed["pending_step_id"] == "quality"
            assert len(resumed["step_attempts"]) == 1

            completed = await resumed_graph.ainvoke(
                Command(
                    resume=_result(
                        workflow_id=workflow_id,
                        step_id="quality",
                    ).to_dict()
                ),
                config,
            )
            assert completed["status"] == "completed"
            checkpoint = await resumed_saver.aget_tuple(config)
            assert checkpoint is not None
            assert checkpoint.checkpoint["channel_values"]["status"] == (
                "completed"
            )
            await resumed_saver.adelete_thread(workflow_id)

    anyio.run(_run)
