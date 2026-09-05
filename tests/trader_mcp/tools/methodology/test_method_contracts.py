"""Adapter tests for MCP methodology contracts and implementation evidence.

Subject: Method registration, fixtures, diagnostics, multiple testing, and draft-card adapters.
Level: Adapter integration.
Collaborators: Real MCP/research services with deterministic embeddings and local stores.
Guarantees: Maintained methods expose validated artifacts and unavailable canonical writes fail closed.
Non-goals: C++ compilation, remote embeddings, model interpretation, or strategy profitability.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import anyio

from trader_mcp.catalogue.definitions import (
    KNOWLEDGE_ASSEMBLE_METHODOLOGY_EVIDENCE_TOOL,
    KNOWLEDGE_CREATE_METHOD_CARD_DRAFT_TOOL,
    KNOWLEDGE_DISCOVER_METHODOLOGY_CANDIDATES_TOOL,
    KNOWLEDGE_EXTRACT_METHODOLOGY_FIELDS_TOOL,
    KNOWLEDGE_PUBLISH_METHOD_CARD_TOOL,
    KNOWLEDGE_REGISTER_SOURCE_TOOL,
    KNOWLEDGE_UPDATE_METHOD_CARD_STATUS_TOOL,
    KNOWLEDGE_VALIDATE_METHODOLOGY_CANDIDATE_TOOL,
    MATH_LIST_METHOD_CONTRACTS_TOOL,
    MATH_PACKAGE_METHOD_ARTIFACT_TOOL,
    MATH_REGISTER_METHOD_IMPLEMENTATION_TOOL,
    MATH_RUN_INDICATOR_FIXTURES_TOOL,
    MCP_CONFIG_TOOL,
    REGISTERED_TOOL_NAMES,
)
from trader_mcp.catalogue.policy import load_local_environment
from trader_mcp.runtime.server import create_server
from trader_research.foundation.artifacts import InMemoryResearchArtifactStore
from trader_research.knowledge.embeddings import DeterministicEmbeddingProvider
from trader_research.knowledge.store import JsonKnowledgeStore


def test_mcp_quant_methods_registration_and_maintained_implementation_flow(
    tmp_path: Path,
) -> None:
    """Carry one maintained method through registration, fixtures, diagnostics, and packaging."""
    artifact_root = tmp_path / "artifacts"
    environment = replace(
        load_local_environment("env.template"), artifact_root=artifact_root
    )
    knowledge_store = JsonKnowledgeStore(artifact_root)
    artifact_store = InMemoryResearchArtifactStore()
    server = create_server(
        environment,
        knowledge_embedding_provider=DeterministicEmbeddingProvider(),
        knowledge_store_provider=lambda: knowledge_store,
        research_artifact_store_provider=lambda: artifact_store,
    )

    async def _run() -> None:
        tools = await server.list_tools()
        config = await server.call_tool(MCP_CONFIG_TOOL, {})
        methods = await server.call_tool(MATH_LIST_METHOD_CONTRACTS_TOOL, {})
        registered = await server.call_tool(
            MATH_REGISTER_METHOD_IMPLEMENTATION_TOOL,
            {
                "method_id": "sma",
                "method_card_ids": [],
                "method_contract": {
                    "method_id": "sma",
                    "parameters": {"period": 3},
                    "no_lookahead": True,
                },
            },
        )
        manifest = registered.structuredContent["data"][
            "method_implementation_manifest"
        ]
        validated = await server.call_tool(
            MATH_RUN_INDICATOR_FIXTURES_TOOL,
            {"implementation_manifest": manifest},
        )
        package = await server.call_tool(
            MATH_PACKAGE_METHOD_ARTIFACT_TOOL,
            {
                "implementation_manifest": validated.structuredContent["data"][
                    "method_implementation_manifest"
                ],
                "validation_report": validated.structuredContent["data"][
                    "indicator_validation_report"
                ],
            },
        )

        tool_names = {tool.name for tool in tools}
        assert tool_names == set(REGISTERED_TOOL_NAMES)
        assert "math_generate_python_method" not in tool_names
        assert KNOWLEDGE_CREATE_METHOD_CARD_DRAFT_TOOL in tool_names
        assert "knowledge_create_rich_method_card_draft" not in tool_names
        metadata = {
            item["name"]: item for item in config.structuredContent["data"]["tools"]
        }
        for tool_name in (
            KNOWLEDGE_REGISTER_SOURCE_TOOL,
            KNOWLEDGE_DISCOVER_METHODOLOGY_CANDIDATES_TOOL,
            KNOWLEDGE_ASSEMBLE_METHODOLOGY_EVIDENCE_TOOL,
            KNOWLEDGE_EXTRACT_METHODOLOGY_FIELDS_TOOL,
            KNOWLEDGE_VALIDATE_METHODOLOGY_CANDIDATE_TOOL,
            KNOWLEDGE_CREATE_METHOD_CARD_DRAFT_TOOL,
            KNOWLEDGE_PUBLISH_METHOD_CARD_TOOL,
            KNOWLEDGE_UPDATE_METHOD_CARD_STATUS_TOOL,
        ):
            assert metadata[tool_name]["agent_owner"] == "Quantitative Methods Agent"
            assert metadata[tool_name]["side_effect"] == "local_mutating"
        assert methods.isError is False
        assert "sma" in {
            item["method_id"] for item in methods.structuredContent["data"]["methods"]
        }
        assert registered.isError is False
        assert manifest["method_card_ids"] == []
        assert validated.isError is False
        assert package.isError is False
        assert (
            package.structuredContent["data"]["method_package_manifest"][
                "method_card_ids"
            ]
            == []
        )

    anyio.run(_run)


def test_mcp_method_card_draft_has_only_validation_backed_contract(
    tmp_path: Path,
) -> None:
    """Build a method-card draft only from validated evidence-backed contract fields."""
    artifact_root = tmp_path / "artifacts"
    environment = replace(
        load_local_environment("env.template"), artifact_root=artifact_root
    )
    server = create_server(
        environment,
        knowledge_store_provider=lambda: JsonKnowledgeStore(artifact_root),
        research_artifact_store_provider=InMemoryResearchArtifactStore,
    )

    async def _run() -> None:
        tool = next(
            item
            for item in await server.list_tools()
            if item.name == KNOWLEDGE_CREATE_METHOD_CARD_DRAFT_TOOL
        )
        schema = tool.inputSchema
        assert "methodology_candidate_validation_id" in schema["properties"]
        assert "assumptions" not in schema["properties"]
        assert "inputs" not in schema["properties"]
        result = await server.call_tool(KNOWLEDGE_CREATE_METHOD_CARD_DRAFT_TOOL, {})
        assert result.isError is True
        assert (
            "exactly one of methodology_candidate_validation_id"
            in result.structuredContent["errors"][0]["message"]
        )

    anyio.run(_run)


def test_mcp_methodology_writes_fail_closed_without_research_artifact_store(
    tmp_path: Path,
) -> None:
    """Fail methodology artifact writes closed without a canonical research store."""
    artifact_root = tmp_path / "artifacts"
    environment = replace(
        load_local_environment("env.template"), artifact_root=artifact_root
    )
    server = create_server(
        environment,
        knowledge_store_provider=lambda: JsonKnowledgeStore(artifact_root),
        research_artifact_store_provider=lambda: None,
    )

    async def _run() -> None:
        discovered = await server.call_tool(
            KNOWLEDGE_DISCOVER_METHODOLOGY_CANDIDATES_TOOL,
            {"query": "pairs trading"},
        )
        drafted = await server.call_tool(
            KNOWLEDGE_CREATE_METHOD_CARD_DRAFT_TOOL,
            {"methodology_candidate_validation_id": "validation_missing"},
        )

        assert discovered.isError is True
        assert (
            discovered.structuredContent["errors"][0]["code"]
            == "research_artifact_store_unavailable"
        )
        assert drafted.isError is True
        assert (
            drafted.structuredContent["errors"][0]["message"]
            == "research artifact store is required"
        )

    anyio.run(_run)
