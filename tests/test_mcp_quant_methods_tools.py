from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import anyio

from trader_mcp.constants import (
    KNOWLEDGE_ASSEMBLE_METHODOLOGY_EVIDENCE_TOOL,
    KNOWLEDGE_CREATE_METHOD_CARD_DRAFT_TOOL,
    KNOWLEDGE_CREATE_RICH_METHOD_CARD_DRAFT_TOOL,
    KNOWLEDGE_DISCOVER_METHODOLOGY_CANDIDATES_TOOL,
    KNOWLEDGE_EXTRACT_METHODOLOGY_FIELDS_TOOL,
    KNOWLEDGE_GET_EVIDENCE_CHUNKS_TOOL,
    KNOWLEDGE_INGEST_DOCUMENTS_TOOL,
    KNOWLEDGE_PUBLISH_METHOD_CARD_TOOL,
    KNOWLEDGE_REGISTER_SOURCE_TOOL,
    KNOWLEDGE_RETRIEVE_EVIDENCE_TOOL,
    KNOWLEDGE_VALIDATE_CITATIONS_TOOL,
    KNOWLEDGE_VALIDATE_METHODOLOGY_CANDIDATE_TOOL,
    KNOWLEDGE_UPDATE_METHOD_CARD_STATUS_TOOL,
    MATH_COMPILE_KERNEL_TOOL,
    MATH_GENERATE_CPP_KERNEL_TOOL,
    MATH_LIST_METHOD_CONTRACTS_TOOL,
    MATH_GENERATE_PYTHON_METHOD_TOOL,
    MATH_PACKAGE_METHOD_ARTIFACT_TOOL,
    MATH_REGISTER_METHOD_IMPLEMENTATION_TOOL,
    MATH_RUN_INDICATOR_FIXTURES_TOOL,
    MATH_RUN_MULTIPLE_TESTING_REPORT_TOOL,
    MATH_RUN_SIGNAL_DIAGNOSTICS_TOOL,
    MATH_RUN_SIGNAL_FIXTURES_TOOL,
    MATH_VALIDATE_METHOD_CONTRACT_TOOL,
    MCP_CONFIG_TOOL,
    REGISTERED_TOOL_NAMES,
    RESEARCH_CREATE_STRATEGY_CANDIDATE_TOOL,
    RESEARCH_VALIDATE_STRATEGY_CANDIDATE_TOOL,
)
from trader_mcp.environment import load_local_environment
from trader_mcp.server import create_server
from trader_agents.llm_client import StaticJsonLlmClient
from trader_research.artifact_store import InMemoryResearchArtifactStore
from trader_research.domain import (
    METHODOLOGY_CANDIDATE,
    METHODOLOGY_CANDIDATE_VALIDATION_REPORT,
    METHODOLOGY_EVIDENCE_PACKET,
    METHODOLOGY_FIELD_EXTRACTION_REPORT,
)
from trader_research.knowledge.embeddings import DeterministicEmbeddingProvider
from trader_research.knowledge.store import JsonKnowledgeStore
from trader_research.methods.contracts import MethodRegistryEntry, ParameterSpec


def test_mcp_quant_methods_core_evidence_flow(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    source_dir = artifact_root / "knowledge_sources"
    source_dir.mkdir(parents=True)
    source = source_dir / "sma.md"
    source.write_text(Path("tests/fixtures/knowledge/sma_method.md").read_text(encoding="utf-8"), encoding="utf-8")
    environment = replace(load_local_environment("env.template"), artifact_root=artifact_root)
    knowledge_store = JsonKnowledgeStore(artifact_root)
    artifact_store = InMemoryResearchArtifactStore()
    server = create_server(
        environment,
        knowledge_embedding_provider=DeterministicEmbeddingProvider(),
        knowledge_store_provider=lambda: knowledge_store,
        research_artifact_store_provider=lambda: artifact_store,
        method_generation_llm_client=StaticJsonLlmClient(
            [
                {
                    "class_name": "GeneratedSmaIndicator",
                    "source_code": GENERATED_SMA_SOURCE,
                }
            ]
        ),
    )

    async def _run() -> None:
        tools = await server.list_tools()
        config = await server.call_tool(MCP_CONFIG_TOOL, {})
        registered = await server.call_tool(
            KNOWLEDGE_REGISTER_SOURCE_TOOL,
            {
                "path": str(source),
                "title": "SMA Source",
                "source_type": "internal_note",
                "topics": ["indicators"],
                "method_families": ["indicator"],
            },
        )
        source_id = registered.structuredContent["data"]["knowledge_source_manifest"]["source_id"]
        ingested = await server.call_tool(KNOWLEDGE_INGEST_DOCUMENTS_TOOL, {"source_ids": [source_id]})
        retrieved = await server.call_tool(
            KNOWLEDGE_RETRIEVE_EVIDENCE_TOOL,
            {"query": "moving average warmup", "source_ids": [source_id], "top_k": 1},
        )
        evidence = retrieved.structuredContent["data"]["evidence_retrieval_report"]["results"][0]
        dereferenced = await server.call_tool(
            KNOWLEDGE_GET_EVIDENCE_CHUNKS_TOOL,
            {"chunk_ids": [evidence["chunk_id"]], "source_id": source_id},
        )
        draft = await server.call_tool(
            KNOWLEDGE_CREATE_METHOD_CARD_DRAFT_TOOL,
            {
                "method_id": "sma",
                "title": "Persisted SMA Method Card",
                "family": "indicator",
                "assumptions": ["input observations are ordered"],
                "inputs": ["price series"],
                "outputs": ["rolling mean series"],
                "failure_modes": ["insufficient warmup observations"],
                "evidence_refs": [
                    {
                        "source_id": evidence["source_id"],
                        "chunk_id": evidence["chunk_id"],
                        "locator": evidence["locator"],
                    }
                ],
            },
        )
        draft_id = draft.structuredContent["data"]["method_card_draft"]["method_card_id"]
        published = await server.call_tool(
            KNOWLEDGE_PUBLISH_METHOD_CARD_TOOL,
            {
                "draft_method_card_id": draft_id,
                "approved_method_card_id": "method_card_persisted_sma_v1",
                "approved_by": "test",
                "approval_note": "fixture evidence reviewed",
                "approve": True,
            },
        )
        citations = await server.call_tool(
            KNOWLEDGE_VALIDATE_CITATIONS_TOOL,
            {
                "artifact": {
                    "knowledge_evidence_refs": [
                        {
                            "source_id": evidence["source_id"],
                            "chunk_id": evidence["chunk_id"],
                            "locator": evidence["locator"],
                            "method_card_id": "method_card_persisted_sma_v1",
                        }
                    ]
                }
            },
        )
        methods = await server.call_tool(MATH_LIST_METHOD_CONTRACTS_TOOL, {})
        valid_contract = await server.call_tool(
            MATH_VALIDATE_METHOD_CONTRACT_TOOL,
            {"method_contract": {"method_id": "sma", "parameters": {"period": 20}, "no_lookahead": True}},
        )
        implementation_contract = {
            "method_id": "sma",
            "parameters": {"period": 3},
            "no_lookahead": True,
            "knowledge_evidence_refs": [{"method_card_id": "method_card_persisted_sma_v1"}],
        }
        registered_implementation = await server.call_tool(
            MATH_REGISTER_METHOD_IMPLEMENTATION_TOOL,
            {
                "method_id": "sma",
                "method_card_ids": ["method_card_persisted_sma_v1"],
                "method_contract": implementation_contract,
            },
        )
        implementation_manifest = registered_implementation.structuredContent["data"]["method_implementation_manifest"]
        fixture_validation = await server.call_tool(
            MATH_RUN_INDICATOR_FIXTURES_TOOL,
            {"implementation_manifest": implementation_manifest},
        )
        method_package = await server.call_tool(
            MATH_PACKAGE_METHOD_ARTIFACT_TOOL,
            {
                "implementation_manifest": fixture_validation.structuredContent["data"]["method_implementation_manifest"],
                "validation_report": fixture_validation.structuredContent["data"]["indicator_validation_report"],
            },
        )
        generated_cpp = await server.call_tool(
            MATH_GENERATE_CPP_KERNEL_TOOL,
            {"implementation_manifest": fixture_validation.structuredContent["data"]["method_implementation_manifest"]},
        )
        generated = await server.call_tool(
            MATH_GENERATE_PYTHON_METHOD_TOOL,
            {
                "method_id": "sma",
                "method_card_ids": ["method_card_persisted_sma_v1"],
                "method_contract": implementation_contract,
            },
        )

        assert {tool.name for tool in tools} == set(REGISTERED_TOOL_NAMES)
        assert config.structuredContent is not None
        config_tools = {tool["name"]: tool for tool in config.structuredContent["data"]["tools"]}
        assert config.structuredContent["data"]["embedding_runtime"] == {
            "configured": False,
            "provider": None,
            "model": None,
            "base_url": None,
            "api_key_configured": False,
            "timeout_seconds": 30.0,
        }
        assert config.structuredContent["data"]["knowledge_store_runtime"]["provider"] == "injected"
        assert config_tools[KNOWLEDGE_REGISTER_SOURCE_TOOL]["agent_owner"] == "Quantitative Methods Agent"
        assert config_tools[KNOWLEDGE_REGISTER_SOURCE_TOOL]["side_effect"] == "local_mutating"
        assert config_tools[KNOWLEDGE_GET_EVIDENCE_CHUNKS_TOOL]["side_effect"] == "read_only"
        assert config_tools[KNOWLEDGE_DISCOVER_METHODOLOGY_CANDIDATES_TOOL]["side_effect"] == "local_mutating"
        assert config_tools[KNOWLEDGE_ASSEMBLE_METHODOLOGY_EVIDENCE_TOOL]["side_effect"] == "local_mutating"
        assert config_tools[KNOWLEDGE_EXTRACT_METHODOLOGY_FIELDS_TOOL]["side_effect"] == "local_mutating"
        assert config_tools[KNOWLEDGE_VALIDATE_METHODOLOGY_CANDIDATE_TOOL]["side_effect"] == "local_mutating"
        assert config_tools[KNOWLEDGE_CREATE_METHOD_CARD_DRAFT_TOOL]["side_effect"] == "local_mutating"
        assert config_tools[KNOWLEDGE_CREATE_RICH_METHOD_CARD_DRAFT_TOOL]["side_effect"] == "local_mutating"
        assert config_tools[KNOWLEDGE_PUBLISH_METHOD_CARD_TOOL]["side_effect"] == "local_mutating"
        assert config_tools[KNOWLEDGE_UPDATE_METHOD_CARD_STATUS_TOOL]["side_effect"] == "local_mutating"
        assert config_tools[MATH_VALIDATE_METHOD_CONTRACT_TOOL]["side_effect"] == "read_only"
        assert config_tools[MATH_REGISTER_METHOD_IMPLEMENTATION_TOOL]["side_effect"] == "local_mutating"
        assert config_tools[MATH_RUN_INDICATOR_FIXTURES_TOOL]["side_effect"] == "local_mutating"
        assert config_tools[MATH_RUN_SIGNAL_FIXTURES_TOOL]["side_effect"] == "local_mutating"
        assert config_tools[MATH_GENERATE_PYTHON_METHOD_TOOL]["side_effect"] == "local_mutating"
        assert config_tools[MATH_RUN_SIGNAL_DIAGNOSTICS_TOOL]["side_effect"] == "local_mutating"
        assert config_tools[MATH_RUN_MULTIPLE_TESTING_REPORT_TOOL]["side_effect"] == "local_mutating"
        assert config_tools[MATH_GENERATE_CPP_KERNEL_TOOL]["side_effect"] == "local_mutating"
        assert config_tools[MATH_COMPILE_KERNEL_TOOL]["side_effect"] == "local_mutating"
        assert config_tools[MATH_PACKAGE_METHOD_ARTIFACT_TOOL]["side_effect"] == "local_mutating"
        assert registered.isError is False
        assert ingested.isError is False
        assert dereferenced.isError is False
        assert draft.isError is False
        assert draft.structuredContent["data"]["method_card_draft"]["status"] == "draft"
        assert published.isError is False
        assert published.structuredContent["data"]["method_card"]["status"] == "approved"
        assert registered_implementation.isError is False
        assert fixture_validation.isError is False
        assert method_package.isError is False
        assert method_package.structuredContent["data"]["method_package_manifest"]["method_id"] == "sma"
        assert generated_cpp.isError is False
        assert generated_cpp.structuredContent["data"]["cxx_kernel_manifest"]["method_id"] == "sma"
        assert generated.isError is False
        assert generated.structuredContent["data"]["status"] == "validated"
        assert dereferenced.structuredContent["agent_owner"] == "Quantitative Methods Agent"
        dereferenced_chunk = dereferenced.structuredContent["data"]["chunks"][0]
        assert "simple moving average computes the arithmetic mean" in dereferenced_chunk["text"]
        assert dereferenced_chunk["hash_verified"] is True
        assert citations.isError is False
        assert methods.structuredContent["data"]["method_count"] >= 5
        assert valid_contract.isError is False
        assert valid_contract.structuredContent["agent_owner"] == "Quantitative Methods Agent"

    anyio.run(_run)


def test_mcp_methodology_candidate_discovery_extraction_validation_flow(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    source_dir = artifact_root / "knowledge_sources"
    source_dir.mkdir(parents=True)
    source = source_dir / "pairs.md"
    source.write_text(
        (
            "# Pairs Trading\n\n"
            "Pairs trading forms a spread between two related assets. The method estimates a hedge ratio "
            "with regression and tests for cointegration and stationarity.\n\n"
            "The spread signal enters when the z-score crosses a threshold and exits when it mean reverts.\n"
            "The primary limitation is structural break risk when the pair relationship changes.\n"
        ),
        encoding="utf-8",
    )
    environment = replace(load_local_environment("env.template"), artifact_root=artifact_root)
    knowledge_store = JsonKnowledgeStore(artifact_root)
    artifact_store = InMemoryResearchArtifactStore()
    server = create_server(
        environment,
        knowledge_embedding_provider=DeterministicEmbeddingProvider(),
        knowledge_store_provider=lambda: knowledge_store,
        research_artifact_store_provider=lambda: artifact_store,
    )

    async def _run() -> None:
        registered = await server.call_tool(
            KNOWLEDGE_REGISTER_SOURCE_TOOL,
            {
                "path": str(source),
                "title": "Pairs Trading Source",
                "source_type": "method_textbook",
                "topics": ["statistical arbitrage"],
                "method_families": ["statistical_arbitrage"],
            },
        )
        source_id = registered.structuredContent["data"]["knowledge_source_manifest"]["source_id"]
        ingested = await server.call_tool(KNOWLEDGE_INGEST_DOCUMENTS_TOOL, {"source_ids": [source_id]})
        discovered = await server.call_tool(
            KNOWLEDGE_DISCOVER_METHODOLOGY_CANDIDATES_TOOL,
            {
                "source_ids": [source_id],
                "method_families": ["statistical_arbitrage"],
                "neighbor_radius": 1,
                "max_candidates": 2,
            },
        )
        candidate_ref = discovered.structuredContent["artifacts"]["methodology_candidates"][0]
        assembled = await server.call_tool(
            KNOWLEDGE_ASSEMBLE_METHODOLOGY_EVIDENCE_TOOL,
            {"methodology_candidate_uri": candidate_ref["uri"], "readiness_goal": "strategy_template"},
        )
        evidence_packet_ref = assembled.structuredContent["artifacts"]["methodology_evidence_packet"]
        extracted = await server.call_tool(
            KNOWLEDGE_EXTRACT_METHODOLOGY_FIELDS_TOOL,
            {"evidence_packet_uri": evidence_packet_ref["uri"]},
        )
        extraction_ref = extracted.structuredContent["artifacts"]["methodology_field_extraction_report"]
        validated = await server.call_tool(
            KNOWLEDGE_VALIDATE_METHODOLOGY_CANDIDATE_TOOL,
            {"extraction_report_uri": extraction_ref["uri"]},
        )
        validation_ref = validated.structuredContent["artifacts"]["methodology_candidate_validation_report"]
        rich_draft = await server.call_tool(
            KNOWLEDGE_CREATE_RICH_METHOD_CARD_DRAFT_TOOL,
            {
                "methodology_candidate_validation_uri": validation_ref["uri"],
                "method_id": "pairs_mean_reversion",
                "title": "Pairs Mean Reversion",
                "family": "statistical_arbitrage",
            },
        )
        rich_draft_id = rich_draft.structuredContent["data"]["method_card_draft"]["method_card_id"]
        published = await server.call_tool(
            KNOWLEDGE_PUBLISH_METHOD_CARD_TOOL,
            {
                "draft_method_card_id": rich_draft_id,
                "approved_method_card_id": "method_card_pairs_mean_reversion_mcp_v1",
                "approved_by": "test",
                "approval_note": "validated methodology candidate reviewed",
                "approve": True,
            },
        )
        strategy = await server.call_tool(
            RESEARCH_CREATE_STRATEGY_CANDIDATE_TOOL,
            {
                "template_family": "pairs_mean_reversion",
                "method_package_refs": [],
                "rich_method_card_id": "method_card_pairs_mean_reversion_mcp_v1",
                "parameters": {"lookback_period": 20, "entry_zscore": 1.5, "exit_zscore": 0.5, "max_pairs": 1},
            },
        )
        strategy_manifest = strategy.structuredContent["data"]["strategy_candidate_manifest"]
        strategy_validation = await server.call_tool(
            RESEARCH_VALIDATE_STRATEGY_CANDIDATE_TOOL,
            {"strategy_candidate_manifest": strategy_manifest},
        )

        assert registered.isError is False
        assert ingested.isError is False
        assert discovered.isError is False
        assert assembled.isError is False
        packet = assembled.structuredContent["data"]["methodology_evidence_packet"]
        assert packet["artifact_type"] == METHODOLOGY_EVIDENCE_PACKET
        candidate = discovered.structuredContent["data"]["methodology_candidates"][0]
        assert candidate["artifact_type"] == METHODOLOGY_CANDIDATE
        assert candidate_ref["uri"] == f"research://postgres/methodology_candidate/{candidate['methodology_candidate_id']}"
        assert extracted.isError is False
        extracted_candidate = extracted.structuredContent["data"]["methodology_candidate"]
        assert extracted_candidate["extension_fields"]["statistical_arbitrage"]["hedge_ratio_method"]["evidence_refs"]
        assert validated.isError is False
        report = validated.structuredContent["data"]["methodology_candidate_validation_report"]
        assert report["artifact_type"] == METHODOLOGY_CANDIDATE_VALIDATION_REPORT
        assert report["status"] == "passed"
        assert rich_draft.isError is False
        assert rich_draft.structuredContent["data"]["method_card_draft"]["card_format"] == "rich_method_card"
        assert published.isError is False
        assert published.structuredContent["data"]["method_card"]["status"] == "approved"
        assert strategy.isError is False
        assert strategy_manifest["template_family"] == "pairs_mean_reversion"
        assert strategy_manifest["methodology_refs"][0]["artifact_id"] == "method_card_pairs_mean_reversion_mcp_v1"
        assert strategy_validation.isError is False
        assert strategy_validation.structuredContent["data"]["strategy_candidate_validation_report"]["status"] == "passed"
        artifact_types = {record.artifact_type for record in artifact_store.list_artifacts()}
        assert {
            METHODOLOGY_CANDIDATE,
            METHODOLOGY_EVIDENCE_PACKET,
            METHODOLOGY_FIELD_EXTRACTION_REPORT,
            METHODOLOGY_CANDIDATE_VALIDATION_REPORT,
        }.issubset(artifact_types)

    anyio.run(_run)


def test_mcp_methodology_candidate_tools_fail_without_research_artifact_store(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    environment = replace(load_local_environment("env.template"), artifact_root=artifact_root)
    knowledge_store = JsonKnowledgeStore(artifact_root)
    server = create_server(
        environment,
        knowledge_embedding_provider=DeterministicEmbeddingProvider(),
        knowledge_store_provider=lambda: knowledge_store,
        research_artifact_store_provider=lambda: None,
    )

    async def _run() -> None:
        discovered = await server.call_tool(
            KNOWLEDGE_DISCOVER_METHODOLOGY_CANDIDATES_TOOL,
            {"query": "pairs trading"},
        )
        assembled = await server.call_tool(
            KNOWLEDGE_ASSEMBLE_METHODOLOGY_EVIDENCE_TOOL,
            {"methodology_candidate_id": "methodology_candidate_missing_store"},
        )
        rich_draft = await server.call_tool(
            KNOWLEDGE_CREATE_RICH_METHOD_CARD_DRAFT_TOOL,
            {
                "methodology_candidate_validation_report": {
                    "artifact_type": METHODOLOGY_CANDIDATE_VALIDATION_REPORT,
                    "validation_id": "methodology_candidate_validation_missing_store",
                    "methodology_candidate_id": "methodology_candidate_missing_store",
                    "status": "passed",
                    "valid": True,
                }
            },
        )

        assert discovered.isError is True
        assert discovered.structuredContent["errors"][0]["code"] == "research_artifact_store_unavailable"
        assert assembled.isError is True
        assert assembled.structuredContent["errors"][0]["code"] == "research_artifact_store_unavailable"
        assert rich_draft.isError is True
        assert rich_draft.structuredContent["errors"][0]["message"] == "research artifact store is required"

    anyio.run(_run)


def test_mcp_quant_methods_signal_diagnostics_and_multiple_testing(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    environment = replace(load_local_environment("env.template"), artifact_root=artifact_root)
    knowledge_store = JsonKnowledgeStore(artifact_root)
    server = create_server(
        environment,
        knowledge_embedding_provider=DeterministicEmbeddingProvider(),
        knowledge_store_provider=lambda: knowledge_store,
    )

    candidate_family = {
        "candidate_family_id": "family_mcp_diagnostics",
        "candidates": [
            {"candidate_id": "c1", "signal_name": "MCP Action Signal"},
            {"candidate_id": "c2", "signal_name": "MCP Score Signal"},
        ],
        "tested_grid": {"kind": ["action", "score"]},
    }
    rank_ic_contract = {
        "method_id": "rank_ic",
        "parameters": {"horizon": 1},
        "knowledge_evidence_refs": [{"method_card_id": "method_card_rank_ic_seed_v1"}],
    }
    bh_contract = {
        "method_id": "benjamini_hochberg",
        "parameters": {"alpha": 0.05},
        "knowledge_evidence_refs": [{"method_card_id": "method_card_benjamini_hochberg_seed_v1"}],
    }
    observations = [
        {"candidate_id": "c1", "signal_name": "MCP Action Signal", "symbol": "AAA", "ts": "2026-01-01T09:30:00+00:00", "value": 1.0},
        {"candidate_id": "c1", "signal_name": "MCP Action Signal", "symbol": "AAA", "ts": "2026-01-01T09:31:00+00:00", "value": -1.0},
        {"candidate_id": "c1", "signal_name": "MCP Action Signal", "symbol": "AAA", "ts": "2026-01-01T09:32:00+00:00", "value": 1.0},
        {"candidate_id": "c1", "signal_name": "MCP Action Signal", "symbol": "AAA", "ts": "2026-01-01T09:33:00+00:00", "value": -1.0},
        {"candidate_id": "c2", "signal_name": "MCP Score Signal", "symbol": "BBB", "ts": "2026-01-01T09:30:00+00:00", "value": 0.1},
        {"candidate_id": "c2", "signal_name": "MCP Score Signal", "symbol": "BBB", "ts": "2026-01-01T09:31:00+00:00", "value": 0.2},
        {"candidate_id": "c2", "signal_name": "MCP Score Signal", "symbol": "BBB", "ts": "2026-01-01T09:32:00+00:00", "value": 0.3},
        {"candidate_id": "c2", "signal_name": "MCP Score Signal", "symbol": "BBB", "ts": "2026-01-01T09:33:00+00:00", "value": 0.4},
    ]
    labels = [
        {"symbol": "AAA", "ts": "2026-01-01T09:30:00+00:00", "horizon": 1, "forward_return": 0.01},
        {"symbol": "AAA", "ts": "2026-01-01T09:31:00+00:00", "horizon": 1, "forward_return": -0.01},
        {"symbol": "AAA", "ts": "2026-01-01T09:32:00+00:00", "horizon": 1, "forward_return": 0.02},
        {"symbol": "AAA", "ts": "2026-01-01T09:33:00+00:00", "horizon": 1, "forward_return": 0.03},
        {"symbol": "BBB", "ts": "2026-01-01T09:30:00+00:00", "horizon": 1, "forward_return": 0.01},
        {"symbol": "BBB", "ts": "2026-01-01T09:31:00+00:00", "horizon": 1, "forward_return": 0.02},
        {"symbol": "BBB", "ts": "2026-01-01T09:32:00+00:00", "horizon": 1, "forward_return": 0.03},
        {"symbol": "BBB", "ts": "2026-01-01T09:33:00+00:00", "horizon": 1, "forward_return": 0.04},
    ]

    async def _run() -> None:
        tools = await server.list_tools()
        diagnostics = await server.call_tool(
            MATH_RUN_SIGNAL_DIAGNOSTICS_TOOL,
            {
                "signal_observations": observations,
                "forward_return_labels": labels,
                "candidate_family_manifest": candidate_family,
                "method_contracts": [rank_ic_contract],
                "quantile_count": 4,
            },
        )
        multiple_testing = await server.call_tool(
            MATH_RUN_MULTIPLE_TESTING_REPORT_TOOL,
            {
                "candidate_family_manifest": candidate_family,
                "metric_matrix": [
                    {"candidate_id": "c1", "p_value": 0.01},
                    {"candidate_id": "c2", "p_value": 0.20},
                ],
                "method_contract": bh_contract,
            },
        )

        assert {tool.name for tool in tools} == set(REGISTERED_TOOL_NAMES)
        assert diagnostics.isError is False
        assert multiple_testing.isError is False
        assert diagnostics.structuredContent["agent_owner"] == "Quantitative Methods Agent"
        assert multiple_testing.structuredContent["agent_owner"] == "Quantitative Methods Agent"
        assert "signal_diagnostic_report" in diagnostics.structuredContent["artifacts"]
        assert "multiple_testing_report" in multiple_testing.structuredContent["artifacts"]

    anyio.run(_run)


def test_mcp_quant_methods_signal_evidence_flow(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    source_dir = artifact_root / "knowledge_sources"
    source_dir.mkdir(parents=True)
    source = source_dir / "bollinger_bwma.md"
    source.write_text(
        (
            "The Bollinger BWMA band rule computes a moving average, variance, upper band, and lower band. "
            "If price is above the upper band then sell. If price is below the lower band then buy. "
            "No action is taken in-between."
        ),
        encoding="utf-8",
    )
    method_card_id = "method_card_bollinger_bwma_action_signal_algorithmic_trading_v1"
    environment = replace(load_local_environment("env.template"), artifact_root=artifact_root)
    knowledge_store = JsonKnowledgeStore(artifact_root)
    knowledge_store.save_method_contract(
        MethodRegistryEntry(
            method_id="bollinger_bwma_action_signal",
            family="signal",
            status="approved",
            purpose="Emit a scalar Bollinger/BWMA band action signal from a fixed trailing price window.",
            parameters=(
                ParameterSpec("period", "int", min_value=2, max_value=500, default=20),
                ParameterSpec("stddev_multiplier", "float", min_value=0, max_value=10, default=2.0),
            ),
            inputs=("latest-first OHLCV bar window",),
            outputs=("scalar action signal: +1 buy, -1 sell, 0 no action",),
            assumptions=("input bars are ordered latest first",),
            failure_modes=("insufficient warmup observations",),
            artifact_outputs=("method_implementation_manifest.json", "signal_implementation_validation_report.json"),
            warmup="period observations",
            nan_policy="reject",
            no_lookahead=True,
            requires_evidence=True,
            approved_method_card_ids=(method_card_id,),
            runtime_contract="trader.signals.Signal",
        )
    )
    artifact_store = InMemoryResearchArtifactStore()
    server = create_server(
        environment,
        knowledge_embedding_provider=DeterministicEmbeddingProvider(),
        knowledge_store_provider=lambda: knowledge_store,
        research_artifact_store_provider=lambda: artifact_store,
    )

    async def _run() -> None:
        registered = await server.call_tool(
            KNOWLEDGE_REGISTER_SOURCE_TOOL,
            {
                "path": str(source),
                "title": "Bollinger BWMA Signal Source",
                "source_type": "internal_note",
                "topics": ["signals"],
                "method_families": ["signal"],
            },
        )
        source_id = registered.structuredContent["data"]["knowledge_source_manifest"]["source_id"]
        ingested = await server.call_tool(KNOWLEDGE_INGEST_DOCUMENTS_TOOL, {"source_ids": [source_id]})
        retrieved = await server.call_tool(
            KNOWLEDGE_RETRIEVE_EVIDENCE_TOOL,
            {
                "query": "Bollinger BWMA upper band lower band buy sell no action",
                "source_ids": [source_id],
                "method_family": "signal",
                "top_k": 1,
            },
        )
        evidence = retrieved.structuredContent["data"]["evidence_retrieval_report"]["results"][0]
        dereferenced = await server.call_tool(
            KNOWLEDGE_GET_EVIDENCE_CHUNKS_TOOL,
            {"chunk_ids": [evidence["chunk_id"]], "source_id": source_id},
        )
        draft = await server.call_tool(
            KNOWLEDGE_CREATE_METHOD_CARD_DRAFT_TOOL,
            {
                "method_id": "bollinger_bwma_action_signal",
                "title": "Bollinger BWMA Action Signal",
                "family": "signal",
                "assumptions": ["input bars are ordered latest first"],
                "inputs": ["latest-first OHLCV bar window"],
                "outputs": ["scalar action signal: +1 buy, -1 sell, 0 no action"],
                "failure_modes": ["insufficient warmup observations"],
                "evidence_refs": [
                    {
                        "source_id": evidence["source_id"],
                        "chunk_id": evidence["chunk_id"],
                        "locator": evidence["locator"],
                    }
                ],
            },
        )
        draft_id = draft.structuredContent["data"]["method_card_draft"]["method_card_id"]
        published = await server.call_tool(
            KNOWLEDGE_PUBLISH_METHOD_CARD_TOOL,
            {
                "draft_method_card_id": draft_id,
                "approved_method_card_id": method_card_id,
                "approved_by": "test",
                "approval_note": "signal evidence reviewed",
                "approve": True,
            },
        )
        citations = await server.call_tool(
            KNOWLEDGE_VALIDATE_CITATIONS_TOOL,
            {
                "artifact": {
                    "knowledge_evidence_refs": [
                        {
                            "source_id": evidence["source_id"],
                            "chunk_id": evidence["chunk_id"],
                            "locator": evidence["locator"],
                            "method_card_id": method_card_id,
                        }
                    ]
                }
            },
        )
        method_contract = {
            "method_id": "bollinger_bwma_action_signal",
            "parameters": {"period": 20, "stddev_multiplier": 2.0},
            "no_lookahead": True,
            "knowledge_evidence_refs": [{"method_card_id": method_card_id}],
        }
        valid_contract = await server.call_tool(
            MATH_VALIDATE_METHOD_CONTRACT_TOOL,
            {"method_contract": method_contract},
        )
        registered_implementation = await server.call_tool(
            MATH_REGISTER_METHOD_IMPLEMENTATION_TOOL,
            {
                "method_id": "bollinger_bwma_action_signal",
                "method_card_ids": [method_card_id],
                "method_contract": method_contract,
            },
        )
        implementation_manifest = registered_implementation.structuredContent["data"]["method_implementation_manifest"]
        fixture_validation = await server.call_tool(
            MATH_RUN_SIGNAL_FIXTURES_TOOL,
            {"implementation_manifest": implementation_manifest},
        )

        assert registered.isError is False
        assert ingested.isError is False
        assert retrieved.isError is False
        assert dereferenced.isError is False
        assert "upper band then sell" in dereferenced.structuredContent["data"]["chunks"][0]["text"]
        assert draft.isError is False
        assert published.isError is False
        assert published.structuredContent["data"]["method_card"]["method_card_id"] == method_card_id
        assert citations.isError is False
        assert valid_contract.isError is False
        assert registered_implementation.isError is False
        assert implementation_manifest["runtime_contract"] == "trader.signals.Signal"
        assert fixture_validation.isError is False
        report = fixture_validation.structuredContent["data"]["signal_implementation_validation_report"]
        assert report["status"] == "passed"
        assert [result["actual"] for result in report["fixture_results"]] == [1.0, -1.0, 0.0]
        assert "signal_implementation_validation_report" in fixture_validation.structuredContent["artifacts"]

    anyio.run(_run)


GENERATED_SMA_SOURCE = '''"""Citation-backed simple moving average implementation.

Source reference:
- Approved method card: ``method_card_persisted_sma_v1``.
- Registry method: ``sma``.

Implements:
- Entrypoint ``GeneratedSmaIndicator``.
- Trader runtime contract ``trader.indicators.Indicator``.
- For each completed trailing window of ``period`` close values, return the arithmetic mean.
- Outputs omit warmup observations and are latest-first.
- No lookahead: every output uses only close values inside its trailing window.
"""

from trader.indicators import Indicator


class GeneratedSmaIndicator(Indicator):
    def __init__(self, period: int = 3) -> None:
        self.period = int(period)

    @property
    def name(self) -> str:
        return "sma"

    @property
    def window(self) -> int:
        return self.period

    def compute_series(self, bars):
        closes = [float(bar.close) for bar in bars]
        if len(closes) < self.window:
            raise ValueError("Insufficient bars for SMA computation")
        values = []
        for idx in range(0, len(closes) - self.window + 1):
            values.append(sum(closes[idx : idx + self.window]) / self.window)
        return values
'''
