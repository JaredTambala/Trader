"""MCP registrations for Quantitative Methods knowledge and math tools."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult

from trader_mcp.adapters import envelope_to_mcp_result
from trader_mcp.constants import (
    KNOWLEDGE_CREATE_METHOD_CARD_DRAFT_TOOL,
    KNOWLEDGE_GET_EVIDENCE_CHUNKS_TOOL,
    KNOWLEDGE_GET_INGESTION_STATUS_TOOL,
    KNOWLEDGE_INGEST_DOCUMENTS_TOOL,
    KNOWLEDGE_LIST_SOURCES_TOOL,
    KNOWLEDGE_PUBLISH_METHOD_CARD_TOOL,
    KNOWLEDGE_REGISTER_SOURCE_TOOL,
    KNOWLEDGE_RETRIEVE_EVIDENCE_TOOL,
    KNOWLEDGE_SEARCH_METHODS_TOOL,
    KNOWLEDGE_TOOL_DESCRIPTIONS,
    KNOWLEDGE_VALIDATE_CITATIONS_TOOL,
    MATH_COMPILE_KERNEL_TOOL,
    MATH_GENERATE_CPP_KERNEL_TOOL,
    MATH_GENERATE_PYTHON_METHOD_TOOL,
    MATH_LIST_METHOD_CONTRACTS_TOOL,
    MATH_PACKAGE_METHOD_ARTIFACT_TOOL,
    MATH_REGISTER_METHOD_IMPLEMENTATION_TOOL,
    MATH_RUN_INDICATOR_FIXTURES_TOOL,
    MATH_RUN_MULTIPLE_TESTING_REPORT_TOOL,
    MATH_RUN_SIGNAL_DIAGNOSTICS_TOOL,
    MATH_RUN_SIGNAL_FIXTURES_TOOL,
    MATH_TOOL_DESCRIPTIONS,
    MATH_VALIDATE_METHOD_CONTRACT_TOOL,
)
from trader_mcp.environment import McpEnvironment
from trader_agents.llm_client import LlmJsonRequest, LlmMessage, RuntimeConfiguredLlmClient
from trader_research.knowledge.citation_validation import validate_citations as validate_citations_service
from trader_research.knowledge.domain import DEFAULT_SOURCE_TYPE
from trader_research.knowledge.embeddings import EmbeddingProvider, RuntimeConfiguredEmbeddingProvider
from trader_research.knowledge.store import KnowledgeStore
from trader_research.knowledge.ingestion import (
    get_ingestion_status as get_ingestion_status_service,
    ingest_documents as ingest_documents_service,
)
from trader_research.knowledge.method_cards import (
    create_method_card_draft as create_method_card_draft_service,
    publish_method_card as publish_method_card_service,
)
from trader_research.knowledge.retrieval import (
    get_evidence_chunks as get_evidence_chunks_service,
    retrieve_evidence as retrieve_evidence_service,
    search_methods as search_methods_service,
)
from trader_research.knowledge.sources import list_sources as list_sources_service
from trader_research.knowledge.sources import register_source as register_source_service
from trader_research.methods import (
    math_compile_kernel as compile_kernel_service,
    math_generate_cpp_kernel as generate_cpp_kernel_service,
    math_generate_python_method as generate_python_method_service,
    math_list_method_contracts as list_method_contracts_service,
    math_package_method_artifact as package_method_artifact_service,
    math_register_method_implementation as register_method_implementation_service,
    math_run_indicator_fixtures as run_indicator_fixtures_service,
    math_run_multiple_testing_report as run_multiple_testing_report_service,
    math_run_signal_diagnostics as run_signal_diagnostics_service,
    math_run_signal_fixtures as run_signal_fixtures_service,
    math_validate_method_contract as validate_method_contract_service,
)
from trader_research.method_implementations import generation_messages, generation_response_schema


def register_quant_methods_tools(
    server: FastMCP,
    environment: McpEnvironment,
    *,
    embedding_provider: EmbeddingProvider | None = None,
    knowledge_store_provider: Any | None = None,
    method_generation_llm_client: Any | None = None,
) -> None:
    """Register Slice 5 Quantitative Methods tools on an MCP server."""
    resolved_embedding_provider = embedding_provider or RuntimeConfiguredEmbeddingProvider(env=environment.embeddings_env())
    resolved_method_generation_llm_client = method_generation_llm_client or RuntimeConfiguredLlmClient()

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
            knowledge_store=_knowledge_store(),
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
        name=KNOWLEDGE_CREATE_METHOD_CARD_DRAFT_TOOL,
        description=KNOWLEDGE_TOOL_DESCRIPTIONS[KNOWLEDGE_CREATE_METHOD_CARD_DRAFT_TOOL],
    )
    def knowledge_create_method_card_draft(
        method_id: str,
        title: str,
        family: str,
        assumptions: list[str],
        inputs: list[str],
        outputs: list[str],
        failure_modes: list[str],
        evidence_refs: list[dict[str, Any]],
        version: int = 1,
    ) -> CallToolResult:
        envelope = create_method_card_draft_service(
            artifact_root=environment.artifact_root,
            method_id=method_id,
            title=title,
            family=family,
            assumptions=assumptions,
            inputs=inputs,
            outputs=outputs,
            failure_modes=failure_modes,
            evidence_refs=evidence_refs,
            version=version,
            knowledge_store=_knowledge_store(),
        )
        return CallToolResult(**envelope_to_mcp_result(envelope))

    @server.tool(
        name=KNOWLEDGE_PUBLISH_METHOD_CARD_TOOL,
        description=KNOWLEDGE_TOOL_DESCRIPTIONS[KNOWLEDGE_PUBLISH_METHOD_CARD_TOOL],
    )
    def knowledge_publish_method_card(
        draft_method_card_id: str,
        approved_method_card_id: str,
        approved_by: str,
        approval_note: str,
        approve: bool = False,
    ) -> CallToolResult:
        envelope = publish_method_card_service(
            artifact_root=environment.artifact_root,
            draft_method_card_id=draft_method_card_id,
            approved_method_card_id=approved_method_card_id,
            approved_by=approved_by,
            approval_note=approval_note,
            approve=approve,
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
            knowledge_store=_knowledge_store(),
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
            knowledge_store=_knowledge_store(),
        )
        return CallToolResult(**envelope_to_mcp_result(envelope))

    @server.tool(
        name=MATH_REGISTER_METHOD_IMPLEMENTATION_TOOL,
        description=MATH_TOOL_DESCRIPTIONS[MATH_REGISTER_METHOD_IMPLEMENTATION_TOOL],
    )
    def math_register_method_implementation(
        method_id: str,
        method_card_ids: list[str],
        method_contract: dict[str, Any] | None = None,
        entrypoint: str | None = None,
        source_path: str | None = None,
        class_name: str | None = None,
        constructor_kwargs: dict[str, Any] | None = None,
        implementation_kind: str = "maintained",
        dependency_allowlist: list[str] | None = None,
        expected_source_hash: str | None = None,
    ) -> CallToolResult:
        envelope = register_method_implementation_service(
            artifact_root=environment.artifact_root,
            method_id=method_id,
            method_card_ids=method_card_ids,
            method_contract=method_contract,
            entrypoint=entrypoint,
            source_path=source_path,
            class_name=class_name,
            constructor_kwargs=constructor_kwargs,
            implementation_kind=implementation_kind,
            dependency_allowlist=dependency_allowlist,
            expected_source_hash=expected_source_hash,
            knowledge_store=_knowledge_store(),
        )
        return CallToolResult(**envelope_to_mcp_result(envelope))

    @server.tool(
        name=MATH_RUN_INDICATOR_FIXTURES_TOOL,
        description=MATH_TOOL_DESCRIPTIONS[MATH_RUN_INDICATOR_FIXTURES_TOOL],
    )
    def math_run_indicator_fixtures(
        implementation_id: str | None = None,
        implementation_manifest: dict[str, Any] | None = None,
        fixtures: list[dict[str, Any]] | None = None,
    ) -> CallToolResult:
        envelope = run_indicator_fixtures_service(
            artifact_root=environment.artifact_root,
            implementation_id=implementation_id,
            implementation_manifest=implementation_manifest,
            fixtures=fixtures,
            knowledge_store=_knowledge_store(),
        )
        return CallToolResult(**envelope_to_mcp_result(envelope))

    @server.tool(
        name=MATH_RUN_SIGNAL_FIXTURES_TOOL,
        description=MATH_TOOL_DESCRIPTIONS[MATH_RUN_SIGNAL_FIXTURES_TOOL],
    )
    def math_run_signal_fixtures(
        implementation_id: str | None = None,
        implementation_manifest: dict[str, Any] | None = None,
        fixtures: list[dict[str, Any]] | None = None,
    ) -> CallToolResult:
        envelope = run_signal_fixtures_service(
            artifact_root=environment.artifact_root,
            implementation_id=implementation_id,
            implementation_manifest=implementation_manifest,
            fixtures=fixtures,
            knowledge_store=_knowledge_store(),
        )
        return CallToolResult(**envelope_to_mcp_result(envelope))

    @server.tool(
        name=MATH_GENERATE_PYTHON_METHOD_TOOL,
        description=MATH_TOOL_DESCRIPTIONS[MATH_GENERATE_PYTHON_METHOD_TOOL],
    )
    async def math_generate_python_method(
        method_id: str,
        method_card_ids: list[str],
        method_contract: dict[str, Any],
        fixtures: list[dict[str, Any]] | None = None,
    ) -> CallToolResult:
        llm_request = LlmJsonRequest(
            messages=tuple(
                LlmMessage(**message)
                for message in generation_messages(method_id, method_contract, method_card_ids)
            ),
            response_schema=generation_response_schema(),
            max_tokens=1800,
        )
        llm_payload = await resolved_method_generation_llm_client.complete_json(llm_request)
        envelope = generate_python_method_service(
            artifact_root=environment.artifact_root,
            method_id=method_id,
            method_card_ids=method_card_ids,
            method_contract=method_contract,
            llm_payload=llm_payload,
            fixtures=fixtures,
            knowledge_store=_knowledge_store(),
        )
        return CallToolResult(**envelope_to_mcp_result(envelope))

    @server.tool(
        name=MATH_RUN_SIGNAL_DIAGNOSTICS_TOOL,
        description=MATH_TOOL_DESCRIPTIONS[MATH_RUN_SIGNAL_DIAGNOSTICS_TOOL],
    )
    def math_run_signal_diagnostics(
        signal_observations: list[dict[str, Any]],
        forward_return_labels: list[dict[str, Any]],
        candidate_family_manifest: dict[str, Any],
        method_contracts: list[dict[str, Any]],
        quantile_count: int = 5,
        data_quality_report: dict[str, Any] | None = None,
    ) -> CallToolResult:
        envelope = run_signal_diagnostics_service(
            artifact_root=environment.artifact_root,
            signal_observations=signal_observations,
            forward_return_labels=forward_return_labels,
            candidate_family_manifest=candidate_family_manifest,
            method_contracts=method_contracts,
            quantile_count=quantile_count,
            data_quality_report=data_quality_report,
            knowledge_store=_knowledge_store(),
        )
        return CallToolResult(**envelope_to_mcp_result(envelope))

    @server.tool(
        name=MATH_RUN_MULTIPLE_TESTING_REPORT_TOOL,
        description=MATH_TOOL_DESCRIPTIONS[MATH_RUN_MULTIPLE_TESTING_REPORT_TOOL],
    )
    def math_run_multiple_testing_report(
        candidate_family_manifest: dict[str, Any],
        metric_matrix: list[dict[str, Any]],
        method_contract: dict[str, Any],
        alpha: float | None = None,
    ) -> CallToolResult:
        envelope = run_multiple_testing_report_service(
            artifact_root=environment.artifact_root,
            candidate_family_manifest=candidate_family_manifest,
            metric_matrix=metric_matrix,
            method_contract=method_contract,
            alpha=alpha,
            knowledge_store=_knowledge_store(),
        )
        return CallToolResult(**envelope_to_mcp_result(envelope))

    @server.tool(
        name=MATH_GENERATE_CPP_KERNEL_TOOL,
        description=MATH_TOOL_DESCRIPTIONS[MATH_GENERATE_CPP_KERNEL_TOOL],
    )
    def math_generate_cpp_kernel(
        implementation_id: str | None = None,
        implementation_manifest: dict[str, Any] | None = None,
        template_id: str | None = None,
    ) -> CallToolResult:
        envelope = generate_cpp_kernel_service(
            artifact_root=environment.artifact_root,
            implementation_id=implementation_id,
            implementation_manifest=implementation_manifest,
            template_id=template_id,
        )
        return CallToolResult(**envelope_to_mcp_result(envelope))

    @server.tool(
        name=MATH_COMPILE_KERNEL_TOOL,
        description=MATH_TOOL_DESCRIPTIONS[MATH_COMPILE_KERNEL_TOOL],
    )
    def math_compile_kernel(
        kernel_id: str | None = None,
        kernel_manifest: dict[str, Any] | None = None,
        compiler: str | None = None,
        timeout_seconds: float = 30.0,
    ) -> CallToolResult:
        envelope = compile_kernel_service(
            artifact_root=environment.artifact_root,
            kernel_id=kernel_id,
            kernel_manifest=kernel_manifest,
            compiler=compiler,
            timeout_seconds=timeout_seconds,
        )
        return CallToolResult(**envelope_to_mcp_result(envelope))

    @server.tool(
        name=MATH_PACKAGE_METHOD_ARTIFACT_TOOL,
        description=MATH_TOOL_DESCRIPTIONS[MATH_PACKAGE_METHOD_ARTIFACT_TOOL],
    )
    def math_package_method_artifact(
        implementation_id: str | None = None,
        implementation_manifest: dict[str, Any] | None = None,
        validation_report_id: str | None = None,
        validation_report: dict[str, Any] | None = None,
        cxx_kernel_id: str | None = None,
        cxx_kernel_manifest: dict[str, Any] | None = None,
    ) -> CallToolResult:
        envelope = package_method_artifact_service(
            artifact_root=environment.artifact_root,
            implementation_id=implementation_id,
            implementation_manifest=implementation_manifest,
            validation_report_id=validation_report_id,
            validation_report=validation_report,
            cxx_kernel_id=cxx_kernel_id,
            cxx_kernel_manifest=cxx_kernel_manifest,
        )
        return CallToolResult(**envelope_to_mcp_result(envelope))
