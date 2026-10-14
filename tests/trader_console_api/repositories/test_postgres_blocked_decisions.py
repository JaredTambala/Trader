"""Blocked-decision canonical validation and durable append-only persistence.

Subject: Console canonical blocked-evidence adapter and research projection recovery.
Level: PostgreSQL integration with a fresh-process read.
Collaborators: Real Psycopg connections, a uniquely owned schema, research store,
Console command repository and producer-shaped canonical artifacts.
Guarantees: Exact blockers, human attribution and pinned input chains survive a
process restart; drift fails closed and duplicate domain submissions are stable.
Non-goals: Run publication views, authentication middleware, UI and scientific review.
"""
from __future__ import annotations

import asyncio
from dataclasses import replace
import json
import os
import subprocess
import sys
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
from psycopg.types.json import Jsonb
import pytest

from tests.trader_research.governance.support.blocked_decisions import blocked_fixture
from trader_console_api.repositories.next_research_decisions import (
    NextResearchDecisionEvidenceUnavailable, NextResearchDecisionSession,
)
from trader_research.governance import create_next_research_decision
from trader_research.infrastructure.postgres import PostgresResearchArtifactStore

pytestmark = pytest.mark.postgres


@pytest.fixture
def isolated_blocked_store(postgres_settings):
    """Install and seed only a unique schema inside the guarded test database."""
    schema = f"blocked_decision_{uuid4().hex}"
    with psycopg.connect(**postgres_settings, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    dsn = make_conninfo(**postgres_settings, options=f"-csearch_path={schema}")
    store = PostgresResearchArtifactStore(dsn=dsn)
    memory, decision, _ = blocked_fixture()
    try:
        for record in memory.list_artifacts():
            store.connection().execute(
                "INSERT INTO research_artifacts (artifact_type,artifact_id,domain_owner,producer_tool,status,schema_version,metadata,payload) "
                "VALUES (%s,%s,%s,%s,%s,'1',%s,%s)",
                (record.artifact_type, record.artifact_id, record.domain_owner, record.producer_tool,
                 record.status, Jsonb(dict(record.metadata)), Jsonb(dict(record.payload))),
            )
        yield store, decision, dsn
    finally:
        store.close()
        with psycopg.connect(**postgres_settings, autocommit=True) as connection:
            connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def test_blocked_human_decision_is_idempotent_and_reopens_in_fresh_process(isolated_blocked_store):
    """A fresh process resolves the same immutable unassessed blocker basis."""
    store, decision, dsn = isolated_blocked_store
    for _ in range(2):
        result = create_next_research_decision(decision.to_dict(), artifact_store=store, requested_by="human:jared", actor="human:jared")
        assert result.ok, result.errors
    assert len(store.list_artifacts(artifact_type="research_next_decision")) == 1
    reader = '''import json, os
from trader_research.governance import get_next_research_decision
from trader_research.infrastructure.postgres import PostgresResearchArtifactStore
store=PostgresResearchArtifactStore(dsn=os.environ["BLOCKED_DECISION_TEST_DSN"], ensure_schema=False)
try:
    result=get_next_research_decision(os.environ["BLOCKED_DECISION_ARTIFACT"], artifact_store=store)
    assert result.ok, result.errors
    print(json.dumps(result.data["research_next_decision"]))
finally:
    store.close()
'''
    completed = subprocess.run([sys.executable, "-c", reader], env={**os.environ, "PYTHONPATH": "src", "BLOCKED_DECISION_TEST_DSN": dsn, "BLOCKED_DECISION_ARTIFACT": decision.artifact_id}, capture_output=True, text=True, check=True)
    assert json.loads(completed.stdout) == decision.to_dict()


def test_console_blocked_adapter_persists_and_rejects_changed_blockers(isolated_blocked_store):
    """Real Console SQL pins the same blockers before an atomic artifact write."""
    _, decision, dsn = isolated_blocked_store

    async def exercise():
        async with await psycopg.AsyncConnection.connect(dsn) as connection:
            session = NextResearchDecisionSession(connection, "isolated-test")
            await session._validate_blocked_evidence(decision)
            stored = await session.create(decision, requested_by="human:jared")
            assert stored.to_dict() == decision.to_dict()
        async with await psycopg.AsyncConnection.connect(dsn) as connection:
            session = NextResearchDecisionSession(connection, "isolated-test")
            recovered = await session.get("run-1", decision.decision_id, 1)
            assert recovered.to_dict() == decision.to_dict()
            changed = replace(decision, blocked_evidence=replace(decision.blocked_evidence, blockers=(replace(decision.blocked_evidence.blockers[0], details={"role": "fabricated"}),)))
            with pytest.raises(NextResearchDecisionEvidenceUnavailable, match="blockers differ"):
                await session._validate_blocked_evidence(changed)
    asyncio.run(exercise())
