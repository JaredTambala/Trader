"""Response-loss and restart qualification for controlled orchestration."""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Mapping

import anyio
import psycopg
from psycopg import sql
from psycopg.rows import dict_row
import pytest

from trader.event_store import PostgresEventStore
from trader_agents import PersistentStdioMcpToolClient
from trader_mcp.constants import RESEARCH_VALIDATE_STRATEGY_IMPLEMENTATION_TOOL
from trader_research.governance import (
    EXPERIMENT_PROTOCOL_PROPOSAL,
    WORKFLOW_OUTCOME,
    WORKFLOW_PLAN,
    ExperimentProtocolProposal,
)
from trader_research.infrastructure.postgres import PostgresResearchArtifactStore
from tests.support.orchestration_qualification import (
    RECOVERY_COMPOSITION_ID,
    RecordingMcpToolClient,
    approve_qualification_proposal,
    clear_call_evidence,
    ensure_fixture_region,
    persist_call_evidence,
    prepare_qualification_request,
    run_resume_worker,
)
from tests.support.postgres_verification import (
    DEFAULT_CHECKPOINT_SCHEMA,
    ORCHESTRATION_VERIFICATION_PROFILE,
    REPO_ROOT,
    VERIFICATION_PROFILE_ENV,
    load_qualification_profile,
    load_test_settings,
    resolve_freeze_revision,
)
from tests.support.realistic_optimization_fixture import (
    build_realistic_optimization_fixture,
)


pytestmark = pytest.mark.postgres


def test_response_loss_reconciles_and_fresh_process_resume_does_not_replay(
    postgres_event_store: PostgresEventStore,
    postgres_research_artifact_store: PostgresResearchArtifactStore,
) -> None:
    """Lose one canonical response, retry identically, restart, and replay zero."""
    _require_orchestration_profile()
    clear_call_evidence(
        phase="ORCHESTRATION_RECOVERY",
        composition_id=RECOVERY_COMPOSITION_ID,
    )
    fixture = build_realistic_optimization_fixture()
    ensure_fixture_region(postgres_event_store, fixture.selection)

    async def _prepare() -> tuple[Mapping[str, Any], list[Any]]:
        client = PersistentStdioMcpToolClient(
            command=sys.executable,
            args=("-m", "tests.support.mcp_postgres_orchestration_server"),
            cwd=REPO_ROOT,
            env=dict(os.environ),
            read_timeout_seconds=300,
        )
        recording = RecordingMcpToolClient(client)
        async with client:
            request = await prepare_qualification_request(
                tool_client=recording,
                fixture=fixture,
                include_optimization=False,
                composition_id=RECOVERY_COMPOSITION_ID,
            )
        return request.to_dict(), recording.calls

    request_payload, setup_calls = anyio.run(_prepare)
    persist_call_evidence(
        phase="ORCHESTRATION_RECOVERY",
        composition_id=RECOVERY_COMPOSITION_ID,
        calls=setup_calls,
    )
    paused_stage = run_resume_worker(
        {
            "request": request_payload,
            "protocol": None,
            "phase": "ORCHESTRATION_RECOVERY",
            "setup": True,
            "reset": True,
        }
    )
    paused = _mapping(paused_stage["result"])
    assert paused["status"] == "awaiting_approval"
    proposal_ref = _mapping(paused["protocol_proposal_ref"])
    proposal = ExperimentProtocolProposal.from_dict(
        postgres_research_artifact_store.load_artifact(
            EXPERIMENT_PROTOCOL_PROPOSAL,
            str(proposal_ref["artifact_id"]),
        )
    )
    approved = approve_qualification_proposal(proposal)

    faulted_stage = run_resume_worker(
        {
            "request": request_payload,
            "protocol": approved.to_dict(),
            "phase": "ORCHESTRATION_RECOVERY",
            "setup": False,
            "max_workflow_tool_calls": 2,
            "lose_response_after_tool": (
                RESEARCH_VALIDATE_STRATEGY_IMPLEMENTATION_TOOL
            ),
        }
    )
    faulted = _mapping(faulted_stage["result"])
    assert faulted["status"] == "interrupted"

    completed_stage = run_resume_worker(
        {
            "request": request_payload,
            "protocol": approved.to_dict(),
            "phase": "ORCHESTRATION_RECOVERY",
            "setup": False,
        }
    )
    completed = _mapping(completed_stage["result"])
    assert completed["status"] == "completed"
    replayed = run_resume_worker(
        {
            "request": request_payload,
            "protocol": approved.to_dict(),
            "phase": "ORCHESTRATION_RECOVERY",
            "setup": False,
        }
    )
    assert replayed["result"] == completed
    assert replayed["calls"] == []
    workflow_id = str(completed["workflow_id"])
    assert _workflow_artifact_count(
        postgres_research_artifact_store,
        artifact_type=WORKFLOW_PLAN,
        workflow_id=workflow_id,
    ) == 1
    assert _workflow_artifact_count(
        postgres_research_artifact_store,
        artifact_type=WORKFLOW_OUTCOME,
        workflow_id=workflow_id,
    ) == 1
    _assert_identical_retry_evidence()
    _assert_checkpoint_payload_is_bounded()


def _workflow_artifact_count(
    artifact_store: PostgresResearchArtifactStore,
    *,
    artifact_type: str,
    workflow_id: str,
) -> int:
    """Count canonical artifacts attributed to one qualification workflow."""
    return sum(
        record.requested_by == workflow_id
        for record in artifact_store.list_artifacts(artifact_type=artifact_type)
    )


def _assert_identical_retry_evidence() -> None:
    settings = load_test_settings(required=True)
    assert settings is not None
    with psycopg.connect(settings.conninfo(), row_factory=dict_row) as connection:
        rows = connection.execute(
            "SELECT argument_digest, result_identity, retry_disposition "
            "FROM verification_control.orchestration_call_ledger "
            "WHERE qualification_profile = %s AND freeze_revision = %s "
            "AND phase = 'ORCHESTRATION_RECOVERY' AND composition_id = %s "
            "AND command = %s ORDER BY sequence",
            [
                ORCHESTRATION_VERIFICATION_PROFILE,
                resolve_freeze_revision(),
                RECOVERY_COMPOSITION_ID,
                RESEARCH_VALIDATE_STRATEGY_IMPLEMENTATION_TOOL,
            ],
        ).fetchall()
    lost = [row for row in rows if row["retry_disposition"] == "response_lost"]
    retried = [
        row for row in rows if row["retry_disposition"] == "identical_retry"
    ]
    assert len(lost) == 1
    assert len(retried) == 1
    assert lost[0]["argument_digest"] == retried[0]["argument_digest"]
    assert lost[0]["result_identity"] == retried[0]["result_identity"]


def _assert_checkpoint_payload_is_bounded() -> None:
    settings = load_test_settings(required=True)
    assert settings is not None
    schema_name = os.environ.get(
        "TRADER_CHECKPOINT_SCHEMA", DEFAULT_CHECKPOINT_SCHEMA
    )
    with psycopg.connect(settings.conninfo()) as connection:
        checkpoint_rows = connection.execute(
            sql.SQL("SELECT checkpoint::text, metadata::text FROM {}.checkpoints").format(
                sql.Identifier(schema_name)
            )
        ).fetchall()
        write_rows = connection.execute(
            sql.SQL("SELECT encode(blob, 'escape') FROM {}.checkpoint_writes").format(
                sql.Identifier(schema_name)
            )
        ).fetchall()
    serialized = json.dumps([checkpoint_rows, write_rows], default=str)
    assert "structuredContent" not in serialized
    assert "source_code" not in serialized
    assert "approval rationale" not in serialized.lower()
    assert "password" not in serialized.lower()


def _require_orchestration_profile() -> None:
    if load_qualification_profile().name != ORCHESTRATION_VERIFICATION_PROFILE:
        pytest.skip(
            f"set {VERIFICATION_PROFILE_ENV}={ORCHESTRATION_VERIFICATION_PROFILE}"
        )


def _mapping(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise AssertionError("expected a mapping")
    return value
