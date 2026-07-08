from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import anyio

from tests.support.duckdb_store import DuckDBEventStore
from tests.test_mcp_research_toolchain import (
    METHOD_ID,
    _knowledge_store_with_bollinger_signal,
    _method_contract,
    _signal_fixtures_period_2,
)
from tests.test_portfolio_backtests import (
    PORTFOLIO_END,
    PORTFOLIO_START,
    PORTFOLIO_SYMBOLS,
    _load_portfolio_bars,
    _portfolio_config,
)
from trader_mcp.constants import (
    DATA_GET_INVENTORY_TOOL,
    DATA_SUMMARIZE_QUALITY_TOOL,
    EVALUATION_GENERATE_PERFORMANCE_REPORT_TOOL,
    MATH_PACKAGE_METHOD_ARTIFACT_TOOL,
    MATH_REGISTER_METHOD_IMPLEMENTATION_TOOL,
    MATH_RUN_SIGNAL_FIXTURES_TOOL,
    MCP_CONFIG_TOOL,
    RESEARCH_CREATE_RISK_MANAGER_CANDIDATE_TOOL,
    RESEARCH_CREATE_STRATEGY_CANDIDATE_TOOL,
    RESEARCH_CREATE_STRATEGY_RISK_STACK_TOOL,
    RESEARCH_RUN_PORTFOLIO_BACKTEST_TOOL,
    RESEARCH_VALIDATE_RISK_MANAGER_CANDIDATE_TOOL,
    RESEARCH_VALIDATE_STRATEGY_CANDIDATE_TOOL,
    RESEARCH_VALIDATE_STRATEGY_RISK_STACK_TOOL,
)
from trader_mcp.environment import load_local_environment
from trader_mcp.server import create_server
from trader_research.artifact_store import InMemoryResearchArtifactStore
from trader_research.domain import (
    EVALUATION_REPORT,
    METHOD_IMPLEMENTATION_MANIFEST,
    METHOD_PACKAGE_MANIFEST,
    PORTFOLIO_BACKTEST_RUN_REF,
    RISK_MANAGER_CANDIDATE,
    STRATEGY_CANDIDATE,
    STRATEGY_RISK_STACK,
)


def test_mcp_portfolio_risk_toolchain_runs_to_evaluation_report(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    store = DuckDBEventStore(str(tmp_path / "portfolio_events.duckdb"))
    _load_portfolio_bars(store)
    knowledge_store = _knowledge_store_with_bollinger_signal(artifact_root)
    artifact_store = InMemoryResearchArtifactStore()
    environment = replace(
        load_local_environment("env.template"),
        artifact_root=artifact_root,
        allow_backtests=True,
    )
    server = create_server(
        environment,
        event_store_provider=lambda: store,
        knowledge_store_provider=lambda: knowledge_store,
        research_artifact_store_provider=lambda: artifact_store,
        backtest_config_provider=lambda: _portfolio_config(tmp_path),
    )

    async def _run() -> None:
        config = await server.call_tool(MCP_CONFIG_TOOL, {})
        inventory = await server.call_tool(DATA_GET_INVENTORY_TOOL, _data_args())
        quality = await server.call_tool(DATA_SUMMARIZE_QUALITY_TOOL, _data_args())
        registered = await server.call_tool(
            MATH_REGISTER_METHOD_IMPLEMENTATION_TOOL,
            {
                "method_id": METHOD_ID,
                "method_card_ids": ["method_card_bollinger_bwma_action_signal_algorithmic_trading_v1"],
                "method_contract": _method_contract(),
            },
        )
        validated_signal = await server.call_tool(
            MATH_RUN_SIGNAL_FIXTURES_TOOL,
            {
                "implementation_manifest": registered.structuredContent["data"]["method_implementation_manifest"],
                "fixtures": _signal_fixtures_period_2(),
            },
        )
        method_package = await server.call_tool(
            MATH_PACKAGE_METHOD_ARTIFACT_TOOL,
            {
                "implementation_manifest": validated_signal.structuredContent["data"]["method_implementation_manifest"],
                "validation_report": validated_signal.structuredContent["data"][
                    "signal_implementation_validation_report"
                ],
            },
        )
        created_strategy = await server.call_tool(
            RESEARCH_CREATE_STRATEGY_CANDIDATE_TOOL,
            {
                "template_family": "cross_sectional_momentum",
                "method_package_refs": [
                    {
                        "role": "ranking_signal",
                        "package_manifest": method_package.structuredContent["data"]["method_package_manifest"],
                    }
                ],
                "parameters": {"lookback_period": 1, "top_n": 2, "rebalance_cadence": "every_bar"},
                "sizing": {"target_qty_when_long": 1.0, "max_position_qty": 10.0},
            },
        )
        strategy_candidate = created_strategy.structuredContent["data"]["strategy_candidate_manifest"]
        validated_strategy = await server.call_tool(
            RESEARCH_VALIDATE_STRATEGY_CANDIDATE_TOOL,
            {"strategy_candidate_manifest": strategy_candidate},
        )
        strategy_report = validated_strategy.structuredContent["data"]["strategy_candidate_validation_report"]
        created_risk = await server.call_tool(
            RESEARCH_CREATE_RISK_MANAGER_CANDIDATE_TOOL,
            {
                "template_family": "gross_exposure_cap",
                "parameters": {"max_gross_exposure": 1_000_000.0},
            },
        )
        risk_candidate = created_risk.structuredContent["data"]["risk_manager_candidate_manifest"]
        rejected_stack = await server.call_tool(
            RESEARCH_CREATE_STRATEGY_RISK_STACK_TOOL,
            {
                "strategy_candidate_validation_report": strategy_report,
                "risk_manager_validation_refs": [
                    {
                        "risk_manager_candidate_validation_report": {
                            "artifact_type": "risk_manager_candidate_validation_report",
                            "validation_id": "risk_validation_failed",
                            "candidate_id": risk_candidate["candidate_id"],
                            "status": "failed",
                            "blockers": ["fixture failed"],
                        }
                    }
                ],
            },
        )
        validated_risk = await server.call_tool(
            RESEARCH_VALIDATE_RISK_MANAGER_CANDIDATE_TOOL,
            {"risk_manager_candidate_manifest": risk_candidate},
        )
        risk_report = validated_risk.structuredContent["data"]["risk_manager_candidate_validation_report"]
        created_stack = await server.call_tool(
            RESEARCH_CREATE_STRATEGY_RISK_STACK_TOOL,
            {
                "strategy_candidate_validation_report": strategy_report,
                "risk_manager_validation_refs": [{"risk_manager_candidate_validation_report": risk_report}],
            },
        )
        stack_manifest = created_stack.structuredContent["data"]["strategy_risk_stack_manifest"]
        validated_stack = await server.call_tool(
            RESEARCH_VALIDATE_STRATEGY_RISK_STACK_TOOL,
            {"strategy_risk_stack_manifest": stack_manifest},
        )
        stack_report = validated_stack.structuredContent["data"]["strategy_risk_stack_validation_report"]
        rejected_portfolio = await server.call_tool(
            RESEARCH_RUN_PORTFOLIO_BACKTEST_TOOL,
            {
                "strategy_risk_stack_validation_report": {**stack_report, "status": "failed"},
                "dataset_manifest": inventory.structuredContent["data"]["dataset_manifest"],
            },
        )
        portfolio = await server.call_tool(
            RESEARCH_RUN_PORTFOLIO_BACKTEST_TOOL,
            {
                "strategy_risk_stack_validation_report": stack_report,
                "dataset_manifest": inventory.structuredContent["data"]["dataset_manifest"],
                "data_quality_report": quality.structuredContent["data"]["data_quality_report"],
                "max_runs": 12,
            },
        )
        performance = await server.call_tool(
            EVALUATION_GENERATE_PERFORMANCE_REPORT_TOOL,
            {
                "portfolio_backtest_run_ref": portfolio.structuredContent["data"]["portfolio_backtest_run_ref"],
                "data_quality_report": quality.structuredContent["data"]["data_quality_report"],
            },
        )

        for result in (
            inventory,
            quality,
            registered,
            validated_signal,
            method_package,
            created_strategy,
            validated_strategy,
            created_risk,
            validated_risk,
            created_stack,
            validated_stack,
            portfolio,
            performance,
        ):
            assert result.isError is False, result.structuredContent

        assert rejected_stack.isError is True
        assert "status must be passed" in rejected_stack.structuredContent["errors"][0]["message"]
        assert rejected_portfolio.isError is True
        assert rejected_portfolio.structuredContent["errors"][0]["code"] == "portfolio_backtest_input_validation_failed"

        config_tools = {tool["name"]: tool for tool in config.structuredContent["data"]["tools"]}
        assert config_tools[RESEARCH_RUN_PORTFOLIO_BACKTEST_TOOL]["agent_owner"] == "Quant Research Supervisor Agent"
        assert config_tools[RESEARCH_RUN_PORTFOLIO_BACKTEST_TOOL]["side_effect"] == "local_mutating"
        assert config.structuredContent["data"]["safety"]["backtest_execution_allowed"] is True
        assert config.structuredContent["data"]["research_artifact_store_runtime"]["configured"] is True
        assert config.structuredContent["data"]["research_artifact_store_runtime"]["provider"] == "injected"

        run_ref = portfolio.structuredContent["data"]["portfolio_backtest_run_ref"]
        assert run_ref["artifact_type"] == "portfolio_backtest_run_ref"
        assert run_ref["uri"] == f"research://postgres/portfolio_backtest_run_ref/{run_ref['run_id']}"
        assert run_ref["data_scope"]["symbols"] == list(PORTFOLIO_SYMBOLS)
        assert run_ref["strategy_risk_stack_id"] == stack_manifest["stack_id"]
        assert run_ref["strategy_risk_stack_validation_id"] == stack_report["validation_id"]
        assert portfolio.structuredContent["data"]["risk_decisions"]["manager_count"] == 1
        assert portfolio.structuredContent["data"]["risk_measure_summary"]["missing_required_telemetry"] == []
        assert run_ref["artifact_dir"] is None
        assert run_ref["artifact_paths"] == {}
        assert run_ref["artifact_uris"]["portfolio_backtest_run_ref"] == run_ref["uri"]

        report = performance.structuredContent["data"]["evaluation_report"]
        assert report["status"] == "passed"
        assert report["backtest_kind"] == "portfolio"
        assert report["strategy_risk_stack_id"] == stack_manifest["stack_id"]
        assert report["risk_decisions"]["manager_count"] == 1
        assert report["risk_measure_summary"]["missing_required_telemetry"] == []
        evaluation_ref = performance.structuredContent["artifacts"]["evaluation_report"]
        assert evaluation_ref["path"] is None
        assert evaluation_ref["uri"] == f"research://postgres/evaluation_report/{report['report_id']}"
        artifact_types = {record.artifact_type for record in artifact_store.list_artifacts()}
        assert {
            METHOD_IMPLEMENTATION_MANIFEST,
            METHOD_PACKAGE_MANIFEST,
            STRATEGY_CANDIDATE,
            RISK_MANAGER_CANDIDATE,
            STRATEGY_RISK_STACK,
            PORTFOLIO_BACKTEST_RUN_REF,
            EVALUATION_REPORT,
        } <= artifact_types

    anyio.run(_run)


def _data_args() -> dict[str, Any]:
    return {
        "symbols": list(PORTFOLIO_SYMBOLS),
        "asset_class": "stocks",
        "timeframe": "1Min",
        "start": PORTFOLIO_START.isoformat().replace("+00:00", "Z"),
        "end": PORTFOLIO_END.isoformat().replace("+00:00", "Z"),
    }
