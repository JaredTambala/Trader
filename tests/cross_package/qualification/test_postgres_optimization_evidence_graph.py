"""Postgres-native optimization evidence graph through the public MCP process.

Subject: Complete data, implementation, backtest, optimization, evaluation, and adversarial evidence flow.
Level: Cross-package controlled qualification.
Collaborators: Core Postgres events, research artifacts, stdio MCP, and deterministic optimization services.
Guarantees: The public tool graph yields canonical projections, meaningful results, and no filesystem authority.
Non-goals: Provider-specific optimizers, model reasoning, live trading, or performance qualification.
"""

from __future__ import annotations

from datetime import timedelta
import json
from typing import Any, Mapping

import anyio
from mcp import ClientSession
from mcp.client.stdio import stdio_client
import pytest

from trader.event_store import PostgresEventStore
from trader_mcp.catalogue.definitions import REGISTERED_TOOL_NAMES
from trader_research.infrastructure.postgres import PostgresResearchArtifactStore
from tests.cross_package.qualification.optimization_evidence_graph_support import (
    _assert_no_filesystem_authority,
    _assert_postgres_graph,
    _run_graph,
    _server_parameters,
)
from tests.cross_package.qualification.support.postgres_verification import retain_verification_evidence
from tests.cross_package.qualification.support.realistic_optimization_fixture import (
    HOLDOUT_CONTENT_SHA256,
    SELECTION_CONTENT_SHA256,
    build_realistic_optimization_fixture,
    postgres_region_content_sha256,
    seed_fixture,
)


@pytest.mark.postgres
def test_postgres_native_stdio_mcp_optimization_evidence_graph(
    postgres_event_store: PostgresEventStore,
    postgres_research_artifact_store: PostgresResearchArtifactStore,
) -> None:
    """Prove the complete optimization evidence graph through a real stdio server."""
    fixture = build_realistic_optimization_fixture()
    seed_fixture(postgres_event_store, fixture)
    responses: list[Mapping[str, Any]] = []

    async def _run() -> Mapping[str, Any]:
        parameters = _server_parameters()
        async with stdio_client(parameters) as (read_stream, write_stream):
            async with ClientSession(
                read_stream,
                write_stream,
                read_timeout_seconds=timedelta(seconds=180),
            ) as session:
                await session.initialize()
                listed = await session.list_tools()
                assert {tool.name for tool in listed.tools} == set(
                    REGISTERED_TOOL_NAMES
                )
                return await _run_graph(
                    session, responses, postgres_research_artifact_store
                )

    evidence = anyio.run(_run)
    _assert_postgres_graph(postgres_research_artifact_store, evidence)
    _assert_no_filesystem_authority(responses, postgres_research_artifact_store)
    assert postgres_region_content_sha256(postgres_event_store, fixture.selection) == (
        SELECTION_CONTENT_SHA256
    )
    assert postgres_region_content_sha256(postgres_event_store, fixture.holdout) == (
        HOLDOUT_CONTENT_SHA256
    )
    if retain_verification_evidence():
        print("57M_EVIDENCE=" + json.dumps(evidence, sort_keys=True))
