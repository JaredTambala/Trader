from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import anyio

from trader_mcp.constants import (
    KNOWLEDGE_CREATE_METHOD_CARD_DRAFT_TOOL,
    KNOWLEDGE_GET_EVIDENCE_CHUNKS_TOOL,
    KNOWLEDGE_INGEST_DOCUMENTS_TOOL,
    KNOWLEDGE_PUBLISH_METHOD_CARD_TOOL,
    KNOWLEDGE_REGISTER_SOURCE_TOOL,
    KNOWLEDGE_RETRIEVE_EVIDENCE_TOOL,
    KNOWLEDGE_VALIDATE_CITATIONS_TOOL,
    MATH_LIST_METHOD_CONTRACTS_TOOL,
    MATH_GENERATE_PYTHON_METHOD_TOOL,
    MATH_REGISTER_METHOD_IMPLEMENTATION_TOOL,
    MATH_RUN_INDICATOR_FIXTURES_TOOL,
    MATH_VALIDATE_METHOD_CONTRACT_TOOL,
    MCP_CONFIG_TOOL,
    REGISTERED_TOOL_NAMES,
)
from trader_mcp.environment import load_local_environment
from trader_mcp.server import create_server
from trader_agents.llm_client import StaticJsonLlmClient
from trader_research.knowledge.embeddings import DeterministicEmbeddingProvider
from trader_research.knowledge.store import JsonKnowledgeStore


def test_mcp_quant_methods_core_evidence_flow(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    source_dir = artifact_root / "knowledge_sources"
    source_dir.mkdir(parents=True)
    source = source_dir / "sma.md"
    source.write_text(Path("tests/fixtures/knowledge/sma_method.md").read_text(encoding="utf-8"), encoding="utf-8")
    environment = replace(load_local_environment("env.template"), artifact_root=artifact_root)
    knowledge_store = JsonKnowledgeStore(artifact_root)
    server = create_server(
        environment,
        knowledge_embedding_provider=DeterministicEmbeddingProvider(),
        knowledge_store_provider=lambda: knowledge_store,
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
        assert config_tools[KNOWLEDGE_CREATE_METHOD_CARD_DRAFT_TOOL]["side_effect"] == "local_mutating"
        assert config_tools[KNOWLEDGE_PUBLISH_METHOD_CARD_TOOL]["side_effect"] == "local_mutating"
        assert config_tools[MATH_VALIDATE_METHOD_CONTRACT_TOOL]["side_effect"] == "read_only"
        assert config_tools[MATH_REGISTER_METHOD_IMPLEMENTATION_TOOL]["side_effect"] == "local_mutating"
        assert config_tools[MATH_RUN_INDICATOR_FIXTURES_TOOL]["side_effect"] == "local_mutating"
        assert config_tools[MATH_GENERATE_PYTHON_METHOD_TOOL]["side_effect"] == "local_mutating"
        assert registered.isError is False
        assert ingested.isError is False
        assert dereferenced.isError is False
        assert draft.isError is False
        assert draft.structuredContent["data"]["method_card_draft"]["status"] == "draft"
        assert published.isError is False
        assert published.structuredContent["data"]["method_card"]["status"] == "approved"
        assert registered_implementation.isError is False
        assert fixture_validation.isError is False
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
