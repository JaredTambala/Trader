from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import anyio

from tests.support.duckdb_store import DuckDBEventStore
from trader.config import Config
from trader_mcp.constants import (
    DATA_GET_INVENTORY_TOOL,
    DATA_SUMMARIZE_QUALITY_TOOL,
    EVALUATION_GENERATE_PERFORMANCE_REPORT_TOOL,
    MATH_PACKAGE_METHOD_ARTIFACT_TOOL,
    MATH_REGISTER_METHOD_IMPLEMENTATION_TOOL,
    MATH_RUN_SIGNAL_FIXTURES_TOOL,
    MCP_CONFIG_TOOL,
    RESEARCH_CREATE_STRATEGY_CANDIDATE_TOOL,
    RESEARCH_RUN_BACKTEST_TOOL,
    RESEARCH_VALIDATE_STRATEGY_CANDIDATE_TOOL,
)
from trader_mcp.environment import load_local_environment
from trader_mcp.server import create_server
from trader_research.artifact_store import InMemoryResearchArtifactStore
from trader_research.knowledge.domain import MethodCard
from trader_research.knowledge.store import JsonKnowledgeStore
from trader_research.methods.contracts import MethodRegistryEntry, ParameterSpec


METHOD_ID = "bollinger_bwma_action_signal"
METHOD_CARD_ID = "method_card_bollinger_bwma_action_signal_algorithmic_trading_v1"


def test_mcp_research_toolchain_runs_from_method_package_to_performance_report(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    store = DuckDBEventStore(str(tmp_path / "events.duckdb"))
    _load_bollinger_reentry_bars(store)
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
        backtest_config_provider=lambda: _config(tmp_path),
    )

    async def _run() -> None:
        config = await server.call_tool(MCP_CONFIG_TOOL, {})
        inventory = await server.call_tool(DATA_GET_INVENTORY_TOOL, _data_args())
        quality = await server.call_tool(DATA_SUMMARIZE_QUALITY_TOOL, _data_args())
        registered = await server.call_tool(
            MATH_REGISTER_METHOD_IMPLEMENTATION_TOOL,
            {
                "method_id": METHOD_ID,
                "method_card_ids": [METHOD_CARD_ID],
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
                "validation_report": validated_signal.structuredContent["data"]["signal_implementation_validation_report"],
            },
        )
        created_candidate = await server.call_tool(
            RESEARCH_CREATE_STRATEGY_CANDIDATE_TOOL,
            {
                "template_family": "bollinger_band",
                "method_package_refs": [
                    {
                        "role": "bollinger_band_signal",
                        "package_manifest": method_package.structuredContent["data"]["method_package_manifest"],
                    }
                ],
                "parameters": {"period": 2, "stddev_multiplier": 0.5},
                "sizing": {"target_qty_when_long": 1.0, "max_position_qty": 5.0},
            },
        )
        strategy_candidate = created_candidate.structuredContent["data"]["strategy_candidate_manifest"]
        validated_strategy = await server.call_tool(
            RESEARCH_VALIDATE_STRATEGY_CANDIDATE_TOOL,
            {"strategy_candidate_manifest": strategy_candidate},
        )
        validation_report = validated_strategy.structuredContent["data"]["strategy_candidate_validation_report"]
        backtest = await server.call_tool(
            RESEARCH_RUN_BACKTEST_TOOL,
            {
                "strategy_candidate_manifest": strategy_candidate,
                "strategy_candidate_validation_report": validation_report,
                "dataset_manifest": inventory.structuredContent["data"]["dataset_manifest"],
                "data_quality_report": quality.structuredContent["data"]["data_quality_report"],
            },
        )
        performance = await server.call_tool(
            EVALUATION_GENERATE_PERFORMANCE_REPORT_TOOL,
            {
                "backtest_run_ref": backtest.structuredContent["data"]["backtest_run_ref"],
                "data_quality_report": quality.structuredContent["data"]["data_quality_report"],
            },
        )

        config_tools = {tool["name"]: tool for tool in config.structuredContent["data"]["tools"]}
        assert config_tools[MATH_PACKAGE_METHOD_ARTIFACT_TOOL]["agent_owner"] == "Quantitative Methods Agent"
        assert config_tools[RESEARCH_CREATE_STRATEGY_CANDIDATE_TOOL]["agent_owner"] == "Quant Research Supervisor Agent"
        assert config_tools[RESEARCH_RUN_BACKTEST_TOOL]["side_effect"] == "local_mutating"
        assert config_tools[EVALUATION_GENERATE_PERFORMANCE_REPORT_TOOL]["agent_owner"] == "Evaluation Agent"
        assert config.structuredContent["data"]["safety"]["backtest_execution_allowed"] is True

        for result in (
            inventory,
            quality,
            registered,
            validated_signal,
            method_package,
            created_candidate,
            validated_strategy,
            backtest,
            performance,
        ):
            assert result.isError is False, result.structuredContent

        package_manifest = method_package.structuredContent["data"]["method_package_manifest"]
        assert package_manifest["artifact_type"] == "method_package_manifest"
        assert package_manifest["status"] == "validated"
        assert package_manifest["runtime_contract"] == "trader.signals.Signal"
        assert method_package.structuredContent["artifacts"]["method_package_manifest"]["path"] is None
        assert method_package.structuredContent["artifacts"]["method_package_manifest"]["uri"].startswith(
            "research://postgres/method_package_manifest/"
        )

        assert strategy_candidate["artifact_type"] == "strategy_candidate"
        assert strategy_candidate["method_package_refs"][0]["metadata"]["package_id"] == package_manifest["package_id"]
        assert strategy_candidate["strategy_source"]["runtime_contract"] == "trader.strategies.Strategy"
        assert strategy_candidate["strategy_source"]["path"] is None
        assert strategy_candidate["strategy_source"]["uri"].startswith("research://postgres/strategy_implementation/")

        assert validation_report["status"] == "passed"
        assert validation_report["candidate_id"] == strategy_candidate["candidate_id"]
        assert validated_strategy.structuredContent["artifacts"]["strategy_candidate_validation_report"]["path"] is None
        assert validated_strategy.structuredContent["artifacts"]["strategy_candidate_validation_report"]["uri"].startswith(
            "research://postgres/strategy_candidate_validation_report/"
        )

        run_ref = backtest.structuredContent["data"]["backtest_run_ref"]
        assert run_ref["candidate_id"] == strategy_candidate["candidate_id"]
        assert run_ref["validation_id"] == validation_report["validation_id"]
        assert run_ref["dataset_id"] == inventory.structuredContent["data"]["dataset_manifest"]["dataset_id"]
        assert backtest.structuredContent["data"]["summary"]["trade_count"] >= 1
        assert Path(run_ref["artifact_paths"]["trades"]).exists()

        report = performance.structuredContent["data"]["evaluation_report"]
        assert report["artifact_type"] == "evaluation_report"
        assert report["report_kind"] == "performance_report"
        assert report["status"] == "passed"
        assert report["run_id"] == run_ref["run_id"]
        assert report["candidate_id"] == strategy_candidate["candidate_id"]
        assert report["validation_id"] == validation_report["validation_id"]
        assert report["dataset_id"] == run_ref["dataset_id"]
        assert report["trade_stats"]["trade_count"] >= 1
        assert performance.structuredContent["artifacts"]["evaluation_report"]["path"] is None
        assert performance.structuredContent["artifacts"]["evaluation_report"]["uri"].startswith(
            "research://postgres/evaluation_report/"
        )

    anyio.run(_run)


def test_mcp_research_toolchain_rejects_missing_method_provenance(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    knowledge_store = JsonKnowledgeStore(artifact_root)
    environment = replace(load_local_environment("env.template"), artifact_root=artifact_root)
    server = create_server(environment, knowledge_store_provider=lambda: knowledge_store)

    async def _run() -> None:
        result = await server.call_tool(
            MATH_REGISTER_METHOD_IMPLEMENTATION_TOOL,
            {
                "method_id": METHOD_ID,
                "method_card_ids": [METHOD_CARD_ID],
                "method_contract": _method_contract(),
            },
        )

        assert result.isError is True
        assert result.structuredContent["errors"][0]["code"] == "method_implementation_registration_failed"
        assert "approved method-card evidence does not match the requested method" in result.structuredContent["data"]["blockers"]

    anyio.run(_run)


def test_mcp_research_toolchain_rejects_unvalidated_strategy_candidates(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    store = DuckDBEventStore(str(tmp_path / "events.duckdb"))
    _load_bollinger_reentry_bars(store)
    artifact_store = InMemoryResearchArtifactStore()
    environment = replace(
        load_local_environment("env.template"),
        artifact_root=artifact_root,
        allow_backtests=True,
    )
    server = create_server(
        environment,
        event_store_provider=lambda: store,
        research_artifact_store_provider=lambda: artifact_store,
        backtest_config_provider=lambda: _config(tmp_path),
    )

    async def _run() -> None:
        inventory = await server.call_tool(DATA_GET_INVENTORY_TOOL, _data_args())
        created_candidate = await server.call_tool(
            RESEARCH_CREATE_STRATEGY_CANDIDATE_TOOL,
            {
                "template_family": "bollinger_band",
                "method_package_refs": [
                    {
                        "role": "bollinger_band_signal",
                        "package_manifest": _validated_signal_package_fixture(),
                    }
                ],
                "parameters": {"period": 2, "stddev_multiplier": 0.5},
            },
        )
        result = await server.call_tool(
            RESEARCH_RUN_BACKTEST_TOOL,
            {
                "strategy_candidate_manifest": created_candidate.structuredContent["data"]["strategy_candidate_manifest"],
                "strategy_candidate_validation_report": {
                    "artifact_type": "strategy_candidate_validation_report",
                    "validation_id": "strategy_validation_failed",
                    "candidate_id": created_candidate.structuredContent["data"]["strategy_candidate_manifest"]["candidate_id"],
                    "status": "failed",
                    "blockers": [{"code": "fixture_failed", "message": "fixture failed"}],
                },
                "dataset_manifest": inventory.structuredContent["data"]["dataset_manifest"],
            },
        )

        assert created_candidate.isError is False
        assert result.isError is True
        assert result.structuredContent["errors"][0]["code"] == "backtest_input_validation_failed"
        assert "validation report status must be passed" in result.structuredContent["errors"][0]["message"]

    anyio.run(_run)


def _knowledge_store_with_bollinger_signal(artifact_root: Path) -> JsonKnowledgeStore:
    store = JsonKnowledgeStore(artifact_root)
    store.save_method_card(
        MethodCard(
            method_card_id=METHOD_CARD_ID,
            method_card_set_id="method_card_set_bollinger_bwma_action_signal_test",
            revision_number=1,
            method_id=METHOD_ID,
            title="Bollinger BWMA action signal",
            family="signal",
            status="approved",
            assumptions=("input bars are ordered latest first",),
            inputs=("latest-first OHLCV bar window",),
            outputs=("scalar action signal",),
            failure_modes=("insufficient warmup observations",),
            approved_by="test",
            approval_note="Approved for end-to-end MCP toolchain evidence.",
        )
    )
    store.save_method_contract(
        MethodRegistryEntry(
            method_id=METHOD_ID,
            family="signal",
            status="approved",
            purpose="Validate a Bollinger/BWMA trade-intent signal implementation.",
            parameters=(
                ParameterSpec("period", "int", min_value=2, max_value=100),
                ParameterSpec("stddev_multiplier", "float", min_value=0.1, max_value=10.0),
            ),
            inputs=("latest-first OHLCV bar window",),
            outputs=("scalar action signal",),
            assumptions=("input bars are ordered latest first",),
            failure_modes=("insufficient warmup observations",),
            artifact_outputs=("signal_implementation_validation_report.json",),
            warmup="period observations",
            nan_policy="return 0 for invalid windows",
            no_lookahead=True,
            requires_evidence=True,
            approved_method_card_ids=(METHOD_CARD_ID,),
            runtime_contract="trader.signals.Signal",
        )
    )
    return store


def _load_bollinger_reentry_bars(store: DuckDBEventStore) -> None:
    start = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    closes = (1.0, 1.0, 2.0, 1.0, 1.0, 1.0)
    for index, close in enumerate(closes):
        ts = start + timedelta(minutes=index)
        store.record_event(
            "stock_bar_events",
            {
                "symbol": "DEMO",
                "timeframe": "1Min",
                "ts": ts,
                "ingested_at": ts,
                "open": close,
                "high": close,
                "low": close,
                "close": close,
                "volume": 100.0 + index,
                "trade_count": 1.0,
                "vwap": close,
                "source": "task33_fixture",
            },
        )


def _data_args() -> dict[str, Any]:
    return {
        "symbols": ["DEMO"],
        "asset_class": "stocks",
        "timeframe": "1Min",
        "start": "2026-01-20T12:00:00Z",
        "end": "2026-01-20T12:05:00Z",
    }


def _method_contract() -> dict[str, Any]:
    return {
        "method_id": METHOD_ID,
        "parameters": {"period": 2, "stddev_multiplier": 0.5},
        "no_lookahead": True,
        "knowledge_evidence_refs": [{"method_card_id": METHOD_CARD_ID}],
    }


def _signal_fixtures_period_2() -> list[dict[str, Any]]:
    return [
        {
            "fixture_id": "task33_bollinger_bwma_action_lower_band_buy",
            "closes": [10.0, 1.0],
            "expected": 1.0,
            "expected_prefix": [None, 1.0],
            "tolerance": 1e-9,
        },
        {
            "fixture_id": "task33_bollinger_bwma_action_upper_band_sell",
            "closes": [1.0, 10.0],
            "expected": -1.0,
            "expected_prefix": [None, -1.0],
            "tolerance": 1e-9,
        },
        {
            "fixture_id": "task33_bollinger_bwma_action_in_band_no_action",
            "closes": [10.0, 10.0],
            "expected": 0.0,
            "expected_prefix": [None, 0.0],
            "tolerance": 1e-9,
        },
    ]


def _validated_signal_package_fixture() -> dict[str, Any]:
    return {
        "artifact_type": "method_package_manifest",
        "schema_version": "1",
        "package_id": "method_package_task33_fixture",
        "method_id": METHOD_ID,
        "runtime_contract": "trader.signals.Signal",
        "implementation_id": "method_impl_task33_fixture",
        "entrypoint": "trader_standard.signals:BollingerBwmaActionSignal",
        "class_name": "BollingerBwmaActionSignal",
        "source_path": "src/trader_standard/signals/bollinger_bwma_action_signal.py",
        "source_hash": "task33_fixture_hash",
        "source_provenance": {"kind": "fixture"},
        "constructor_kwargs": {"period": 2, "stddev_multiplier": 0.5},
        "method_contract": _method_contract(),
        "method_card_ids": [METHOD_CARD_ID],
        "validation_report_ref": {
            "artifact_type": "signal_implementation_validation_report",
            "validation_id": "signal_validation_task33_fixture",
            "status": "passed",
        },
        "validation_summary": {"status": "passed", "fixture_count": 1},
        "safety_profile": {"no_broker_access": True},
        "dependency_allowlist": ["trader", "trader_standard"],
        "cxx_kernel_refs": [],
        "warnings": [],
        "blockers": [],
        "status": "validated",
    }


def _config(tmp_path: Path) -> Config:
    return Config(
        mode="once",
        strategy_type="research",
        strategy_id="research",
        strategy_timeframe="1Min",
        sma_short_window=2,
        sma_long_window=3,
        db_path=str(tmp_path / "events.duckdb"),
        event_store="postgres",
        market_data_source="noop",
        market_data_asset_class="stocks",
        market_data_stock_feed="iex",
        market_data_symbols=("DEMO",),
        market_data_max_age_seconds=60,
        alpaca_api_key="",
        alpaca_secret_key="",
        alpaca_data_base_url="https://data.alpaca.markets",
        alpaca_base_url="https://paper-api.alpaca.markets",
        pg_dsn="",
        pg_host="",
        pg_port=5432,
        pg_db="",
        pg_user="",
        pg_password="",
        buffered_event_store=False,
        buffer_flush_interval_ms=250,
        buffer_max_batch_size=500,
        buffer_max_queue_size=10000,
        buffer_block_on_full=True,
        log_signal_events=True,
        log_indicator_events=True,
        log_order_events=True,
        log_fill_events=True,
        log_position_snapshots=True,
        broker_type="noop",
    )
