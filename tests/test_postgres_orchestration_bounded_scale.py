"""Bounded task and three-symbol scale evidence for orchestration."""

from __future__ import annotations

from datetime import timedelta
import os
import sys
import time
from typing import Any, Mapping

import anyio
import psycopg
from psycopg.rows import dict_row
import pytest

from trader.event_store import PostgresEventStore
from trader_agents import (
    DataSpecialistRequest,
    PersistentStdioMcpToolClient,
    ResearchCompositionRequest,
    SpecialistTask,
    build_data_specialist_task,
)
from trader_research.governance import (
    EXPERIMENT_PROTOCOL_PROPOSAL,
    DataRequirement,
    ExperimentProtocolProposal,
    ResearchObjective,
    ResearchObjectiveStatus,
)
from trader_research.infrastructure.postgres import PostgresResearchArtifactStore
from tests.support.orchestration_qualification import (
    RecordingMcpToolClient,
    approve_qualification_proposal,
    clear_call_evidence,
    ensure_fixture_region,
    persist_call_evidence,
    persist_scale_result,
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
)
from tests.support.realistic_optimization_fixture import (
    ASSET_CLASS,
    FixtureRegion,
    SYMBOLS,
    TIMEFRAME,
    RealisticOptimizationFixture,
    build_bounded_scale_region,
    build_realistic_optimization_fixture,
)


pytestmark = pytest.mark.postgres
_TASK_LIMIT_COMPOSITION_ID = "controlled_orchestration_eight_tasks_v1"
_SCALE_PATH_COMPOSITION_ID = "controlled_orchestration_scale_path_v1"


def test_eight_real_tasks_and_three_symbol_baseline_scale(
    postgres_event_store: PostgresEventStore,
    postgres_research_artifact_store: PostgresResearchArtifactStore,
) -> None:
    """Exercise structural limits and record local scale measurements."""
    _require_orchestration_profile()
    clear_call_evidence(
        phase="ORCHESTRATION_SCALE",
        composition_id=_TASK_LIMIT_COMPOSITION_ID,
    )
    clear_call_evidence(
        phase="ORCHESTRATION_SCALE",
        composition_id=_SCALE_PATH_COMPOSITION_ID,
    )
    started = time.perf_counter()
    region = build_bounded_scale_region(bar_count=1_000)
    ensure_fixture_region(postgres_event_store, region)

    task_limit_request = _build_data_task_limit_request(region)
    with pytest.raises(ValueError, match="specialist task limit"):
        ResearchCompositionRequest(
            composition_id=_TASK_LIMIT_COMPOSITION_ID,
            objective=task_limit_request.objective,
            specialist_tasks=(
                *task_limit_request.specialist_tasks,
                _data_task(
                    objective=task_limit_request.objective,
                    composition_id=_TASK_LIMIT_COMPOSITION_ID,
                    requirement=_requirement_for_offsets(region, 0, 1),
                ),
            ),
            requested_by=task_limit_request.requested_by,
            actor=task_limit_request.actor,
        )
    task_result_stage = run_resume_worker(
        {
            "request": task_limit_request.to_dict(),
            "protocol": None,
            "phase": "ORCHESTRATION_SCALE",
            "setup": True,
            "reset": True,
        }
    )
    task_result = _mapping(task_result_stage["result"])
    assert task_result["status"] == "awaiting_prerequisite"
    assert len(task_result["accepted_specialist_results"]) == 8

    fixture = RealisticOptimizationFixture(
        selection=region,
        holdout=build_realistic_optimization_fixture().holdout,
    )

    async def _prepare_scale_path() -> tuple[Mapping[str, Any], list[Any]]:
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
                composition_id=_SCALE_PATH_COMPOSITION_ID,
            )
        return request.to_dict(), recording.calls

    scale_request, setup_calls = anyio.run(_prepare_scale_path)
    persist_call_evidence(
        phase="ORCHESTRATION_SCALE",
        composition_id=_SCALE_PATH_COMPOSITION_ID,
        calls=setup_calls,
    )
    paused_stage = run_resume_worker(
        {
            "request": scale_request,
            "protocol": None,
            "phase": "ORCHESTRATION_SCALE",
            "setup": False,
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
    completed_stage = run_resume_worker(
        {
            "request": scale_request,
            "protocol": approved.to_dict(),
            "phase": "ORCHESTRATION_SCALE",
            "setup": False,
        }
    )
    completed = _mapping(completed_stage["result"])
    assert completed["status"] == "completed"
    elapsed = time.perf_counter() - started
    measurements = _measurements()
    persist_scale_result(
        profile_name="eight_explicit_data_tasks",
        task_count=8,
        transition_count=int(task_result["transition_count"]),
        tool_call_count=_tool_call_count(_TASK_LIMIT_COMPOSITION_ID),
        wall_seconds=elapsed,
        payload={"ninth_task_rejected_before_mcp": True},
        **measurements,
    )
    persist_scale_result(
        profile_name="three_symbol_1000_bar_baseline",
        task_count=2,
        transition_count=int(completed["transition_count"]),
        tool_call_count=_tool_call_count(_SCALE_PATH_COMPOSITION_ID),
        wall_seconds=elapsed,
        payload={
            "symbols": len(SYMBOLS),
            "bars_per_symbol": 1_000,
            "outcome_ref": completed["outcome_ref"],
        },
        **measurements,
    )


def _build_data_task_limit_request(
    region: FixtureRegion,
) -> ResearchCompositionRequest:
    objective = ResearchObjective(
        objective_id="objective_controlled_orchestration_task_limit_v1",
        statement="Capture eight explicit bounded Data evidence slices.",
        success_criteria=("Return canonical manifest and quality refs.",),
        requested_by="operator:controlled_qualification",
        actor="operator:controlled_qualification",
        status=ResearchObjectiveStatus.APPROVED,
    )
    tasks = tuple(
        _data_task(
            objective=objective,
            composition_id=_TASK_LIMIT_COMPOSITION_ID,
            requirement=_requirement_for_offsets(
                region,
                index * 125,
                ((index + 1) * 125) - 1,
            ),
        )
        for index in range(8)
    )
    return ResearchCompositionRequest(
        composition_id=_TASK_LIMIT_COMPOSITION_ID,
        objective=objective,
        specialist_tasks=tasks,
        requested_by="operator:controlled_qualification",
        actor="research_coordinator",
    )


def _data_task(
    *,
    objective: ResearchObjective,
    composition_id: str,
    requirement: DataRequirement,
) -> SpecialistTask:
    return build_data_specialist_task(
        request=DataSpecialistRequest(data_requirement=requirement),
        objective=objective,
        requested_by=composition_id,
        actor="research_coordinator",
        permit_local_mutation=True,
    )


def _requirement_for_offsets(
    region: FixtureRegion,
    first: int,
    last: int,
) -> DataRequirement:
    return DataRequirement(
        symbols=SYMBOLS,
        asset_class=ASSET_CLASS,
        timeframe=TIMEFRAME,
        start=(region.start + timedelta(hours=first)).isoformat(),
        end=(region.start + timedelta(hours=last)).isoformat(),
    )


def _measurements() -> Mapping[str, int]:
    settings = load_test_settings(required=True)
    assert settings is not None
    checkpoint_schema = os.environ.get(
        "TRADER_CHECKPOINT_SCHEMA", DEFAULT_CHECKPOINT_SCHEMA
    )
    with psycopg.connect(settings.conninfo(), row_factory=dict_row) as connection:
        row = connection.execute(
            "SELECT pg_database_size(current_database()) AS database_bytes, "
            "(SELECT count(*) FROM research_artifacts) AS artifact_count, "
            "COALESCE((SELECT sum(pg_total_relation_size(format('%I.%I', "
            "schemaname, tablename)::regclass)) FROM pg_tables "
            "WHERE schemaname = %s), 0) AS checkpoint_bytes",
            [checkpoint_schema],
        ).fetchone()
    assert row is not None
    return {
        "checkpoint_bytes": int(row["checkpoint_bytes"]),
        "artifact_count": int(row["artifact_count"]),
        "database_bytes": int(row["database_bytes"]),
    }


def _tool_call_count(composition_id: str) -> int:
    settings = load_test_settings(required=True)
    assert settings is not None
    with psycopg.connect(settings.conninfo()) as connection:
        row = connection.execute(
            "SELECT count(*) FROM verification_control.orchestration_call_ledger "
            "WHERE qualification_profile = %s AND phase = 'ORCHESTRATION_SCALE' "
            "AND composition_id = %s",
            [ORCHESTRATION_VERIFICATION_PROFILE, composition_id],
        ).fetchone()
    return int(row[0]) if row is not None else 0


def _require_orchestration_profile() -> None:
    if load_qualification_profile().name != ORCHESTRATION_VERIFICATION_PROFILE:
        pytest.skip(
            f"set {VERIFICATION_PROFILE_ENV}={ORCHESTRATION_VERIFICATION_PROFILE}"
        )


def _mapping(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise AssertionError("expected a mapping")
    return value
