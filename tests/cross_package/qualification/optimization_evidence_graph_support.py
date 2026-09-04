"""Shared construction and assertion helpers for the optimization evidence graph.

These helpers keep the large multi-package workflow legible without creating a
second collected test module. They preserve the original tool sequence,
canonical-artifact assertions, and subprocess boundary used by both the primary
evidence-graph qualification and the determinism/integrity qualification.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

from mcp import ClientSession, StdioServerParameters

from trader_mcp.catalogue.definitions import (
    ADVERSARIAL_CREATE_PARAMETER_OPTIMIZATION_AUDIT_PLAN_TOOL,
    ADVERSARIAL_GENERATE_PARAMETER_OPTIMIZATION_AUDIT_TOOL,
    DATA_GET_INVENTORY_TOOL,
    DATA_SUMMARIZE_QUALITY_TOOL,
    EVALUATION_GENERATE_PARAMETER_OPTIMIZATION_REPORT_TOOL,
    MCP_CONFIG_TOOL,
    RESEARCH_CREATE_BACKTEST_SPECIFICATION_TOOL,
    RESEARCH_CREATE_PARAMETER_OPTIMIZATION_PLAN_TOOL,
    RESEARCH_CREATE_RISK_STACK_SPECIFICATION_TOOL,
    RESEARCH_CREATE_STRATEGY_SPECIFICATION_TOOL,
    RESEARCH_GET_BACKTEST_RESULTS_TOOL,
    RESEARCH_GET_OPTIMIZER_RUNTIME_TOOL,
    RESEARCH_GET_PARAMETER_OPTIMIZATION_RESULTS_TOOL,
    RESEARCH_REGISTER_OPTIMIZATION_OBJECTIVE_TOOL,
    RESEARCH_REGISTER_RISK_MANAGER_IMPLEMENTATION_TOOL,
    RESEARCH_REGISTER_STRATEGY_IMPLEMENTATION_TOOL,
    RESEARCH_RUN_BACKTEST_SPECIFICATION_TOOL,
    RESEARCH_RUN_PARAMETER_OPTIMIZATION_TOOL,
    RESEARCH_RUN_PARAMETER_OPTIMIZATION_VARIANTS_TOOL,
    RESEARCH_VALIDATE_BACKTEST_SPECIFICATION_TOOL,
    RESEARCH_VALIDATE_OPTIMIZATION_OBJECTIVE_TOOL,
    RESEARCH_VALIDATE_RISK_MANAGER_IMPLEMENTATION_TOOL,
    RESEARCH_VALIDATE_RISK_STACK_SPECIFICATION_TOOL,
    RESEARCH_VALIDATE_STRATEGY_IMPLEMENTATION_TOOL,
    RESEARCH_VALIDATE_STRATEGY_SPECIFICATION_TOOL,
)
from trader_research.foundation import json_payload_hash
from trader_research.governance.artifacts import (
    BACKTEST_RUN,
    BACKTEST_SPECIFICATION,
    BACKTEST_SPECIFICATION_VALIDATION_REPORT,
    IMPLEMENTATION_VALIDATION_REPORT,
    IMPLEMENTATION_VERSION,
    PARAMETER_OPTIMIZATION_AUDIT_PLAN,
    PARAMETER_OPTIMIZATION_EVALUATION_REPORT,
    PARAMETER_OPTIMIZATION_PLAN,
    PARAMETER_OPTIMIZATION_ROBUSTNESS_REPORT,
    PARAMETER_OPTIMIZATION_RUN,
    PARAMETER_OPTIMIZATION_TRIAL,
    RISK_STACK_SPECIFICATION,
    RISK_STACK_SPECIFICATION_VALIDATION_REPORT,
    STRATEGY_SPECIFICATION,
    STRATEGY_SPECIFICATION_VALIDATION_REPORT,
)
from trader_research.infrastructure.postgres import PostgresResearchArtifactStore
from tests.cross_package.qualification.support.postgres_57n import ACCESS_STAGE_ENV
from tests.cross_package.qualification.support.realistic_optimization_fixture import (
    ASSET_CLASS,
    BACKTEST_ASSUMPTIONS,
    BASE_STRATEGY_PARAMETERS,
    HOLDOUT_DATASET_ID,
    HOLDOUT_MANIFEST_SHA256,
    HOLDOUT_QUALITY_SHA256,
    INITIAL_CASH,
    OBJECTIVE_SOURCE,
    OBJECTIVE_SOURCE_SHA256,
    RISK_PARAMETERS,
    RISK_PARAMETER_SCHEMA,
    RISK_SOURCE,
    RISK_SOURCE_SHA256,
    SEARCH_LOOKBACKS,
    SEED,
    SELECTION_DATASET_ID,
    SELECTION_MANIFEST_SHA256,
    SELECTION_QUALITY_SHA256,
    STRATEGY_PARAMETER_SCHEMA,
    STRATEGY_SOURCE,
    STRATEGY_SOURCE_SHA256,
    SYMBOLS,
    TIMEFRAME,
    build_realistic_optimization_fixture,
)


_PROJECTIONS = {
    IMPLEMENTATION_VERSION: (
        "research_implementation_versions",
        "implementation_version_id",
    ),
    IMPLEMENTATION_VALIDATION_REPORT: (
        "research_implementation_validations",
        "validation_id",
    ),
    STRATEGY_SPECIFICATION: (
        "research_strategy_specifications",
        "strategy_specification_id",
    ),
    STRATEGY_SPECIFICATION_VALIDATION_REPORT: (
        "research_strategy_specification_validations",
        "validation_id",
    ),
    RISK_STACK_SPECIFICATION: (
        "research_risk_stack_specifications",
        "risk_stack_specification_id",
    ),
    RISK_STACK_SPECIFICATION_VALIDATION_REPORT: (
        "research_risk_stack_specification_validations",
        "validation_id",
    ),
    BACKTEST_SPECIFICATION: (
        "research_backtest_specifications",
        "backtest_specification_id",
    ),
    BACKTEST_SPECIFICATION_VALIDATION_REPORT: (
        "research_backtest_specification_validations",
        "validation_id",
    ),
    BACKTEST_RUN: ("research_backtest_runs", "run_id"),
    PARAMETER_OPTIMIZATION_PLAN: (
        "research_parameter_optimization_plans",
        "optimization_plan_id",
    ),
    PARAMETER_OPTIMIZATION_RUN: (
        "research_parameter_optimization_runs",
        "optimization_run_id",
    ),
    PARAMETER_OPTIMIZATION_TRIAL: (
        "research_parameter_optimization_trials",
        "trial_id",
    ),
    PARAMETER_OPTIMIZATION_EVALUATION_REPORT: (
        "research_parameter_optimization_evaluations",
        "report_id",
    ),
    PARAMETER_OPTIMIZATION_AUDIT_PLAN: (
        "research_parameter_optimization_audit_plans",
        "audit_plan_id",
    ),
    PARAMETER_OPTIMIZATION_ROBUSTNESS_REPORT: (
        "research_parameter_optimization_robustness_reports",
        "report_id",
    ),
}


async def _run_graph(
    session: ClientSession,
    responses: list[Mapping[str, Any]],
    store: PostgresResearchArtifactStore,
) -> Mapping[str, Any]:
    config = await _call(session, MCP_CONFIG_TOOL, {}, responses, collect=False)
    safety = config["data"]["safety"]
    assert safety["backtest_execution_allowed"] is True
    assert safety["optimization_execution_allowed"] is True
    assert safety["data_loading_mutation_allowed"] is False
    assert safety["external_research_writes_allowed"] is False
    assert safety["optuna_writes_allowed"] is False
    assert safety["experiment_tracking_writes_allowed"] is False
    assert config["data"]["research_artifact_store_runtime"] == {
        "backend": "postgres",
        "configured": True,
        "provider": "injected",
        "trader_config_path": None,
        "canonical_uri_scheme": "research://postgres/{artifact_type}/{artifact_id}",
    }
    runtime = await _call(session, RESEARCH_GET_OPTIMIZER_RUNTIME_TOOL, {}, responses)
    profiles = {item["profile_name"]: item for item in runtime["data"]["profiles"]}
    assert profiles["builtin_grid"]["available"] is True
    assert profiles["builtin_random"]["available"] is True

    fixture = build_realistic_optimization_fixture()
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
    _assert_data_snapshot(
        selection_manifest,
        selection_quality,
        dataset_id=SELECTION_DATASET_ID,
        manifest_sha256=SELECTION_MANIFEST_SHA256,
        quality_sha256=SELECTION_QUALITY_SHA256,
        total_rows=48 * len(SYMBOLS),
    )
    _assert_data_snapshot(
        holdout_manifest,
        holdout_quality,
        dataset_id=HOLDOUT_DATASET_ID,
        manifest_sha256=HOLDOUT_MANIFEST_SHA256,
        quality_sha256=HOLDOUT_QUALITY_SHA256,
        total_rows=32 * len(SYMBOLS),
    )

    strategy_validation, strategy = await _register_strategy(session, responses)
    risk_validation, risk = await _register_risk(session, responses)
    objective_validation, objective = await _register_objective(session, responses)
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
    selection_run = _value(
        await _call(
            session,
            RESEARCH_RUN_BACKTEST_SPECIFICATION_TOOL,
            {
                "backtest_specification_validation_ref": selection_validation[
                    "validation_id"
                ]
            },
            responses,
        ),
        "backtest_run",
    )
    _assert_meaningful_backtest(selection_run)
    selection_read = _value(
        await _call(
            session,
            RESEARCH_GET_BACKTEST_RESULTS_TOOL,
            {"run_id": selection_run["run_id"]},
            responses,
        ),
        "backtest_run",
    )
    assert selection_read == selection_run

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
    optimization = _value(
        await _call(
            session,
            RESEARCH_RUN_PARAMETER_OPTIMIZATION_TOOL,
            {
                "optimization_plan_ref": plan["optimization_plan_id"],
                "optimizer_profile": "builtin_grid",
            },
            responses,
        ),
        "parameter_optimization_run",
    )
    optimization_results = await _call(
        session,
        RESEARCH_GET_PARAMETER_OPTIMIZATION_RESULTS_TOOL,
        {"optimization_run_ref": optimization["optimization_run_id"]},
        responses,
    )
    trials = list(optimization_results["data"]["trials"])
    assert optimization_results["data"]["parameter_optimization_run"] == optimization
    _assert_parameter_sensitive_optimization(optimization, trials)
    baseline_digest = json_payload_hash(optimization)
    selected_strategy = store.load_artifact(
        STRATEGY_SPECIFICATION,
        optimization["selected_child_refs"]["strategy_specification_id"],
    )
    selected_strategy_digest = json_payload_hash(selected_strategy)

    selection_runs = store.list_artifacts(artifact_type=BACKTEST_RUN)
    assert len(selection_runs) == 1 + len(SEARCH_LOOKBACKS)
    assert {record.payload["dataset_hash"] for record in selection_runs} == {
        selection_validation["dataset_hash"]
    }
    holdout_validation = await _create_validated_backtest(
        session,
        strategy_validation_id=optimization["selected_child_refs"][
            "strategy_specification_validation_id"
        ],
        risk_validation_id=optimization["selected_child_refs"][
            "risk_stack_specification_validation_id"
        ],
        manifest=holdout_manifest,
        quality=holdout_quality,
        selection_origin_ref=optimization["optimization_run_id"],
        responses=responses,
    )
    holdout_run = _value(
        await _call(
            session,
            RESEARCH_RUN_BACKTEST_SPECIFICATION_TOOL,
            {
                "backtest_specification_validation_ref": holdout_validation[
                    "validation_id"
                ]
            },
            responses,
        ),
        "backtest_run",
    )
    _assert_meaningful_backtest(holdout_run)
    assert holdout_run["dataset_hash"] != selection_validation["dataset_hash"]
    assert holdout_run["selection_origin_ref"] == optimization["optimization_run_id"]
    holdout_read = _value(
        await _call(
            session,
            RESEARCH_GET_BACKTEST_RESULTS_TOOL,
            {
                "backtest_run_uri": f"research://postgres/{BACKTEST_RUN}/{holdout_run['run_id']}"
            },
            responses,
        ),
        "backtest_run",
    )
    assert holdout_read == holdout_run

    evaluation = _value(
        await _call(
            session,
            EVALUATION_GENERATE_PARAMETER_OPTIMIZATION_REPORT_TOOL,
            {
                "optimization_run_ref": optimization["optimization_run_id"],
                "holdout_backtest_run_ref": holdout_run["run_id"],
            },
            responses,
        ),
        "parameter_optimization_evaluation_report",
    )
    assert evaluation["status"] == "passed"
    assert evaluation["valid"] is True
    assert evaluation["selected_trial_id"] == optimization["selected_trial_id"]
    assert evaluation["holdout_backtest_run_id"] == holdout_run["run_id"]
    assert evaluation["holdout_performance"] == holdout_run["summary"]
    assert evaluation["holdout_risk"]["decisions"]["rejected_order_count"] > 0

    audit_plan = _value(
        await _call(
            session,
            ADVERSARIAL_CREATE_PARAMETER_OPTIMIZATION_AUDIT_PLAN_TOOL,
            {
                "optimization_run_ref": optimization["optimization_run_id"],
                "attacks": [
                    {"attack_type": "seed_sensitivity"},
                    {"attack_type": "multiple_testing"},
                ],
            },
            responses,
        ),
        "parameter_optimization_audit_plan",
    )
    variants_payload = await _call(
        session,
        RESEARCH_RUN_PARAMETER_OPTIMIZATION_VARIANTS_TOOL,
        {"audit_plan_ref": audit_plan["audit_plan_id"]},
        responses,
    )
    variants = list(variants_payload["data"]["variant_optimization_runs"])
    assert len(variants) == 1
    assert variants[0]["status"] == "completed"
    assert variants[0]["selected_parameters"] == optimization["selected_parameters"]
    assert variants_payload["data"]["skipped_attacks"] == [
        {"attack_type": "multiple_testing", "reason": "requires separate evidence kind"}
    ]
    audit = _value(
        await _call(
            session,
            ADVERSARIAL_GENERATE_PARAMETER_OPTIMIZATION_AUDIT_TOOL,
            {
                "audit_plan_ref": audit_plan["audit_plan_id"],
                "variant_optimization_run_refs": [variants[0]["optimization_run_id"]],
            },
            responses,
        ),
        "parameter_optimization_robustness_report",
    )
    assert audit["status"] == "passed"
    assert audit["valid"] is True
    assert audit["baseline_selected_trial_id"] == optimization["selected_trial_id"]
    assert {item["attack_type"]: item["covered"] for item in audit["coverage"]} == {
        "multiple_testing": True,
        "seed_sensitivity": True,
    }

    reloaded = store.load_artifact(
        PARAMETER_OPTIMIZATION_RUN, optimization["optimization_run_id"]
    )
    assert json_payload_hash(reloaded) == baseline_digest
    assert reloaded["selected_child_refs"] == optimization["selected_child_refs"]
    reloaded_strategy = store.load_artifact(
        STRATEGY_SPECIFICATION,
        optimization["selected_child_refs"]["strategy_specification_id"],
    )
    assert json_payload_hash(reloaded_strategy) == selected_strategy_digest

    return {
        "strategy_implementation_uri": _uri(
            IMPLEMENTATION_VERSION, strategy["implementation_version_id"]
        ),
        "risk_implementation_uri": _uri(
            IMPLEMENTATION_VERSION, risk["implementation_version_id"]
        ),
        "objective_implementation_uri": _uri(
            IMPLEMENTATION_VERSION, objective["implementation_version_id"]
        ),
        "selection_backtest_uri": _uri(BACKTEST_RUN, selection_run["run_id"]),
        "optimization_plan_uri": _uri(
            PARAMETER_OPTIMIZATION_PLAN, plan["optimization_plan_id"]
        ),
        "optimization_run_uri": _uri(
            PARAMETER_OPTIMIZATION_RUN, optimization["optimization_run_id"]
        ),
        "selected_trial_uri": _uri(
            PARAMETER_OPTIMIZATION_TRIAL, optimization["selected_trial_id"]
        ),
        "holdout_backtest_uri": _uri(BACKTEST_RUN, holdout_run["run_id"]),
        "evaluation_uri": _uri(
            PARAMETER_OPTIMIZATION_EVALUATION_REPORT, evaluation["report_id"]
        ),
        "audit_plan_uri": _uri(
            PARAMETER_OPTIMIZATION_AUDIT_PLAN, audit_plan["audit_plan_id"]
        ),
        "variant_optimization_run_uris": [
            _uri(PARAMETER_OPTIMIZATION_RUN, variants[0]["optimization_run_id"])
        ],
        "adversarial_report_uri": _uri(
            PARAMETER_OPTIMIZATION_ROBUSTNESS_REPORT, audit["report_id"]
        ),
    }


async def _register_strategy(
    session: ClientSession, responses: list[Mapping[str, Any]]
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    strategy = _value(
        await _call(
            session,
            RESEARCH_REGISTER_STRATEGY_IMPLEMENTATION_TOOL,
            {
                "name": "verification-trailing-return-transition",
                "version": "1",
                "source_code": STRATEGY_SOURCE,
                "factory_name": "build_strategy",
                "class_name": "TrailingReturnTransitionStrategy",
                "parameter_schema": STRATEGY_PARAMETER_SCHEMA,
                "authoring_origin": "handwritten_test_fixture",
                "capabilities": ["multi_asset", "long_flat", "event_store_bars"],
            },
            responses,
        ),
        "implementation_version",
    )
    assert strategy["source_hash"] == STRATEGY_SOURCE_SHA256
    validation = _value(
        await _call(
            session,
            RESEARCH_VALIDATE_STRATEGY_IMPLEMENTATION_TOOL,
            {
                "implementation_version_id": strategy["implementation_version_id"],
                "fixture_parameters": BASE_STRATEGY_PARAMETERS,
            },
            responses,
        ),
        "implementation_validation_report",
    )
    return validation, strategy


async def _register_risk(
    session: ClientSession, responses: list[Mapping[str, Any]]
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    risk = _value(
        await _call(
            session,
            RESEARCH_REGISTER_RISK_MANAGER_IMPLEMENTATION_TOOL,
            {
                "name": "verification-entry-quantity-limit",
                "version": "1",
                "source_code": RISK_SOURCE,
                "factory_name": "build_risk_manager",
                "class_name": "EntryQuantityLimitRiskManager",
                "parameter_schema": RISK_PARAMETER_SCHEMA,
                "authoring_origin": "handwritten_test_fixture",
                "capabilities": ["entry_quantity_limit", "risk_reducing_exit"],
            },
            responses,
        ),
        "implementation_version",
    )
    assert risk["source_hash"] == RISK_SOURCE_SHA256
    validation = _value(
        await _call(
            session,
            RESEARCH_VALIDATE_RISK_MANAGER_IMPLEMENTATION_TOOL,
            {
                "implementation_version_id": risk["implementation_version_id"],
                "fixture_parameters": RISK_PARAMETERS,
            },
            responses,
        ),
        "implementation_validation_report",
    )
    return validation, risk


async def _register_objective(
    session: ClientSession, responses: list[Mapping[str, Any]]
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    objective = _value(
        await _call(
            session,
            RESEARCH_REGISTER_OPTIMIZATION_OBJECTIVE_TOOL,
            {
                "name": "verification-risk-adjusted-return",
                "version": "1",
                "source_code": OBJECTIVE_SOURCE,
                "factory_name": "objective",
                "authoring_origin": "handwritten_test_fixture",
            },
            responses,
        ),
        "implementation_version",
    )
    assert objective["source_hash"] == OBJECTIVE_SOURCE_SHA256
    validation = _value(
        await _call(
            session,
            RESEARCH_VALIDATE_OPTIMIZATION_OBJECTIVE_TOOL,
            {"implementation_version_id": objective["implementation_version_id"]},
            responses,
        ),
        "implementation_validation_report",
    )
    return validation, objective


async def _create_behavior_specifications(
    session: ClientSession,
    *,
    strategy_validation_id: str,
    risk_validation_id: str,
    responses: list[Mapping[str, Any]],
) -> Mapping[str, str]:
    assumptions = {
        "broker_mutation_allowed": False,
        "live_trading_allowed": False,
        "raw_sql_allowed": False,
    }
    strategy = _value(
        await _call(
            session,
            RESEARCH_CREATE_STRATEGY_SPECIFICATION_TOOL,
            {
                "implementation_validation_ref": strategy_validation_id,
                "parameters": BASE_STRATEGY_PARAMETERS,
                "portfolio_mode": "multi_asset",
                "required_runtime_context": {
                    "event_store_bars": True,
                    "portfolio_positions": True,
                },
                "execution_assumptions": assumptions,
                "tunable_fields": ["/strategy/parameters/lookback_bars"],
            },
            responses,
        ),
        "strategy_specification",
    )
    strategy_validation = _value(
        await _call(
            session,
            RESEARCH_VALIDATE_STRATEGY_SPECIFICATION_TOOL,
            {"strategy_specification_id": strategy["strategy_specification_id"]},
            responses,
        ),
        "strategy_specification_validation_report",
    )
    risk = _value(
        await _call(
            session,
            RESEARCH_CREATE_RISK_STACK_SPECIFICATION_TOOL,
            {
                "risk_managers": [
                    {
                        "implementation_validation_ref": risk_validation_id,
                        "parameters": RISK_PARAMETERS,
                    }
                ],
                "execution_assumptions": assumptions,
            },
            responses,
        ),
        "risk_stack_specification",
    )
    risk_validation = _value(
        await _call(
            session,
            RESEARCH_VALIDATE_RISK_STACK_SPECIFICATION_TOOL,
            {"risk_stack_specification_id": risk["risk_stack_specification_id"]},
            responses,
        ),
        "risk_stack_specification_validation_report",
    )
    return {
        "strategy_validation_id": strategy_validation["validation_id"],
        "risk_validation_id": risk_validation["validation_id"],
    }


async def _create_validated_backtest(
    session: ClientSession,
    *,
    strategy_validation_id: str,
    risk_validation_id: str,
    manifest: Mapping[str, Any],
    quality: Mapping[str, Any],
    responses: list[Mapping[str, Any]],
    selection_origin_ref: str | None = None,
) -> Mapping[str, Any]:
    specification = _value(
        await _call(
            session,
            RESEARCH_CREATE_BACKTEST_SPECIFICATION_TOOL,
            {
                "strategy_specification_validation_ref": strategy_validation_id,
                "risk_stack_specification_validation_ref": risk_validation_id,
                "dataset_manifest": dict(manifest),
                "data_quality_report": dict(quality),
                "assumptions": BACKTEST_ASSUMPTIONS,
                "initial_cash": INITIAL_CASH,
                "deterministic_seed": SEED,
                "log_cycle_details": False,
                "runtime_limits": {"fixture": "57M", "bounded": True},
                "selection_origin_ref": selection_origin_ref,
            },
            responses,
        ),
        "backtest_specification",
    )
    return _value(
        await _call(
            session,
            RESEARCH_VALIDATE_BACKTEST_SPECIFICATION_TOOL,
            {"backtest_specification_id": specification["backtest_specification_id"]},
            responses,
        ),
        "backtest_specification_validation_report",
    )


async def _mcp_data_evidence(
    session: ClientSession,
    start: str,
    end: str,
    responses: list[Mapping[str, Any]],
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    arguments = {
        "symbols": list(SYMBOLS),
        "asset_class": ASSET_CLASS,
        "timeframe": TIMEFRAME,
        "start": start,
        "end": end,
    }
    inventory = _value(
        await _call(session, DATA_GET_INVENTORY_TOOL, arguments, responses),
        "dataset_manifest",
    )
    quality = _value(
        await _call(session, DATA_SUMMARIZE_QUALITY_TOOL, arguments, responses),
        "data_quality_report",
    )
    return inventory, quality


async def _call(
    session: ClientSession,
    tool_name: str,
    arguments: Mapping[str, Any],
    responses: list[Mapping[str, Any]],
    *,
    collect: bool = True,
) -> Mapping[str, Any]:
    result = await session.call_tool(tool_name, dict(arguments))
    assert result.structuredContent is not None
    payload = result.structuredContent
    assert result.isError is False, payload.get("errors")
    assert payload["ok"] is True, payload.get("errors")
    assert payload["command"] == tool_name
    assert json.loads(result.content[0].text) == payload
    if collect:
        responses.append(payload)
        _assert_artifact_references(payload.get("artifacts") or {})
    return payload


def _value(payload: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = payload["data"].get(key)
    assert isinstance(value, Mapping), payload["data"]
    return value


def _assert_data_snapshot(
    manifest: Mapping[str, Any],
    quality: Mapping[str, Any],
    *,
    dataset_id: str,
    manifest_sha256: str,
    quality_sha256: str,
    total_rows: int,
) -> None:
    assert manifest["dataset_id"] == dataset_id
    assert manifest["complete"] is True
    assert manifest["symbols"] == list(SYMBOLS)
    assert manifest["total_rows"] == total_rows
    assert manifest["source_filter"] is None
    assert json_payload_hash(manifest) == manifest_sha256
    assert quality["report_id"] == f"data_quality_{dataset_id.removeprefix('dataset_')}"
    assert quality["complete"] is True
    assert quality["total_bars"] == total_rows
    assert quality["missing_gap_count"] == 0
    assert quality["missing_bar_count"] == 0
    assert json_payload_hash(quality) == quality_sha256


def _assert_meaningful_backtest(run: Mapping[str, Any]) -> None:
    assert run["status"] == "passed"
    assert run["backtest_kind"] == "portfolio"
    trades = run["bundle"]["trades"]
    assert run["summary"]["trade_count"] >= 6
    assert {trade["side"] for trade in trades} == {"buy", "sell"}
    assert len({trade["symbol"] for trade in trades}) >= 2
    assert run["summary"]["fees"] > 0.0
    assert run["summary"]["slippage"] > 0.0
    exposure = run["bundle"]["exposure_summary"]
    assert exposure["avg_gross_exposure"] > 0.0
    assert exposure["final_gross_notional"] > 0.0
    risk = run["bundle"]["risk_decisions"]
    assert sum(int(item["approved_count"]) for item in risk["decisions"]) > 0
    assert risk["rejected_order_count"] > 0
    breaches = run["bundle"]["risk_limit_breaches"]
    assert breaches["breach_count"] == risk["rejected_order_count"]
    assert any(
        item["symbol"] == "GAMMA" and item["rejection_reason"] == "entry_quantity_limit"
        for item in breaches["breaches"]
    )


def _assert_parameter_sensitive_optimization(
    optimization: Mapping[str, Any], trials: Sequence[Mapping[str, Any]]
) -> None:
    assert optimization["status"] == "completed"
    assert optimization["trial_count"] == len(SEARCH_LOOKBACKS)
    assert optimization["passed_trial_count"] == len(SEARCH_LOOKBACKS)
    assert optimization["failed_trial_count"] == 0
    assert [trial["sequence"] for trial in trials] == list(range(len(SEARCH_LOOKBACKS)))
    assert [
        trial["parameters"]["/strategy/parameters/lookback_bars"] for trial in trials
    ] == list(SEARCH_LOOKBACKS)
    assert all(trial["status"] == "passed" for trial in trials)
    assert all(len(trial["attempts"]) == 1 for trial in trials)
    assert all(trial["attempts"][0]["status"] == "passed" for trial in trials)
    assert all(trial["child_refs"].get("backtest_run_id") for trial in trials)
    values = [float(trial["objective_value"]) for trial in trials]
    returns = [
        float(trial["observation"]["metrics"]["total_return"]) for trial in trials
    ]
    trade_counts = [
        int(trial["observation"]["counts"]["trade_count"]) for trial in trials
    ]
    assert max(values) - min(values) > 1e-6
    assert len({round(value, 12) for value in returns}) > 1
    assert len(set(trade_counts)) > 1
    best = max(values)
    assert sum(abs(value - best) <= 1e-12 for value in values) == 1
    selected = trials[values.index(best)]
    assert optimization["selected_trial_id"] == selected["trial_id"]
    assert optimization["selected_parameters"] == selected["parameters"]
    assert optimization["selected_child_refs"] == selected["child_refs"]
    assert optimization["selection_policy"]["tie_break"] == [
        "canonical_parameters",
        "trial_id",
    ]


def _assert_artifact_references(value: Any) -> None:
    if isinstance(value, Mapping):
        if "artifact_type" in value and "uri" in value:
            assert value["uri"].startswith(
                f"research://postgres/{value['artifact_type']}/"
            )
        for item in value.values():
            _assert_artifact_references(item)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for item in value:
            _assert_artifact_references(item)


def _assert_postgres_graph(
    store: PostgresResearchArtifactStore, evidence: Mapping[str, Any]
) -> None:
    records = store.list_artifacts()
    assert records
    counts: dict[str, int] = {}
    for record in records:
        counts[record.artifact_type] = counts.get(record.artifact_type, 0) + 1
        assert record.artifact_type in _PROJECTIONS
        table, id_column = _PROJECTIONS[record.artifact_type]
        projection = (
            store.connection()
            .execute(
                f"SELECT payload FROM {table} WHERE {id_column} = %s",
                [record.artifact_id],
            )
            .fetchone()
        )
        assert projection is not None
        assert projection["payload"] == record.payload
        canonical = (
            store.connection()
            .execute(
                "SELECT payload FROM research_artifacts WHERE artifact_type = %s AND artifact_id = %s",
                [record.artifact_type, record.artifact_id],
            )
            .fetchone()
        )
        assert canonical == {"payload": record.payload}
    assert counts[IMPLEMENTATION_VERSION] == 3
    assert counts[IMPLEMENTATION_VALIDATION_REPORT] == 3
    assert counts[PARAMETER_OPTIMIZATION_PLAN] == 2
    assert counts[PARAMETER_OPTIMIZATION_RUN] == 2
    assert counts[PARAMETER_OPTIMIZATION_TRIAL] == 8
    assert counts[PARAMETER_OPTIMIZATION_EVALUATION_REPORT] == 1
    assert counts[PARAMETER_OPTIMIZATION_AUDIT_PLAN] == 1
    assert counts[PARAMETER_OPTIMIZATION_ROBUSTNESS_REPORT] == 1
    for uri in _all_strings(evidence):
        if uri.startswith("research://"):
            _, _, suffix = uri.partition("research://postgres/")
            artifact_type, _, artifact_id = suffix.partition("/")
            assert store.load_artifact(artifact_type, artifact_id)


def _assert_no_filesystem_authority(
    responses: Sequence[Mapping[str, Any]], store: PostgresResearchArtifactStore
) -> None:
    forbidden_keys = {
        "artifact_dir",
        "artifact_path",
        "bundle_path",
        "filesystem_path",
        "output_path",
        "report_path",
        "run_ref_path",
    }
    values: list[Any] = list(responses)
    values.extend(record.payload for record in store.list_artifacts())
    for value in values:
        for key in _all_keys(value):
            assert key not in forbidden_keys
        for text in _all_strings(value):
            lowered = text.lower()
            assert not lowered.startswith("file://")
            assert not lowered.startswith("/home/")
            assert not lowered.startswith("/tmp/")
            assert not lowered.startswith("artifacts/research")


def _all_keys(value: Any) -> list[str]:
    keys: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            keys.append(str(key))
            keys.extend(_all_keys(item))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for item in value:
            keys.extend(_all_keys(item))
    return keys


def _all_strings(value: Any) -> list[str]:
    strings: list[str] = []
    if isinstance(value, str):
        strings.append(value)
    elif isinstance(value, Mapping):
        for item in value.values():
            strings.extend(_all_strings(item))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for item in value:
            strings.extend(_all_strings(item))
    return strings


def _server_parameters(*, access_stage: str | None = None) -> StdioServerParameters:
    repo_root = Path(__file__).resolve().parents[3]
    environment = dict(os.environ)
    source_path = str(repo_root / "src")
    environment["PYTHONPATH"] = (
        f"{repo_root}{os.pathsep}{source_path}{os.pathsep}{environment.get('PYTHONPATH', '')}"
    )
    environment.update(
        {
            "TRADER_MCP_TRADER_CONFIG_PATH": "",
            "TRADER_MCP_ALLOW_BROKER_MUTATION": "false",
            "TRADER_MCP_ALLOW_RAW_SQL": "false",
            "TRADER_MCP_ALLOW_SYMBOL_PROVIDER_DISCOVERY": "false",
            "TRADER_MCP_ALLOW_DATA_LOADING": "false",
            "TRADER_MCP_ALLOW_BACKTESTS": "true",
            "TRADER_MCP_ALLOW_OPTIMIZATION": "true",
            "TRADER_MCP_ALLOW_EXTERNAL_RESEARCH_WRITES": "false",
            "TRADER_MCP_ALLOW_OPTUNA_WRITES": "false",
            "TRADER_MCP_ALLOW_EXPERIMENT_TRACKING_WRITES": "false",
        }
    )
    if access_stage is not None:
        environment[ACCESS_STAGE_ENV] = access_stage
    else:
        environment.pop(ACCESS_STAGE_ENV, None)
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "tests.cross_package.qualification.support.mcp_postgres_optimization_server"],
        cwd=repo_root,
        env=environment,
    )


def _uri(artifact_type: str, artifact_id: str) -> str:
    return f"research://postgres/{artifact_type}/{artifact_id}"
