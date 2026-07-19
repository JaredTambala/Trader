"""Controlled Postgres determinism, integrity, and holdout-leakage evidence for 57N."""

from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from datetime import timedelta
import json
import random
from typing import Any, Callable, Iterator, Mapping

import anyio
from mcp import ClientSession
from mcp.client.stdio import stdio_client
from psycopg.types.json import Jsonb
import pytest

from trader.event_store import PostgresEventStore
from trader_mcp.constants import (
    EVALUATION_GENERATE_PARAMETER_OPTIMIZATION_REPORT_TOOL,
    RESEARCH_CREATE_PARAMETER_OPTIMIZATION_PLAN_TOOL,
    RESEARCH_GET_PARAMETER_OPTIMIZATION_RESULTS_TOOL,
    RESEARCH_RUN_BACKTEST_SPECIFICATION_TOOL,
    RESEARCH_RUN_PARAMETER_OPTIMIZATION_TOOL,
)
from trader_research.governance.artifacts import (
    BACKTEST_SPECIFICATION,
    BACKTEST_RUN,
    IMPLEMENTATION_VALIDATION_REPORT,
    IMPLEMENTATION_VERSION,
    PARAMETER_OPTIMIZATION_PLAN,
    PARAMETER_OPTIMIZATION_RUN,
    PARAMETER_OPTIMIZATION_TRIAL,
    STRATEGY_SPECIFICATION,
)
from trader_research.infrastructure.postgres import PostgresResearchArtifactStore
from tests.support.postgres_57n import (
    access_audit_summary,
    clear_57n_control_evidence,
    ensure_57n_control_schema,
    graph_snapshot,
    reset_57n_product_state,
    save_graph_snapshot,
    save_integrity_check,
    seal_selection,
)
from tests.support.realistic_optimization_fixture import (
    HOLDOUT_CONTENT_SHA256,
    SEARCH_LOOKBACKS,
    SEED,
    SELECTION_CONTENT_SHA256,
    build_realistic_optimization_fixture,
    postgres_region_content_sha256,
    seed_fixture,
)
from tests.test_postgres_optimization_evidence_graph import (
    _assert_meaningful_backtest,
    _assert_postgres_graph,
    _call,
    _create_behavior_specifications,
    _create_validated_backtest,
    _mcp_data_evidence,
    _register_objective,
    _register_risk,
    _register_strategy,
    _run_graph,
    _server_parameters,
    _value,
)


@pytest.mark.postgres
def test_postgres_57n_determinism_integrity_and_holdout_access(
    postgres_settings: dict[str, object],
    postgres_event_store: PostgresEventStore,
    postgres_research_artifact_store: PostgresResearchArtifactStore,
) -> None:
    control = postgres_research_artifact_store.connection()
    ensure_57n_control_schema(control)
    clear_57n_control_evidence(control)

    first = _execute_complete_graph(
        postgres_event_store,
        postgres_research_artifact_store,
        postgres_settings,
    )
    save_graph_snapshot(control, execution_label="clean_a", snapshot=first)
    _assert_fail_closed_tamper_matrix(postgres_research_artifact_store, first)

    reset_57n_product_state(
        postgres_event_store, postgres_research_artifact_store, postgres_settings
    )
    leakage = _execute_staged_holdout_access_graph(
        postgres_event_store,
        postgres_research_artifact_store,
    )

    reset_57n_product_state(
        postgres_event_store, postgres_research_artifact_store, postgres_settings
    )
    second = _execute_complete_graph(
        postgres_event_store,
        postgres_research_artifact_store,
        postgres_settings,
    )
    save_graph_snapshot(control, execution_label="clean_b", snapshot=second)

    assert first["graph_digest"] == second["graph_digest"]
    assert first["root_refs"] == second["root_refs"]
    assert [
        (item["artifact_type"], item["artifact_id"], item["payload_sha256"])
        for item in first["artifacts"]
    ] == [
        (item["artifact_type"], item["artifact_id"], item["payload_sha256"])
        for item in second["artifacts"]
    ]
    fixture = build_realistic_optimization_fixture()
    assert postgres_region_content_sha256(postgres_event_store, fixture.selection) == (
        SELECTION_CONTENT_SHA256
    )
    assert postgres_region_content_sha256(postgres_event_store, fixture.holdout) == (
        HOLDOUT_CONTENT_SHA256
    )
    print(
        "57N_EVIDENCE="
        + json.dumps(
            {
                "artifact_count": len(second["artifacts"]),
                "graph_digest": second["graph_digest"],
                "root_refs": second["root_refs"],
                "holdout_access": leakage,
            },
            sort_keys=True,
        )
    )


def _execute_complete_graph(
    event_store: PostgresEventStore,
    artifact_store: PostgresResearchArtifactStore,
    settings: Mapping[str, object],
) -> Mapping[str, Any]:
    reset_57n_product_state(event_store, artifact_store, settings)
    seed_fixture(event_store, build_realistic_optimization_fixture())
    responses: list[Mapping[str, Any]] = []

    async def _run() -> Mapping[str, Any]:
        async with stdio_client(_server_parameters()) as (read_stream, write_stream):
            async with ClientSession(
                read_stream,
                write_stream,
                read_timeout_seconds=timedelta(seconds=180),
            ) as session:
                await session.initialize()
                evidence = dict(await _run_graph(session, responses, artifact_store))
                _assert_postgres_graph(artifact_store, evidence)
                plan_id = str(evidence["optimization_plan_uri"]).rsplit("/", 1)[-1]
                random_run = _value(
                    await _call(
                        session,
                        RESEARCH_RUN_PARAMETER_OPTIMIZATION_TOOL,
                        {
                            "optimization_plan_ref": plan_id,
                            "optimizer_profile": "builtin_random",
                        },
                        responses,
                    ),
                    "parameter_optimization_run",
                )
                random_results = await _call(
                    session,
                    RESEARCH_GET_PARAMETER_OPTIMIZATION_RESULTS_TOOL,
                    {"optimization_run_ref": random_run["optimization_run_id"]},
                    responses,
                )
                trials = list(random_results["data"]["trials"])
                expected = list(SEARCH_LOOKBACKS)
                random.Random(SEED).shuffle(expected)
                assert [
                    trial["parameters"]["/strategy/parameters/lookback_bars"]
                    for trial in trials
                ] == expected
                assert all(trial["status"] == "passed" for trial in trials)
                evidence["random_optimization_run_uri"] = (
                    f"research://postgres/{PARAMETER_OPTIMIZATION_RUN}/"
                    f"{random_run['optimization_run_id']}"
                )
                return evidence

    evidence = anyio.run(_run)
    return graph_snapshot(artifact_store, evidence)


def _assert_fail_closed_tamper_matrix(
    store: PostgresResearchArtifactStore,
    snapshot: Mapping[str, Any],
) -> None:
    roots = snapshot["root_refs"]
    run_id = str(roots["optimization_run_uri"]).rsplit("/", 1)[-1]
    trial_id = str(roots["selected_trial_uri"]).rsplit("/", 1)[-1]
    plan_id = str(roots["optimization_plan_uri"]).rsplit("/", 1)[-1]
    holdout_id = str(roots["holdout_backtest_uri"]).rsplit("/", 1)[-1]
    plan = store.load_artifact(PARAMETER_OPTIMIZATION_PLAN, plan_id)
    base_id = str(plan["base_backtest_specification_id"])
    base = store.load_artifact(BACKTEST_SPECIFICATION, base_id)
    objective_id = str(plan["objective_implementation_version_id"])
    objective_validation_id = str(plan["objective_validation_id"])
    strategy_id = str(base["strategy_specification_id"])
    cases = (
        (
            "objective_source_hash",
            IMPLEMENTATION_VERSION,
            objective_id,
            RESEARCH_RUN_PARAMETER_OPTIMIZATION_TOOL,
            {"optimization_plan_ref": plan_id, "optimizer_profile": "builtin_grid"},
            lambda payload: payload.__setitem__("source_hash", "tampered"),
            "parameter_optimization_run_failed",
        ),
        (
            "objective_validation",
            IMPLEMENTATION_VALIDATION_REPORT,
            objective_validation_id,
            RESEARCH_RUN_PARAMETER_OPTIMIZATION_TOOL,
            {"optimization_plan_ref": plan_id, "optimizer_profile": "builtin_grid"},
            lambda payload: payload.__setitem__("valid", False),
            "parameter_optimization_run_failed",
        ),
        (
            "strategy_parameters",
            STRATEGY_SPECIFICATION,
            strategy_id,
            RESEARCH_RUN_PARAMETER_OPTIMIZATION_TOOL,
            {"optimization_plan_ref": plan_id, "optimizer_profile": "builtin_grid"},
            lambda payload: payload["parameters"].__setitem__(
                "entry_threshold_bps",
                float(payload["parameters"]["entry_threshold_bps"]) + 1.0,
            ),
            "parameter_optimization_run_failed",
        ),
        (
            "selection_dataset_snapshot",
            BACKTEST_SPECIFICATION,
            base_id,
            RESEARCH_RUN_PARAMETER_OPTIMIZATION_TOOL,
            {"optimization_plan_ref": plan_id, "optimizer_profile": "builtin_grid"},
            lambda payload: payload["dataset"]["payload"].__setitem__(
                "total_rows", int(payload["dataset"]["payload"]["total_rows"]) + 1
            ),
            "parameter_optimization_run_failed",
        ),
        (
            "selection_quality_snapshot",
            BACKTEST_SPECIFICATION,
            base_id,
            RESEARCH_RUN_PARAMETER_OPTIMIZATION_TOOL,
            {"optimization_plan_ref": plan_id, "optimizer_profile": "builtin_grid"},
            lambda payload: payload["data_quality"]["payload"].__setitem__(
                "total_bars", int(payload["data_quality"]["payload"]["total_bars"]) + 1
            ),
            "parameter_optimization_run_failed",
        ),
        (
            "fixed_transaction_costs",
            BACKTEST_SPECIFICATION,
            base_id,
            RESEARCH_RUN_PARAMETER_OPTIMIZATION_TOOL,
            {"optimization_plan_ref": plan_id, "optimizer_profile": "builtin_grid"},
            lambda payload: payload["assumptions"]["fees"].__setitem__(
                "bps", float(payload["assumptions"]["fees"]["bps"]) + 1.0
            ),
            "parameter_optimization_run_failed",
        ),
        (
            "run_selected_trial",
            PARAMETER_OPTIMIZATION_RUN,
            run_id,
            RESEARCH_GET_PARAMETER_OPTIMIZATION_RESULTS_TOOL,
            {"optimization_run_ref": run_id},
            lambda payload: payload.__setitem__(
                "selected_trial_id", "parameter_optimization_trial_tampered"
            ),
            "parameter_optimization_lookup_failed",
        ),
        (
            "run_engine_profile",
            PARAMETER_OPTIMIZATION_RUN,
            run_id,
            RESEARCH_GET_PARAMETER_OPTIMIZATION_RESULTS_TOOL,
            {"optimization_run_ref": run_id},
            lambda payload: payload["engine_profile"].__setitem__(
                "configuration_digest", "tampered"
            ),
            "parameter_optimization_lookup_failed",
        ),
        (
            "run_selected_child",
            PARAMETER_OPTIMIZATION_RUN,
            run_id,
            RESEARCH_GET_PARAMETER_OPTIMIZATION_RESULTS_TOOL,
            {"optimization_run_ref": run_id},
            lambda payload: payload["selected_child_refs"].__setitem__(
                "strategy_specification_id", "strategy_specification_tampered"
            ),
            "parameter_optimization_lookup_failed",
        ),
        (
            "trial_objective",
            PARAMETER_OPTIMIZATION_TRIAL,
            trial_id,
            RESEARCH_GET_PARAMETER_OPTIMIZATION_RESULTS_TOOL,
            {"optimization_run_ref": run_id},
            lambda payload: payload.__setitem__(
                "objective_value", float(payload["objective_value"]) + 1.0
            ),
            "parameter_optimization_lookup_failed",
        ),
        (
            "trial_sequence",
            PARAMETER_OPTIMIZATION_TRIAL,
            trial_id,
            RESEARCH_GET_PARAMETER_OPTIMIZATION_RESULTS_TOOL,
            {"optimization_run_ref": run_id},
            lambda payload: payload.__setitem__("sequence", 99),
            "parameter_optimization_lookup_failed",
        ),
        (
            "trial_child_lineage",
            PARAMETER_OPTIMIZATION_TRIAL,
            trial_id,
            RESEARCH_GET_PARAMETER_OPTIMIZATION_RESULTS_TOOL,
            {"optimization_run_ref": run_id},
            lambda payload: payload["child_refs"].__setitem__(
                "backtest_run_id", "backtest_run_tampered"
            ),
            "parameter_optimization_lookup_failed",
        ),
        (
            "plan_seed",
            PARAMETER_OPTIMIZATION_PLAN,
            plan_id,
            RESEARCH_RUN_PARAMETER_OPTIMIZATION_TOOL,
            {"optimization_plan_ref": plan_id, "optimizer_profile": "builtin_grid"},
            lambda payload: payload.__setitem__("seed", int(payload["seed"]) + 1),
            "parameter_optimization_run_failed",
        ),
        (
            "holdout_selection_origin",
            BACKTEST_RUN,
            holdout_id,
            EVALUATION_GENERATE_PARAMETER_OPTIMIZATION_REPORT_TOOL,
            {"optimization_run_ref": run_id, "holdout_backtest_run_ref": holdout_id},
            lambda payload: payload.__setitem__(
                "selection_origin_ref", "parameter_optimization_run_tampered"
            ),
            "parameter_optimization_evaluation_blocked",
        ),
    )

    async def _run() -> None:
        async with stdio_client(_server_parameters()) as (read_stream, write_stream):
            async with ClientSession(
                read_stream,
                write_stream,
                read_timeout_seconds=timedelta(seconds=180),
            ) as session:
                await session.initialize()
                for (
                    name,
                    artifact_type,
                    artifact_id,
                    tool_name,
                    arguments,
                    mutate,
                    expected_code,
                ) in cases:
                    with _tampered_payload(store, artifact_type, artifact_id, mutate):
                        result = await session.call_tool(tool_name, arguments)
                        payload = result.structuredContent
                        assert payload is not None
                        assert payload["ok"] is False
                        assert result.isError is True
                        assert payload["errors"][0]["code"] == expected_code
                        save_integrity_check(
                            store.connection(),
                            check_name=name,
                            target_artifact_type=artifact_type,
                            target_artifact_id=artifact_id,
                            consumer_tool=tool_name,
                            error_code=expected_code,
                            error_message=payload["errors"][0]["message"],
                        )

    anyio.run(_run)


@contextmanager
def _tampered_payload(
    store: PostgresResearchArtifactStore,
    artifact_type: str,
    artifact_id: str,
    mutate: Callable[[dict[str, Any]], None],
) -> Iterator[None]:
    connection = store.connection()
    row = connection.execute(
        "SELECT payload FROM research_artifacts WHERE artifact_type = %s AND artifact_id = %s",
        [artifact_type, artifact_id],
    ).fetchone()
    assert row is not None
    original = dict(row["payload"])
    changed = deepcopy(original)
    mutate(changed)
    connection.execute(
        "UPDATE research_artifacts SET payload = %s WHERE artifact_type = %s AND artifact_id = %s",
        [Jsonb(changed), artifact_type, artifact_id],
    )
    try:
        yield
    finally:
        connection.execute(
            "UPDATE research_artifacts SET payload = %s WHERE artifact_type = %s AND artifact_id = %s",
            [Jsonb(original), artifact_type, artifact_id],
        )


def _execute_staged_holdout_access_graph(
    event_store: PostgresEventStore,
    store: PostgresResearchArtifactStore,
) -> Mapping[str, Any]:
    fixture = build_realistic_optimization_fixture()
    seed_fixture(event_store, fixture)
    responses: list[Mapping[str, Any]] = []

    async def _setup() -> Mapping[str, Any]:
        async with stdio_client(_server_parameters(access_stage="plan_setup")) as streams:
            async with ClientSession(
                *streams, read_timeout_seconds=timedelta(seconds=180)
            ) as session:
                await session.initialize()
                selection_manifest, selection_quality = await _mcp_data_evidence(
                    session,
                    fixture.selection.start.isoformat(),
                    fixture.selection.end.isoformat(),
                    responses,
                )
                holdout_manifest, holdout_quality = await _mcp_data_evidence(
                    session,
                    fixture.holdout.start.isoformat(),
                    fixture.holdout.end.isoformat(),
                    responses,
                )
                strategy_validation, _ = await _register_strategy(session, responses)
                risk_validation, _ = await _register_risk(session, responses)
                objective_validation, _ = await _register_objective(session, responses)
                configured = await _create_behavior_specifications(
                    session,
                    strategy_validation_id=strategy_validation["validation_id"],
                    risk_validation_id=risk_validation["validation_id"],
                    responses=responses,
                )
                selection_validation = await _create_validated_backtest(
                    session,
                    strategy_validation_id=configured["strategy_validation_id"],
                    risk_validation_id=configured["risk_validation_id"],
                    manifest=selection_manifest,
                    quality=selection_quality,
                    responses=responses,
                )
                plan = _value(
                    await _call(
                        session,
                        RESEARCH_CREATE_PARAMETER_OPTIMIZATION_PLAN_TOOL,
                        {
                            "base_backtest_specification_validation_ref": selection_validation[
                                "validation_id"
                            ],
                            "holdout_dataset_manifest": holdout_manifest,
                            "holdout_data_quality_report": holdout_quality,
                            "objective_validation_ref": objective_validation["validation_id"],
                            "search_space": [
                                {
                                    "path": "/strategy/parameters/lookback_bars",
                                    "type": "integer",
                                    "low": min(SEARCH_LOOKBACKS),
                                    "high": max(SEARCH_LOOKBACKS),
                                }
                            ],
                            "direction": "maximize",
                            "seed": SEED,
                            "max_trials": len(SEARCH_LOOKBACKS),
                            "resource_limits": {
                                "max_trial_attempts": 1,
                                "max_concurrent_trials": 1,
                            },
                        },
                        responses,
                    ),
                    "parameter_optimization_plan",
                )
                return {
                    "plan": plan,
                    "holdout_manifest": holdout_manifest,
                    "holdout_quality": holdout_quality,
                }

    setup = anyio.run(_setup)

    async def _optimize() -> Mapping[str, Any]:
        async with stdio_client(
            _server_parameters(access_stage="selection_optimization")
        ) as streams:
            async with ClientSession(
                *streams, read_timeout_seconds=timedelta(seconds=180)
            ) as session:
                await session.initialize()
                run = _value(
                    await _call(
                        session,
                        RESEARCH_RUN_PARAMETER_OPTIMIZATION_TOOL,
                        {
                            "optimization_plan_ref": setup["plan"]["optimization_plan_id"],
                            "optimizer_profile": "builtin_grid",
                        },
                        responses,
                    ),
                    "parameter_optimization_run",
                )
                await _call(
                    session,
                    RESEARCH_GET_PARAMETER_OPTIMIZATION_RESULTS_TOOL,
                    {"optimization_run_ref": run["optimization_run_id"]},
                    responses,
                )
                return run

    optimization = anyio.run(_optimize)
    holdout_hash = setup["plan"]["holdout_dataset"]["sha256"]
    selection_hash = setup["plan"]["selection_dataset_hash"]
    assert (
        store.connection()
        .execute(
            """
            SELECT count(*) AS run_count
            FROM research_backtest_runs
            WHERE payload ->> 'dataset_hash' = %s
            """,
            [holdout_hash],
        )
        .fetchone()["run_count"]
        == 0
    )
    trials = [
        record.payload
        for record in store.list_artifacts(artifact_type=PARAMETER_OPTIMIZATION_TRIAL)
        if record.payload.get("optimization_run_id") == optimization["optimization_run_id"]
    ]
    assert trials
    for trial in trials:
        assert trial["observation"]["lineage"]["fold"] == "selection"
        child = store.load_artifact(BACKTEST_RUN, trial["child_refs"]["backtest_run_id"])
        assert child["dataset_hash"] == selection_hash
    seal_selection(store.connection(), optimization)

    async def _holdout() -> Mapping[str, Any]:
        async with stdio_client(
            _server_parameters(access_stage="holdout_evaluation")
        ) as streams:
            async with ClientSession(
                *streams, read_timeout_seconds=timedelta(seconds=180)
            ) as session:
                await session.initialize()
                validation = await _create_validated_backtest(
                    session,
                    strategy_validation_id=optimization["selected_child_refs"][
                        "strategy_specification_validation_id"
                    ],
                    risk_validation_id=optimization["selected_child_refs"][
                        "risk_stack_specification_validation_id"
                    ],
                    manifest=setup["holdout_manifest"],
                    quality=setup["holdout_quality"],
                    selection_origin_ref=optimization["optimization_run_id"],
                    responses=responses,
                )
                holdout = _value(
                    await _call(
                        session,
                        RESEARCH_RUN_BACKTEST_SPECIFICATION_TOOL,
                        {
                            "backtest_specification_validation_ref": validation[
                                "validation_id"
                            ]
                        },
                        responses,
                    ),
                    "backtest_run",
                )
                _assert_meaningful_backtest(holdout)
                evaluation = _value(
                    await _call(
                        session,
                        EVALUATION_GENERATE_PARAMETER_OPTIMIZATION_REPORT_TOOL,
                        {
                            "optimization_run_ref": optimization["optimization_run_id"],
                            "holdout_backtest_run_ref": holdout["run_id"],
                        },
                        responses,
                    ),
                    "parameter_optimization_evaluation_report",
                )
                assert evaluation["status"] == "passed"
                return holdout

    holdout = anyio.run(_holdout)
    assert holdout["dataset_hash"] == holdout_hash
    connection = store.connection()
    selection_access = connection.execute(
        """
        SELECT max(maximum_parameter_ts) AS maximum_parameter_ts
        FROM verification_control.data_access_log
        WHERE phase = '57N' AND stage = 'selection_optimization'
        """
    ).fetchone()["maximum_parameter_ts"]
    assert selection_access is not None
    assert selection_access <= fixture.selection.end
    assert selection_access < fixture.holdout.start
    premature = connection.execute(
        """
        SELECT count(*) AS premature_count
        FROM verification_control.data_access_log AS access
        JOIN verification_control.selection_seals AS seal ON seal.phase = access.phase
        WHERE access.phase = '57N'
          AND access.stage = 'holdout_evaluation'
          AND access.recorded_at <= seal.sealed_at
        """
    ).fetchone()["premature_count"]
    assert premature == 0
    summary = access_audit_summary(connection)
    assert {row["stage"] for row in summary["stages"]} == {
        "holdout_evaluation",
        "plan_setup",
        "selection_optimization",
    }
    return summary
