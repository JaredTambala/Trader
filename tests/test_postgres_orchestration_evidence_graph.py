"""Fresh-process Postgres evidence graph for controlled orchestration."""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Mapping

import anyio
import psycopg
from psycopg.rows import dict_row
import pytest

from trader.event_store import PostgresEventStore
from trader_agents import PersistentStdioMcpToolClient
from trader_research.foundation import json_payload_hash
from trader_research.governance import (
    EXPERIMENT_PROTOCOL,
    EXPERIMENT_PROTOCOL_PROPOSAL,
    WORKFLOW_OUTCOME,
    ExperimentProtocolProposal,
)
from trader_research.governance.artifacts import (
    PARAMETER_OPTIMIZATION_EVALUATION_REPORT,
    PARAMETER_OPTIMIZATION_ROBUSTNESS_REPORT,
    PARAMETER_OPTIMIZATION_TRIAL,
)
from trader_research.infrastructure.postgres import PostgresResearchArtifactStore
from tests.support.orchestration_qualification import (
    QUALIFICATION_COMPOSITION_ID,
    RecordingMcpToolClient,
    approve_qualification_proposal,
    clear_call_evidence,
    ensure_fixture_region,
    persist_call_evidence,
    prepare_qualification_request,
    run_resume_worker,
)
from tests.support.postgres_verification import (
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


def test_fresh_process_data_design_and_fixed_workflow_evidence_graph(
    postgres_event_store: PostgresEventStore,
    postgres_research_artifact_store: PostgresResearchArtifactStore,
) -> None:
    """Run Data, design, approval, interruption, resume, and terminal replay."""
    _require_orchestration_profile()
    clear_call_evidence(
        phase="ORCHESTRATION_E2E",
        composition_id=QUALIFICATION_COMPOSITION_ID,
    )
    fixture = build_realistic_optimization_fixture()
    ensure_fixture_region(postgres_event_store, fixture.selection)
    ensure_fixture_region(postgres_event_store, fixture.holdout)
    server_env = dict(os.environ)

    async def _prepare() -> tuple[Mapping[str, Any], list[Any]]:
        client = PersistentStdioMcpToolClient(
            command=sys.executable,
            args=("-m", "tests.support.mcp_postgres_orchestration_server"),
            cwd=REPO_ROOT,
            env=server_env,
            read_timeout_seconds=300,
        )
        recording = RecordingMcpToolClient(client)
        async with client:
            request = await prepare_qualification_request(
                tool_client=recording,
                fixture=fixture,
            )
        return request.to_dict(), recording.calls

    request_payload, setup_calls = anyio.run(_prepare)
    persist_call_evidence(
        phase="ORCHESTRATION_E2E",
        composition_id=QUALIFICATION_COMPOSITION_ID,
        calls=setup_calls,
    )
    awaiting_approval = run_resume_worker(
        {
            "request": request_payload,
            "protocol": None,
            "phase": "ORCHESTRATION_E2E",
            "setup": True,
            "reset": True,
        }
    )
    paused = _mapping(awaiting_approval["result"])
    assert paused["status"] == "awaiting_approval"
    assert len(paused["accepted_specialist_results"]) == 3
    proposal_ref = _mapping(paused["protocol_proposal_ref"])
    assert proposal_ref["artifact_type"] == EXPERIMENT_PROTOCOL_PROPOSAL
    proposal = ExperimentProtocolProposal.from_dict(
        postgres_research_artifact_store.load_artifact(
            EXPERIMENT_PROTOCOL_PROPOSAL,
            str(proposal_ref["artifact_id"]),
        )
    )
    proposal_digest = json_payload_hash(proposal.to_dict())
    approved = approve_qualification_proposal(proposal)

    interrupted_stage = run_resume_worker(
        {
            "request": request_payload,
            "protocol": approved.to_dict(),
            "phase": "ORCHESTRATION_E2E",
            "setup": False,
            "max_workflow_tool_calls": 5,
        }
    )
    interrupted = _mapping(interrupted_stage["result"])
    assert interrupted["status"] == "interrupted"
    assert interrupted["workflow_id"]

    completed_stage = run_resume_worker(
        {
            "request": request_payload,
            "protocol": approved.to_dict(),
            "phase": "ORCHESTRATION_E2E",
            "setup": False,
        }
    )
    completed = _mapping(completed_stage["result"])
    assert completed["status"] == "completed"
    outcome_ref = _mapping(completed["outcome_ref"])
    assert outcome_ref["artifact_type"] == WORKFLOW_OUTCOME

    replayed = run_resume_worker(
        {
            "request": request_payload,
            "protocol": approved.to_dict(),
            "phase": "ORCHESTRATION_E2E",
            "setup": False,
        }
    )
    assert replayed["result"] == completed
    assert replayed["calls"] == []

    persisted_proposal = postgres_research_artifact_store.load_artifact(
        EXPERIMENT_PROTOCOL_PROPOSAL,
        proposal.proposal_id,
    )
    assert json_payload_hash(persisted_proposal) == proposal_digest
    assert persisted_proposal["status"] == "proposed"
    persisted_protocol = postgres_research_artifact_store.load_artifact(
        EXPERIMENT_PROTOCOL,
        approved.protocol_id,
    )
    assert persisted_protocol["status"] == "approved"
    assert persisted_protocol["proposed_by"] == proposal.proposed_by
    assert all(
        approval["decided_by"] != proposal.proposed_by
        for approval in persisted_protocol["approvals"]
    )
    assert len(
        postgres_research_artifact_store.list_artifacts(
            artifact_type=PARAMETER_OPTIMIZATION_TRIAL
        )
    ) >= 4
    settings = load_test_settings(required=True)
    assert settings is not None
    with psycopg.connect(settings.conninfo()) as connection:
        trial_counts = connection.execute(
            "SELECT count(*) FROM research_parameter_optimization_trials "
            "GROUP BY optimization_run_id"
        ).fetchall()
    assert 4 in {int(row[0]) for row in trial_counts}
    assert postgres_research_artifact_store.list_artifacts(
        artifact_type=PARAMETER_OPTIMIZATION_EVALUATION_REPORT
    )
    assert postgres_research_artifact_store.list_artifacts(
        artifact_type=PARAMETER_OPTIMIZATION_ROBUSTNESS_REPORT
    )
    postgres_research_artifact_store.load_artifact(
        WORKFLOW_OUTCOME,
        str(outcome_ref["artifact_id"]),
    )
    _assert_call_ledger()


def _assert_call_ledger() -> None:
    settings = load_test_settings(required=True)
    assert settings is not None
    freeze_revision = resolve_freeze_revision()
    with psycopg.connect(settings.conninfo(), row_factory=dict_row) as connection:
        rows = connection.execute(
            "SELECT sequence, command, argument_digest, result_identity, "
            "retry_disposition FROM verification_control.orchestration_call_ledger "
            "WHERE qualification_profile = %s AND freeze_revision = %s "
            "AND phase = 'ORCHESTRATION_E2E' AND composition_id = %s "
            "ORDER BY sequence",
            [
                ORCHESTRATION_VERIFICATION_PROFILE,
                freeze_revision,
                QUALIFICATION_COMPOSITION_ID,
            ],
        ).fetchall()
    assert rows
    assert [row["sequence"] for row in rows] == list(range(1, len(rows) + 1))
    assert all(len(row["argument_digest"]) == 64 for row in rows)
    serialized = json.dumps(rows, default=str, sort_keys=True)
    assert "source_code" not in serialized
    assert "structuredContent" not in serialized
    assert "credential" not in serialized.lower()


def _require_orchestration_profile() -> None:
    if load_qualification_profile().name != ORCHESTRATION_VERIFICATION_PROFILE:
        pytest.skip(
            f"set {VERIFICATION_PROFILE_ENV}={ORCHESTRATION_VERIFICATION_PROFILE}"
        )


def _mapping(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise AssertionError("expected a mapping")
    return value
