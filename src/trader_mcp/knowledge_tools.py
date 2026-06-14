"""MCP registrations for Quantitative Methods knowledge and math tools."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult

from trader_mcp.adapters import envelope_to_mcp_result
from trader_mcp.constants import (
    KNOWLEDGE_GET_EVIDENCE_CHUNKS_TOOL,
    KNOWLEDGE_GET_INGESTION_STATUS_TOOL,
    KNOWLEDGE_INGEST_DOCUMENTS_TOOL,
    KNOWLEDGE_LIST_SOURCES_TOOL,
    KNOWLEDGE_REGISTER_SOURCE_TOOL,
    KNOWLEDGE_RETRIEVE_EVIDENCE_TOOL,
    KNOWLEDGE_SEARCH_METHODS_TOOL,
    KNOWLEDGE_TOOL_DESCRIPTIONS,
    KNOWLEDGE_VALIDATE_CITATIONS_TOOL,
    MATH_LIST_METHOD_CONTRACTS_TOOL,
    MATH_TOOL_DESCRIPTIONS,
    MATH_VALIDATE_METHOD_CONTRACT_TOOL,
)
from trader_mcp.environment import McpEnvironment
from trader_research.knowledge.citation_validation import validate_citations as validate_citations_service
from trader_research.knowledge.domain import DEFAULT_SOURCE_TYPE
from trader_research.knowledge.embeddings import EmbeddingProvider, RuntimeConfiguredEmbeddingProvider
from trader_research.knowledge.store import KnowledgeStore
from trader_research.knowledge.ingestion import (
    get_ingestion_status as get_ingestion_status_service,
    ingest_documents as ingest_documents_service,
)
from trader_research.knowledge.retrieval import (
    get_evidence_chunks as get_evidence_chunks_service,
    retrieve_evidence as retrieve_evidence_service,
    search_methods as search_methods_service,
)
from trader_research.knowledge.sources import list_sources as list_sources_service
from trader_research.knowledge.sources import register_source as register_source_service
from trader_research.math_tools import (
    math_list_method_contracts as list_method_contracts_service,
    math_validate_method_contract as validate_method_contract_service,
)


def register_quant_methods_tools(
    server: FastMCP,
    environment: McpEnvironment,
    *,
    embedding_provider: EmbeddingProvider | None = None,
    knowledge_store_provider: Any | None = None,
) -> None:
    """Register Slice 5 Quantitative Methods tools on an MCP server."""
    resolved_embedding_provider = embedding_provider or RuntimeConfiguredEmbeddingProvider(env=environment.embeddings_env())

    def _knowledge_store() -> KnowledgeStore | None:
        return knowledge_store_provider() if knowledge_store_provider is not None else None

    @server.tool(
        name=KNOWLEDGE_REGISTER_SOURCE_TOOL,
        description=KNOWLEDGE_TOOL_DESCRIPTIONS[KNOWLEDGE_REGISTER_SOURCE_TOOL],
    )
    def knowledge_register_source(
        path: str,
        title: str,
        source_type: str = DEFAULT_SOURCE_TYPE,
        canonical_citation: str | None = None,
        topics: list[str] | None = None,
        method_families: list[str] | None = None,
        access_policy: str = "local_curated",
    ) -> CallToolResult:
        envelope = register_source_service(
            artifact_root=environment.artifact_root,
            path=path,
            title=title,
            source_type=source_type,
            canonical_citation=canonical_citation,
            topics=topics,
            method_families=method_families,
            access_policy=access_policy,
            knowledge_store=_knowledge_store(),
        )
        return CallToolResult(**envelope_to_mcp_result(envelope))

    @server.tool(
        name=KNOWLEDGE_INGEST_DOCUMENTS_TOOL,
        description=KNOWLEDGE_TOOL_DESCRIPTIONS[KNOWLEDGE_INGEST_DOCUMENTS_TOOL],
    )
    def knowledge_ingest_documents(source_ids: list[str], force: bool = False) -> CallToolResult:
        envelope = ingest_documents_service(
            artifact_root=environment.artifact_root,
            source_ids=source_ids,
            embedding_provider=resolved_embedding_provider,
            force=force,
            knowledge_store=_knowledge_store(),
        )
        return CallToolResult(**envelope_to_mcp_result(envelope))

    @server.tool(
        name=KNOWLEDGE_GET_INGESTION_STATUS_TOOL,
        description=KNOWLEDGE_TOOL_DESCRIPTIONS[KNOWLEDGE_GET_INGESTION_STATUS_TOOL],
    )
    def knowledge_get_ingestion_status(
        source_ids: list[str] | None = None,
        run_id: str | None = None,
    ) -> CallToolResult:
        envelope = get_ingestion_status_service(
            artifact_root=environment.artifact_root,
            source_ids=source_ids,
            run_id=run_id,
            knowledge_store=_knowledge_store(),
        )
        return CallToolResult(**envelope_to_mcp_result(envelope))

    @server.tool(
        name=KNOWLEDGE_LIST_SOURCES_TOOL,
        description=KNOWLEDGE_TOOL_DESCRIPTIONS[KNOWLEDGE_LIST_SOURCES_TOOL],
    )
    def knowledge_list_sources(
        topic: str | None = None,
        method_family: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> CallToolResult:
        envelope = list_sources_service(
            artifact_root=environment.artifact_root,
            topic=topic,
            method_family=method_family,
            status=status,
            limit=limit,
            knowledge_store=_knowledge_store(),
        )
        return CallToolResult(**envelope_to_mcp_result(envelope))

    @server.tool(
        name=KNOWLEDGE_SEARCH_METHODS_TOOL,
        description=KNOWLEDGE_TOOL_DESCRIPTIONS[KNOWLEDGE_SEARCH_METHODS_TOOL],
    )
    def knowledge_search_methods(
        query: str = "",
        family: str | None = None,
        include_drafts: bool = False,
        limit: int = 10,
    ) -> CallToolResult:
        envelope = search_methods_service(
            artifact_root=environment.artifact_root,
            query=query,
            family=family,
            include_drafts=include_drafts,
            limit=limit,
        )
        return CallToolResult(**envelope_to_mcp_result(envelope))

    @server.tool(
        name=KNOWLEDGE_RETRIEVE_EVIDENCE_TOOL,
        description=KNOWLEDGE_TOOL_DESCRIPTIONS[KNOWLEDGE_RETRIEVE_EVIDENCE_TOOL],
    )
    def knowledge_retrieve_evidence(
        query: str,
        method_id: str | None = None,
        source_ids: list[str] | None = None,
        top_k: int = 5,
        approved_only: bool = True,
    ) -> CallToolResult:
        envelope = retrieve_evidence_service(
            artifact_root=environment.artifact_root,
            query=query,
            method_id=method_id,
            source_ids=source_ids,
            embedding_provider=resolved_embedding_provider,
            top_k=top_k,
            approved_only=approved_only,
            knowledge_store=_knowledge_store(),
        )
        return CallToolResult(**envelope_to_mcp_result(envelope))

    @server.tool(
        name=KNOWLEDGE_GET_EVIDENCE_CHUNKS_TOOL,
        description=KNOWLEDGE_TOOL_DESCRIPTIONS[KNOWLEDGE_GET_EVIDENCE_CHUNKS_TOOL],
    )
    def knowledge_get_evidence_chunks(
        chunk_ids: list[str],
        source_id: str | None = None,
        include_text: bool = True,
        max_chars_per_chunk: int = 4000,
    ) -> CallToolResult:
        envelope = get_evidence_chunks_service(
            artifact_root=environment.artifact_root,
            chunk_ids=chunk_ids,
            source_id=source_id,
            include_text=include_text,
            max_chars_per_chunk=max_chars_per_chunk,
            knowledge_store=_knowledge_store(),
        )
        return CallToolResult(**envelope_to_mcp_result(envelope))

    @server.tool(
        name=KNOWLEDGE_VALIDATE_CITATIONS_TOOL,
        description=KNOWLEDGE_TOOL_DESCRIPTIONS[KNOWLEDGE_VALIDATE_CITATIONS_TOOL],
    )
    def knowledge_validate_citations(
        artifact: dict[str, Any],
        require_approved_method_card: bool = True,
    ) -> CallToolResult:
        envelope = validate_citations_service(
            artifact_root=environment.artifact_root,
            artifact=artifact,
            require_approved_method_card=require_approved_method_card,
            knowledge_store=_knowledge_store(),
        )
        return CallToolResult(**envelope_to_mcp_result(envelope))

    @server.tool(
        name=MATH_LIST_METHOD_CONTRACTS_TOOL,
        description=MATH_TOOL_DESCRIPTIONS[MATH_LIST_METHOD_CONTRACTS_TOOL],
    )
    def math_list_method_contracts(
        family: str | None = None,
        status: str | None = None,
        include_planned: bool = True,
        limit: int = 50,
    ) -> CallToolResult:
        envelope = list_method_contracts_service(
            family=family,
            status=status,
            include_planned=include_planned,
            limit=limit,
        )
        return CallToolResult(**envelope_to_mcp_result(envelope))

    @server.tool(
        name=MATH_VALIDATE_METHOD_CONTRACT_TOOL,
        description=MATH_TOOL_DESCRIPTIONS[MATH_VALIDATE_METHOD_CONTRACT_TOOL],
    )
    def math_validate_method_contract(
        method_contract: dict[str, Any],
        require_evidence: bool = True,
    ) -> CallToolResult:
        envelope = validate_method_contract_service(
            artifact_root=environment.artifact_root,
            method_contract=method_contract,
            require_evidence=require_evidence,
        )
        return CallToolResult(**envelope_to_mcp_result(envelope))
