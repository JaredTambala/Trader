"""Postgres restart evidence for the resumable Data specialist."""

from __future__ import annotations

import anyio
from psycopg.conninfo import make_conninfo
import pytest

from tests.test_data_specialist import RecordingDataMcpClient, _task
from trader_agents import (
    build_data_specialist_graph,
    open_postgres_checkpointer,
    run_specialist_task,
    specialist_thread_config,
)
from trader_research.foundation import InMemoryResearchArtifactStore


pytestmark = pytest.mark.postgres


def test_fresh_postgres_saver_does_not_repeat_accepted_data_actions(
    postgres_settings: dict[str, object],
) -> None:
    """Resume terminal state through a new saver connection without MCP replay."""
    dsn = make_conninfo(**postgres_settings)
    store = InMemoryResearchArtifactStore()
    client = RecordingDataMcpClient(store)
    task = _task()
    config = specialist_thread_config(task)
    thread_id = str(config["configurable"]["thread_id"])

    async def _run() -> None:
        async with open_postgres_checkpointer(dsn=dsn, setup=True) as first_saver:
            await first_saver.adelete_thread(thread_id)
            first_graph = build_data_specialist_graph(
                tool_client=client,
                artifact_store=store,
                checkpointer=first_saver,
            )
            first = await run_specialist_task(graph=first_graph, task=task)
            assert first["status"] == "completed"
            assert len(client.calls) == 2

        async with open_postgres_checkpointer(dsn=dsn) as resumed_saver:
            resumed_graph = build_data_specialist_graph(
                tool_client=client,
                artifact_store=store,
                checkpointer=resumed_saver,
            )
            resumed = await run_specialist_task(graph=resumed_graph, task=task)
            assert resumed["result"] == first["result"]
            assert len(client.calls) == 2
            checkpoint = await resumed_saver.aget_tuple(config)
            assert checkpoint is not None
            values = checkpoint.checkpoint["channel_values"]
            assert values["status"] == "completed"
            assert "structuredContent" not in str(values)
            await resumed_saver.adelete_thread(thread_id)

    anyio.run(_run)
