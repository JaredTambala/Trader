"""Postgres saver restart evidence for the Experiment Design specialist."""

from __future__ import annotations

from typing import cast

import anyio
from psycopg.conninfo import make_conninfo
import pytest

from tests.test_experiment_design import _prepared_design
from tests.test_experiment_design_specialist import _InProcessMcpClient
from trader_agents import (
    SpecialistResult,
    SpecialistResultStatus,
    build_experiment_design_graph,
    build_experiment_design_task,
    open_postgres_checkpointer,
)
from trader_agents.specialists import run_specialist_task, specialist_thread_config
from trader_mcp.constants import (
    RESEARCH_CREATE_EXPERIMENT_PROTOCOL_PROPOSAL_TOOL,
)
from trader_mcp.environment import load_local_environment
from trader_mcp.server import create_server


pytestmark = pytest.mark.postgres


def test_fresh_saver_reuses_accepted_protocol_proposal(
    postgres_settings: dict[str, object],
) -> None:
    """Reopen the saver without repeating the accepted proposal mutation."""
    dsn = make_conninfo(
        "", **cast(dict[str, str | int | None], postgres_settings)
    )

    async def _run() -> None:
        store, objective, design = _prepared_design()
        server = create_server(
            load_local_environment("env.template"),
            research_artifact_store_provider=lambda: store,
        )
        client = _InProcessMcpClient(server)
        task = build_experiment_design_task(
            request=design,
            objective=objective,
            requested_by="postgres_design_composition",
            actor="research_coordinator",
            permit_local_mutation=True,
        )
        config = specialist_thread_config(task)
        thread_id = str(config["configurable"]["thread_id"])

        async with open_postgres_checkpointer(dsn=dsn, setup=True) as first:
            await first.adelete_thread(thread_id)
            graph = build_experiment_design_graph(
                tool_client=client,
                artifact_store=store,
                checkpointer=first,
            )
            result = SpecialistResult.from_dict(
                (await run_specialist_task(graph=graph, task=task))["result"]
            )
            assert result.status is SpecialistResultStatus.COMPLETED

        async with open_postgres_checkpointer(dsn=dsn) as second:
            graph = build_experiment_design_graph(
                tool_client=client,
                artifact_store=store,
                checkpointer=second,
            )
            replay = SpecialistResult.from_dict(
                (await run_specialist_task(graph=graph, task=task))["result"]
            )
            assert replay.to_dict() == result.to_dict()
            assert [name for name, _ in client.calls] == [
                RESEARCH_CREATE_EXPERIMENT_PROTOCOL_PROPOSAL_TOOL
            ]
            await second.adelete_thread(thread_id)

    anyio.run(_run)
