"""Stdio MCP server skeleton for research tools."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any, TypedDict

from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult

from trader_mcp.protocol.adapters import result_to_mcp_result
from trader_mcp.tools.adversarial import register_adversarial_tools
from trader_mcp.tools.coordination import register_agentic_tools
from trader_mcp.tools.coding import register_coding_tools
from trader_mcp.catalogue.definitions import (
    AGENTIC_TOOL_DESCRIPTIONS,
    AGENTIC_TOOL_NAMES,
    ADVERSARIAL_TOOL_DESCRIPTIONS,
    ADVERSARIAL_TOOL_NAMES,
    CAPABILITY_REGISTRATION_FLAGS,
    CODING_TOOL_DESCRIPTIONS,
    CODING_TOOL_NAMES,
    DATA_DISCOVER_SYMBOLS_TOOL,
    DATA_CREATE_RESEARCH_SNAPSHOT_TOOL,
    DATA_ENSURE_LOADED_TOOL,
    DATA_GET_INVENTORY_TOOL,
    DATA_SUMMARIZE_QUALITY_TOOL,
    DATA_TOOL_DESCRIPTIONS,
    EVALUATION_TOOL_DESCRIPTIONS,
    EVALUATION_TOOL_NAMES,
    EXPERIMENT_DESIGN_TOOL_DESCRIPTIONS,
    EXPERIMENT_DESIGN_TOOL_NAMES,
    KNOWLEDGE_ASSEMBLE_METHODOLOGY_EVIDENCE_TOOL,
    KNOWLEDGE_CREATE_METHOD_CARD_DRAFT_TOOL,
    KNOWLEDGE_DISCOVER_METHODOLOGY_CANDIDATES_TOOL,
    KNOWLEDGE_EXTRACT_METHODOLOGY_FIELDS_TOOL,
    KNOWLEDGE_INGEST_DOCUMENTS_TOOL,
    MCP_CONFIG_TOOL,
    MCP_HEALTH_TOOL,
    MCP_SERVER_OWNER,
    KNOWLEDGE_PUBLISH_METHOD_CARD_TOOL,
    KNOWLEDGE_REGISTER_SOURCE_TOOL,
    KNOWLEDGE_TOOL_DESCRIPTIONS,
    KNOWLEDGE_TOOL_NAMES,
    KNOWLEDGE_UPDATE_METHOD_CARD_STATUS_TOOL,
    KNOWLEDGE_VALIDATE_METHODOLOGY_CANDIDATE_TOOL,
    MATH_COMPILE_KERNEL_TOOL,
    MATH_GENERATE_CPP_KERNEL_TOOL,
    MATH_PACKAGE_METHOD_ARTIFACT_TOOL,
    MATH_REGISTER_METHOD_IMPLEMENTATION_TOOL,
    MATH_RUN_INDICATOR_FIXTURES_TOOL,
    MATH_RUN_MULTIPLE_TESTING_REPORT_TOOL,
    MATH_RUN_SIGNAL_DIAGNOSTICS_TOOL,
    MATH_RUN_SIGNAL_FIXTURES_TOOL,
    MATH_TOOL_DESCRIPTIONS,
    MATH_TOOL_NAMES,
    ML_TOOL_DESCRIPTIONS,
    ML_TOOL_NAMES,
    REGISTERED_TOOL_NAMES,
    RESEARCH_REGISTER_OPTIMIZATION_OBJECTIVE_TOOL,
    RESEARCH_VALIDATE_OPTIMIZATION_OBJECTIVE_TOOL,
    RESEARCH_TOOL_DESCRIPTIONS,
    RESEARCH_TOOL_NAMES,
    SERVER_NAME,
    SUPPORT_TOOL_DESCRIPTIONS,
)
from trader_mcp.observability.console import McpConsoleLogger, mcp_console_config
from trader_mcp.runtime.composition import (
    CodingWorkspaceServiceProvider,
    EventStoreProvider,
    KnowledgeStoreProvider,
    OptimizationTrialExecutorFactory,
    ResearchArtifactStoreProvider,
    SymbolDiscoveryPolicyProvider,
    ToolConfigProvider,
    ToolRuntimeConfigurationError,
    compose_runtime_dependencies,
    load_tool_config,
)
from trader_mcp.catalogue.policy import McpEnvironment, load_local_environment
from trader_mcp.tools.evaluation import register_evaluation_tools
from trader_mcp.tools.methodology import register_quant_methods_tools
from trader_mcp.tools.ml import register_ml_tools
from trader_mcp.tools.experiment_design import register_orchestration_tools
from trader_mcp.tools.experiments import (
    ImplementationValidationService,
    register_research_tools,
)
from trader_research.governance import agent_owner_for_tool
from trader_research.foundation import (
    ContextualResearchArtifactStore,
    PredictionMapperCatalog,
)
from trader_mcp.protocol.contracts import (
    SCHEMA_VERSION,
    SideEffect,
    ToolEnvelope,
    error_envelope,
    result_to_envelope,
    side_effect_for_operation,
    success_envelope,
)
from trader_research.data import (
    DataEnsureLoadedPolicy,
    DataEnsureLoadedRequest,
    DataInventoryRequest,
    DataQualityRequest,
    DataSymbolDiscoveryPolicy,
    DataSymbolDiscoveryRequest,
    create_data_research_snapshot,
    data_ensure_loaded as ensure_loaded_service,
    data_discover_symbols as discover_symbols_service,
    data_summarize_quality as summarize_quality_service,
    get_data_inventory,
)
from trader_research.knowledge import (
    EmbeddingProvider,
    embedding_runtime_summary,
)
from trader_research.experiments import (
    ExperimentTrackingSinkRegistry,
    OptimizationEngineRegistry,
)
from trader_research.ml import (
    ArtifactPredictionDeploymentReader,
    ArtifactPredictionRuntimeResolver,
    InferenceAdapterRegistry,
)


class _ConfiguredMarketDataContext(TypedDict):
    """Typed config values copied into bounded Data Agent requests."""

    configured_provider: str | None
    configured_asset_class: str | None
    configured_symbols: tuple[str, ...]
    configured_universe_available: bool


def create_server(
    environment: McpEnvironment | None = None,
    event_store_provider: EventStoreProvider | None = None,
    data_loading_policy: DataEnsureLoadedPolicy | None = None,
    symbol_discovery_policy: DataSymbolDiscoveryPolicy | None = None,
    knowledge_embedding_provider: EmbeddingProvider | None = None,
    knowledge_store_provider: KnowledgeStoreProvider | None = None,
    research_artifact_store_provider: ResearchArtifactStoreProvider | None = None,
    backtest_config_provider: ToolConfigProvider | None = None,
    optimizer_registry: OptimizationEngineRegistry | None = None,
    tracking_sink_registry: ExperimentTrackingSinkRegistry | None = None,
    inference_adapter_registry: InferenceAdapterRegistry | None = None,
    prediction_mapper_catalog: PredictionMapperCatalog | None = None,
    coding_workspace_service_provider: CodingWorkspaceServiceProvider | None = None,
    optimization_trial_executor_factory: OptimizationTrialExecutorFactory | None = None,
    strategy_validation_service: ImplementationValidationService | None = None,
) -> FastMCP:
    """Create the MCP server and register the configured bounded tool catalog.

    Args:
        environment: Optional resolved local MCP environment.
        event_store_provider: Optional provider for read-only event-store queries.
        data_loading_policy: Optional explicit data-loading policy for tests or
            controlled embedding.
        coding_workspace_service_provider: Optional isolated Coding Workspace
            service provider for Strategy Engineering tools.
        optimization_trial_executor_factory: Optional controlled factory for
            backtest-backed optimization trial execution.
        strategy_validation_service: Optional deterministic Strategy admission
            service. Omit this outside controlled composition to use the
            maintained production validator.

    Returns:
        Configured FastMCP server instance.
    """
    local_env = environment or load_local_environment()
    runtime = compose_runtime_dependencies(
        local_env,
        event_store_provider=event_store_provider,
        data_loading_policy=data_loading_policy,
        symbol_discovery_policy=symbol_discovery_policy,
        knowledge_store_provider=knowledge_store_provider,
        research_artifact_store_provider=research_artifact_store_provider,
        backtest_config_provider=backtest_config_provider,
        optimizer_registry=optimizer_registry,
        tracking_sink_registry=tracking_sink_registry,
        inference_adapter_registry=inference_adapter_registry,
        prediction_mapper_catalog=prediction_mapper_catalog,
        coding_workspace_service_provider=coding_workspace_service_provider,
        optimization_trial_executor_factory=optimization_trial_executor_factory,
    )
    data_event_store_provider = runtime.event_store_provider
    resolved_backtest_config_provider = runtime.backtest_config_provider
    resolved_knowledge_store_provider = runtime.knowledge_store_provider
    resolved_research_artifact_store_provider = runtime.research_artifact_store_provider
    resolved_optimizer_registry = runtime.optimizer_registry
    resolved_tracking_sink_registry = runtime.tracking_sink_registry
    resolved_inference_adapter_registry = runtime.inference_adapter_registry
    resolved_prediction_mapper_catalog = runtime.prediction_mapper_catalog
    resolved_coding_workspace_service_provider = (
        runtime.coding_workspace_service_provider
    )

    def _prediction_deployment_reader() -> ArtifactPredictionDeploymentReader:
        return ArtifactPredictionDeploymentReader(
            resolved_research_artifact_store_provider()
        )

    def _prediction_runtime_resolver() -> ArtifactPredictionRuntimeResolver:
        return ArtifactPredictionRuntimeResolver(
            artifact_store=resolved_research_artifact_store_provider(),
            adapter_registry=resolved_inference_adapter_registry,
            mapper_catalog=resolved_prediction_mapper_catalog,
        )

    resolved_data_loading_policy = runtime.data_loading_policy
    resolved_symbol_discovery_policy_provider = runtime.symbol_discovery_policy_provider
    server = FastMCP(SERVER_NAME)

    @server.tool(
        name=MCP_HEALTH_TOOL, description=SUPPORT_TOOL_DESCRIPTIONS[MCP_HEALTH_TOOL]
    )
    def mcp_health() -> CallToolResult:
        """Return read-only MCP server health.

        Returns:
            MCP call result containing a read-only health envelope.
        """
        return CallToolResult(**result_to_mcp_result(build_health_envelope(local_env)))

    @server.tool(
        name=MCP_CONFIG_TOOL, description=SUPPORT_TOOL_DESCRIPTIONS[MCP_CONFIG_TOOL]
    )
    def mcp_get_config() -> CallToolResult:
        """Return read-only MCP server configuration.

        Returns:
            MCP call result containing a read-only configuration envelope.
        """
        return CallToolResult(
            **result_to_mcp_result(
                build_config_envelope(
                    local_env,
                    knowledge_store_provider_configured=knowledge_store_provider
                    is not None,
                    research_artifact_store_provider_configured=research_artifact_store_provider
                    is not None,
                )
            )
        )

    @server.tool(
        name=DATA_DISCOVER_SYMBOLS_TOOL,
        description=DATA_TOOL_DESCRIPTIONS[DATA_DISCOVER_SYMBOLS_TOOL],
    )
    def data_discover_symbols(
        symbols: list[str] | None = None,
        asset_class: str | None = None,
        instrument_type: str | None = None,
        bar_type: str | None = None,
        query: str | None = None,
        source: str = "local",
        provider: str | None = None,
        timeframe: str | None = None,
        source_filter: str | None = None,
        limit: int = 50,
        active_only: bool = True,
        tradable_only: bool = True,
        include_local_coverage: bool = False,
    ) -> CallToolResult:
        """Return a read-only Data Agent symbol discovery envelope."""
        envelope = build_data_symbol_discovery_envelope(
            event_store_provider=data_event_store_provider,
            environment=local_env,
            symbols=symbols,
            asset_class=asset_class,
            instrument_type=instrument_type,
            bar_type=bar_type,
            query=query,
            source=source,
            provider=provider,
            timeframe=timeframe,
            source_filter=source_filter,
            limit=limit,
            active_only=active_only,
            tradable_only=tradable_only,
            include_local_coverage=include_local_coverage,
            policy_provider=resolved_symbol_discovery_policy_provider,
        )
        return CallToolResult(**result_to_mcp_result(envelope))

    @server.tool(
        name=DATA_GET_INVENTORY_TOOL,
        description=DATA_TOOL_DESCRIPTIONS[DATA_GET_INVENTORY_TOOL],
    )
    def data_get_inventory(
        symbols: list[str],
        asset_class: str,
        timeframe: str,
        start: str,
        end: str,
        source: str | None = None,
        provider: str | None = None,
        instrument_type: str | None = None,
        bar_type: str | None = None,
    ) -> CallToolResult:
        """Return a read-only Data Agent inventory envelope.

        Args:
            symbols: JSON array of requested symbols.
            asset_class: Requested asset class.
            timeframe: Requested bar timeframe.
            start: Inclusive requested start timestamp as ISO-8601 text.
            end: Inclusive requested end timestamp as ISO-8601 text.
            source: Optional source filter.

        Returns:
            MCP call result containing a Data Agent inventory envelope.
        """
        envelope = build_data_inventory_envelope(
            event_store_provider=data_event_store_provider,
            environment=local_env,
            symbols=symbols,
            asset_class=asset_class,
            timeframe=timeframe,
            start=start,
            end=end,
            source=source,
            provider=provider,
            instrument_type=instrument_type,
            bar_type=bar_type,
        )
        return CallToolResult(**result_to_mcp_result(envelope))

    @server.tool(
        name=DATA_SUMMARIZE_QUALITY_TOOL,
        description=DATA_TOOL_DESCRIPTIONS[DATA_SUMMARIZE_QUALITY_TOOL],
    )
    def data_summarize_quality(
        symbols: list[str],
        asset_class: str,
        timeframe: str,
        start: str,
        end: str,
        source: str | None = None,
        provider: str | None = None,
        instrument_type: str | None = None,
        bar_type: str | None = None,
    ) -> CallToolResult:
        """Return a read-only Data Agent quality envelope.

        Args:
            symbols: JSON array of requested symbols.
            asset_class: Requested asset class.
            timeframe: Requested bar timeframe.
            start: Inclusive requested start timestamp as ISO-8601 text.
            end: Inclusive requested end timestamp as ISO-8601 text.
            source: Optional source filter.

        Returns:
            MCP call result containing a Data Agent quality envelope.
        """
        envelope = build_data_quality_envelope(
            event_store_provider=data_event_store_provider,
            environment=local_env,
            symbols=symbols,
            asset_class=asset_class,
            timeframe=timeframe,
            start=start,
            end=end,
            source=source,
            provider=provider,
            instrument_type=instrument_type,
            bar_type=bar_type,
        )
        return CallToolResult(**result_to_mcp_result(envelope))

    @server.tool(
        name=DATA_CREATE_RESEARCH_SNAPSHOT_TOOL,
        description=DATA_TOOL_DESCRIPTIONS[DATA_CREATE_RESEARCH_SNAPSHOT_TOOL],
    )
    def data_create_research_snapshot(
        symbols: list[str],
        asset_class: str,
        timeframe: str,
        start: str,
        end: str,
        requested_by: str,
        actor: str,
        source: str | None = None,
        provider: str | None = None,
        instrument_type: str | None = None,
        bar_type: str | None = None,
    ) -> CallToolResult:
        """Persist one exact Data-domain inventory and quality snapshot."""
        try:
            inventory_request = _data_inventory_request_from_inputs(
                symbols=symbols,
                asset_class=asset_class,
                timeframe=timeframe,
                start=start,
                end=end,
                source=source,
                provider=provider,
                instrument_type=instrument_type,
                bar_type=bar_type,
                environment=local_env,
            )
            quality_request = _data_quality_request_from_inputs(
                symbols=symbols,
                asset_class=asset_class,
                timeframe=timeframe,
                start=start,
                end=end,
                source=source,
                provider=provider,
                instrument_type=instrument_type,
                bar_type=bar_type,
                environment=local_env,
            )
            store = ContextualResearchArtifactStore(
                resolved_research_artifact_store_provider(),
                requested_by=requested_by,
                actor=actor,
            )
            result = create_data_research_snapshot(
                event_store=data_event_store_provider(),
                inventory_request=inventory_request,
                quality_request=quality_request,
                requested_by=requested_by,
                actor=actor,
                artifact_store=store,
            )
            envelope = result_to_envelope(result)
        except Exception as exc:
            envelope = error_envelope(
                command=DATA_CREATE_RESEARCH_SNAPSHOT_TOOL,
                side_effect=SideEffect.LOCAL_MUTATING,
                code="data_research_snapshot_failed",
                message=str(exc),
            )
        return CallToolResult(**result_to_mcp_result(envelope))

    @server.tool(
        name=DATA_ENSURE_LOADED_TOOL,
        description=DATA_TOOL_DESCRIPTIONS[DATA_ENSURE_LOADED_TOOL],
    )
    def data_ensure_loaded(
        symbols: list[str],
        asset_class: str,
        timeframe: str,
        start: str,
        end: str,
        mode: str,
        source: str | None = None,
        dry_run: bool = True,
        provider: str | None = None,
        instrument_type: str | None = None,
        bar_type: str | None = None,
        acquisition_plan_id: str | None = None,
        operation_id: str | None = None,
        requested_by: str | None = None,
        actor: str | None = None,
    ) -> CallToolResult:
        """Return a Data Agent data inspection/loading envelope.

        Args:
            symbols: JSON array of requested symbols.
            asset_class: Requested asset class.
            timeframe: Requested bar timeframe.
            start: Inclusive requested start timestamp as ISO-8601 text.
            end: Inclusive requested end timestamp as ISO-8601 text.
            mode: Ensure mode: existing, sample, or backfill.
            source: Optional source filter.
            dry_run: Whether backfill mode should plan only.
            acquisition_plan_id: Exact prior dry-run plan for execution.
            operation_id: Trusted orchestration operation identity.
            requested_by: Owning research-session identity.
            actor: Public Data runtime actor.

        Returns:
            MCP call result containing a Data Agent ensure-loaded envelope.
        """
        envelope = build_data_ensure_loaded_envelope(
            event_store_provider=data_event_store_provider,
            environment=local_env,
            symbols=symbols,
            asset_class=asset_class,
            timeframe=timeframe,
            start=start,
            end=end,
            mode=mode,
            source=source,
            dry_run=dry_run,
            provider=provider,
            instrument_type=instrument_type,
            bar_type=bar_type,
            acquisition_plan_id=acquisition_plan_id,
            operation_id=operation_id,
            requested_by=requested_by,
            actor=actor,
            policy=resolved_data_loading_policy,
            artifact_store_provider=resolved_research_artifact_store_provider,
        )
        return CallToolResult(**result_to_mcp_result(envelope))

    register_quant_methods_tools(
        server,
        local_env,
        embedding_provider=knowledge_embedding_provider,
        knowledge_store_provider=resolved_knowledge_store_provider,
        artifact_store_provider=resolved_research_artifact_store_provider,
    )
    register_ml_tools(
        server,
        local_env,
        artifact_store_provider=resolved_research_artifact_store_provider,
        adapter_registry=resolved_inference_adapter_registry,
    )
    register_coding_tools(
        server,
        local_env,
        service_provider=resolved_coding_workspace_service_provider,
    )
    register_agentic_tools(
        server,
        artifact_store_provider=resolved_research_artifact_store_provider,
    )
    register_research_tools(
        server,
        local_env,
        optimization_trial_executor_factory=runtime.optimization_trial_executor_factory,
        event_store_provider=data_event_store_provider,
        backtest_config_provider=resolved_backtest_config_provider,
        artifact_store_provider=resolved_research_artifact_store_provider,
        optimizer_registry=resolved_optimizer_registry,
        tracking_sink_registry=resolved_tracking_sink_registry,
        prediction_deployment_reader_provider=_prediction_deployment_reader,
        prediction_mapper_catalog=resolved_prediction_mapper_catalog,
        prediction_runtime_resolver_provider=_prediction_runtime_resolver,
        coding_workspace_service_provider=resolved_coding_workspace_service_provider,
        strategy_validation_service=strategy_validation_service,
    )
    register_orchestration_tools(
        server,
        artifact_store_provider=resolved_research_artifact_store_provider,
    )
    register_evaluation_tools(
        server,
        local_env,
        artifact_store_provider=resolved_research_artifact_store_provider,
    )
    register_adversarial_tools(
        server, artifact_store_provider=resolved_research_artifact_store_provider
    )

    return server


def build_health_envelope(environment: McpEnvironment | None = None) -> ToolEnvelope:
    """Build the read-only MCP server health envelope.

    Args:
        environment: Optional resolved local MCP environment.

    Returns:
        Successful health envelope owned by the MCP server support boundary.
    """
    local_env = environment or load_local_environment()
    return success_envelope(
        command=MCP_HEALTH_TOOL,
        agent_owner=MCP_SERVER_OWNER,
        side_effect=SideEffect.READ_ONLY,
        data={
            "status": "ok",
            "environment": local_env.environment,
            "server_name": SERVER_NAME,
            "transport": local_env.transport,
            "schema_version": SCHEMA_VERSION,
            "tools": list(REGISTERED_TOOL_NAMES),
        },
    )


def build_config_envelope(
    environment: McpEnvironment | None = None,
    *,
    knowledge_store_provider_configured: bool = False,
    research_artifact_store_provider_configured: bool = False,
) -> ToolEnvelope:
    """Build the read-only MCP server configuration envelope.

    Args:
        environment: Optional resolved local MCP environment.

    Returns:
        Successful configuration envelope owned by the MCP server support boundary.
    """
    local_env = environment or load_local_environment()
    tool_metadata = [
        {
            "name": MCP_HEALTH_TOOL,
            "agent_owner": MCP_SERVER_OWNER,
            "side_effect": SideEffect.READ_ONLY.value,
            "description": SUPPORT_TOOL_DESCRIPTIONS[MCP_HEALTH_TOOL],
        },
        {
            "name": MCP_CONFIG_TOOL,
            "agent_owner": MCP_SERVER_OWNER,
            "side_effect": SideEffect.READ_ONLY.value,
            "description": SUPPORT_TOOL_DESCRIPTIONS[MCP_CONFIG_TOOL],
        },
        {
            "name": DATA_DISCOVER_SYMBOLS_TOOL,
            "agent_owner": agent_owner_for_tool(DATA_DISCOVER_SYMBOLS_TOOL),
            "side_effect": SideEffect.READ_ONLY.value,
            "description": DATA_TOOL_DESCRIPTIONS[DATA_DISCOVER_SYMBOLS_TOOL],
        },
        {
            "name": DATA_GET_INVENTORY_TOOL,
            "agent_owner": agent_owner_for_tool(DATA_GET_INVENTORY_TOOL),
            "side_effect": SideEffect.READ_ONLY.value,
            "description": DATA_TOOL_DESCRIPTIONS[DATA_GET_INVENTORY_TOOL],
        },
        {
            "name": DATA_SUMMARIZE_QUALITY_TOOL,
            "agent_owner": agent_owner_for_tool(DATA_SUMMARIZE_QUALITY_TOOL),
            "side_effect": SideEffect.READ_ONLY.value,
            "description": DATA_TOOL_DESCRIPTIONS[DATA_SUMMARIZE_QUALITY_TOOL],
        },
        {
            "name": DATA_ENSURE_LOADED_TOOL,
            "agent_owner": agent_owner_for_tool(DATA_ENSURE_LOADED_TOOL),
            "side_effect": SideEffect.LOCAL_MUTATING.value,
            "description": DATA_TOOL_DESCRIPTIONS[DATA_ENSURE_LOADED_TOOL],
        },
        {
            "name": DATA_CREATE_RESEARCH_SNAPSHOT_TOOL,
            "agent_owner": agent_owner_for_tool(DATA_CREATE_RESEARCH_SNAPSHOT_TOOL),
            "side_effect": SideEffect.LOCAL_MUTATING.value,
            "description": DATA_TOOL_DESCRIPTIONS[DATA_CREATE_RESEARCH_SNAPSHOT_TOOL],
        },
    ]
    tool_metadata.extend(
        {
            "name": tool_name,
            "agent_owner": agent_owner_for_tool(tool_name),
            "side_effect": side_effect_for_operation(tool_name).value,
            "description": AGENTIC_TOOL_DESCRIPTIONS[tool_name],
        }
        for tool_name in AGENTIC_TOOL_NAMES
    )
    tool_metadata.extend(
        {
            "name": tool_name,
            "agent_owner": agent_owner_for_tool(tool_name),
            "side_effect": side_effect_for_operation(tool_name).value,
            "description": CODING_TOOL_DESCRIPTIONS[tool_name],
        }
        for tool_name in CODING_TOOL_NAMES
    )
    tool_metadata.extend(
        {
            "name": tool_name,
            "agent_owner": agent_owner_for_tool(tool_name),
            "side_effect": SideEffect.LOCAL_MUTATING.value,
            "description": EXPERIMENT_DESIGN_TOOL_DESCRIPTIONS[tool_name],
        }
        for tool_name in EXPERIMENT_DESIGN_TOOL_NAMES
    )
    tool_metadata.extend(
        {
            "name": tool_name,
            "agent_owner": agent_owner_for_tool(tool_name),
            "side_effect": SideEffect.LOCAL_MUTATING.value,
            "description": ML_TOOL_DESCRIPTIONS[tool_name],
        }
        for tool_name in ML_TOOL_NAMES
    )
    tool_metadata.extend(
        {
            "name": tool_name,
            "agent_owner": agent_owner_for_tool(tool_name),
            "side_effect": SideEffect.LOCAL_MUTATING.value
            if tool_name
            in {
                KNOWLEDGE_REGISTER_SOURCE_TOOL,
                KNOWLEDGE_INGEST_DOCUMENTS_TOOL,
                KNOWLEDGE_DISCOVER_METHODOLOGY_CANDIDATES_TOOL,
                KNOWLEDGE_ASSEMBLE_METHODOLOGY_EVIDENCE_TOOL,
                KNOWLEDGE_EXTRACT_METHODOLOGY_FIELDS_TOOL,
                KNOWLEDGE_VALIDATE_METHODOLOGY_CANDIDATE_TOOL,
                KNOWLEDGE_CREATE_METHOD_CARD_DRAFT_TOOL,
                KNOWLEDGE_PUBLISH_METHOD_CARD_TOOL,
                KNOWLEDGE_UPDATE_METHOD_CARD_STATUS_TOOL,
            }
            else SideEffect.READ_ONLY.value,
            "description": KNOWLEDGE_TOOL_DESCRIPTIONS[tool_name],
        }
        for tool_name in KNOWLEDGE_TOOL_NAMES
    )
    tool_metadata.extend(
        {
            "name": tool_name,
            "agent_owner": agent_owner_for_tool(tool_name),
            "side_effect": SideEffect.LOCAL_MUTATING.value
            if tool_name
            in {
                MATH_REGISTER_METHOD_IMPLEMENTATION_TOOL,
                MATH_RUN_INDICATOR_FIXTURES_TOOL,
                MATH_RUN_SIGNAL_FIXTURES_TOOL,
                MATH_RUN_SIGNAL_DIAGNOSTICS_TOOL,
                MATH_RUN_MULTIPLE_TESTING_REPORT_TOOL,
                MATH_GENERATE_CPP_KERNEL_TOOL,
                MATH_COMPILE_KERNEL_TOOL,
                MATH_PACKAGE_METHOD_ARTIFACT_TOOL,
                RESEARCH_REGISTER_OPTIMIZATION_OBJECTIVE_TOOL,
                RESEARCH_VALIDATE_OPTIMIZATION_OBJECTIVE_TOOL,
            }
            else SideEffect.READ_ONLY.value,
            "description": MATH_TOOL_DESCRIPTIONS[tool_name],
        }
        for tool_name in MATH_TOOL_NAMES
    )
    tool_metadata.extend(
        {
            "name": tool_name,
            "agent_owner": agent_owner_for_tool(tool_name),
            "side_effect": side_effect_for_operation(tool_name).value,
            "description": RESEARCH_TOOL_DESCRIPTIONS[tool_name],
        }
        for tool_name in RESEARCH_TOOL_NAMES
    )
    tool_metadata.extend(
        {
            "name": tool_name,
            "agent_owner": agent_owner_for_tool(tool_name),
            "side_effect": SideEffect.LOCAL_MUTATING.value,
            "description": EVALUATION_TOOL_DESCRIPTIONS[tool_name],
        }
        for tool_name in EVALUATION_TOOL_NAMES
    )
    tool_metadata.extend(
        {
            "name": tool_name,
            "agent_owner": agent_owner_for_tool(tool_name),
            "side_effect": SideEffect.LOCAL_MUTATING.value,
            "description": ADVERSARIAL_TOOL_DESCRIPTIONS[tool_name],
        }
        for tool_name in ADVERSARIAL_TOOL_NAMES
    )
    safety = {
        **CAPABILITY_REGISTRATION_FLAGS,
        "symbol_provider_discovery_allowed": local_env.allow_symbol_provider_discovery,
        "data_loading_mutation_allowed": local_env.allow_data_loading,
        "backtest_execution_allowed": local_env.allow_backtests,
        "optimization_execution_allowed": local_env.allow_optimization,
        "optuna_writes_allowed": local_env.allow_optuna_writes,
        "external_research_writes_allowed": local_env.allow_external_research_writes,
        "experiment_tracking_writes_allowed": local_env.allow_experiment_tracking_writes,
        "ml_runtime_allowed": local_env.allow_ml_runtime,
        "coding_workspace_allowed": local_env.allow_coding_workspace,
    }
    return success_envelope(
        command=MCP_CONFIG_TOOL,
        agent_owner=MCP_SERVER_OWNER,
        side_effect=SideEffect.READ_ONLY,
        data={
            "environment": local_env.environment,
            "server_name": SERVER_NAME,
            "transport": local_env.transport,
            "artifact_root": str(local_env.artifact_root),
            "trader_config_path": str(local_env.trader_config_path)
            if local_env.trader_config_path
            else None,
            "tool_runtime": {
                "trader_config_path": str(local_env.trader_config_path)
                if local_env.trader_config_path
                else None,
                "env_path": str(local_env.tool_env_path)
                if local_env.tool_env_path
                else None,
                "config_loaded_at_startup": False,
                "event_store_provider": "configured"
                if local_env.trader_config_path
                else "noop",
            },
            "embedding_runtime": embedding_runtime_summary(local_env.embeddings_env()),
            "knowledge_store_runtime": knowledge_store_runtime_summary(
                local_env,
                provider_injected=knowledge_store_provider_configured,
            ),
            "research_artifact_store_runtime": research_artifact_store_runtime_summary(
                local_env,
                provider_injected=research_artifact_store_provider_configured,
            ),
            "optimizer_runtime": {
                "canonical_store": "research_artifacts",
                "built_in_profiles": ["builtin_grid", "builtin_random"],
                "optuna_profile_configured": bool(local_env.optuna_storage_url),
                "optuna_schema_authority": "sampler_state_only",
            },
            "experiment_tracking_runtime": {
                "canonical_store": "research_artifacts",
                "mlflow_profile_configured": bool(local_env.mlflow_tracking_uri),
                "authority": "analytical_projection_only",
            },
            "ml_inference_runtime": {
                "canonical_store": "research_artifacts",
                "profile_name": local_env.mlflow_inference_profile,
                "mlflow_tracking_uri_configured": bool(local_env.mlflow_tracking_uri),
                "runtime_allowed": local_env.allow_ml_runtime,
                "resolution": "session_start_only",
            },
            "coding_workspace_runtime": {
                "allowed": local_env.allow_coding_workspace,
                "workspace_root_configured": local_env.coding_workspace_root
                is not None,
                "repository_root_configured": local_env.coding_repository_root
                is not None,
                "repository_revision": local_env.coding_repository_revision or None,
                "container_image": local_env.coding_container_image or None,
                "network_enabled": False,
                "host_execution_allowed": False,
            },
            "tool_count": len(tool_metadata),
            "tools": tool_metadata,
            "policy": local_env.policy_flags(),
            "safety": safety,
        },
    )


def knowledge_store_runtime_summary(
    environment: McpEnvironment,
    *,
    provider_injected: bool = False,
) -> Mapping[str, Any]:
    """Return non-secret knowledge-store runtime metadata without opening the DB."""
    backend = environment.knowledge_store.strip().lower() or "postgres"
    configured = provider_injected or (
        backend == "postgres" and environment.trader_config_path is not None
    )
    return {
        "backend": backend,
        "configured": configured,
        "provider": "injected"
        if provider_injected
        else "trader_config_path"
        if configured
        else "unconfigured",
        "trader_config_path": str(environment.trader_config_path)
        if environment.trader_config_path
        else None,
        "pgvector_available": "not_checked" if backend == "postgres" else None,
    }


def research_artifact_store_runtime_summary(
    environment: McpEnvironment,
    *,
    provider_injected: bool = False,
) -> Mapping[str, Any]:
    """Return non-secret research-artifact store metadata without opening the DB."""
    configured = provider_injected or environment.trader_config_path is not None
    return {
        "backend": "postgres",
        "configured": configured,
        "provider": "injected"
        if provider_injected
        else "trader_config_path"
        if configured
        else "unconfigured",
        "trader_config_path": str(environment.trader_config_path)
        if environment.trader_config_path
        else None,
        "canonical_uri_scheme": "research://postgres/{artifact_type}/{artifact_id}",
    }


def build_data_inventory_envelope(
    *,
    event_store_provider: EventStoreProvider,
    symbols: Sequence[str],
    asset_class: str,
    timeframe: str,
    start: str,
    end: str,
    source: str | None = None,
    provider: str | None = None,
    instrument_type: str | None = None,
    bar_type: str | None = None,
    environment: McpEnvironment | None = None,
) -> ToolEnvelope:
    """Build a Data Agent inventory envelope from MCP-native inputs.

    Args:
        event_store_provider: Provider for read-only event-store queries.
        symbols: Requested symbol universe.
        asset_class: Requested asset class.
        timeframe: Requested bar timeframe.
        start: Inclusive requested start timestamp as ISO-8601 text.
        end: Inclusive requested end timestamp as ISO-8601 text.
        source: Optional source filter.

    Returns:
        Data Agent tool envelope for the requested inventory.
    """
    try:
        request = _data_inventory_request_from_inputs(
            symbols=symbols,
            asset_class=asset_class,
            timeframe=timeframe,
            start=start,
            end=end,
            source=source,
            provider=provider,
            instrument_type=instrument_type,
            bar_type=bar_type,
            environment=environment,
        )
    except ToolRuntimeConfigurationError as exc:
        return _tool_runtime_configuration_error_envelope(
            command=DATA_GET_INVENTORY_TOOL,
            side_effect=SideEffect.READ_ONLY,
            error=exc,
            environment=environment,
        )
    except ValueError as exc:
        return error_envelope(
            command=DATA_GET_INVENTORY_TOOL,
            side_effect=SideEffect.READ_ONLY,
            code="validation_error",
            message=str(exc),
        )
    try:
        event_store = event_store_provider()
    except Exception as exc:
        return _tool_runtime_configuration_error_envelope(
            command=DATA_GET_INVENTORY_TOOL,
            side_effect=SideEffect.READ_ONLY,
            error=exc,
            environment=environment,
        )
    return result_to_envelope(get_data_inventory(event_store, request))


def build_data_quality_envelope(
    *,
    event_store_provider: EventStoreProvider,
    symbols: Sequence[str],
    asset_class: str,
    timeframe: str,
    start: str,
    end: str,
    source: str | None = None,
    provider: str | None = None,
    instrument_type: str | None = None,
    bar_type: str | None = None,
    environment: McpEnvironment | None = None,
) -> ToolEnvelope:
    """Build a Data Agent quality envelope from MCP-native inputs.

    Args:
        event_store_provider: Provider for read-only event-store queries.
        symbols: Requested symbol universe.
        asset_class: Requested asset class.
        timeframe: Requested bar timeframe.
        start: Inclusive requested start timestamp as ISO-8601 text.
        end: Inclusive requested end timestamp as ISO-8601 text.
        source: Optional source filter.

    Returns:
        Data Agent quality envelope for the requested window.
    """
    try:
        request = _data_quality_request_from_inputs(
            symbols=symbols,
            asset_class=asset_class,
            timeframe=timeframe,
            start=start,
            end=end,
            source=source,
            provider=provider,
            instrument_type=instrument_type,
            bar_type=bar_type,
            environment=environment,
        )
    except ToolRuntimeConfigurationError as exc:
        return _tool_runtime_configuration_error_envelope(
            command=DATA_SUMMARIZE_QUALITY_TOOL,
            side_effect=SideEffect.READ_ONLY,
            error=exc,
            environment=environment,
        )
    except ValueError as exc:
        return error_envelope(
            command=DATA_SUMMARIZE_QUALITY_TOOL,
            side_effect=SideEffect.READ_ONLY,
            code="validation_error",
            message=str(exc),
        )
    try:
        event_store = event_store_provider()
    except Exception as exc:
        return _tool_runtime_configuration_error_envelope(
            command=DATA_SUMMARIZE_QUALITY_TOOL,
            side_effect=SideEffect.READ_ONLY,
            error=exc,
            environment=environment,
        )
    return result_to_envelope(summarize_quality_service(event_store, request))


def build_data_ensure_loaded_envelope(
    *,
    event_store_provider: EventStoreProvider,
    environment: McpEnvironment,
    symbols: Sequence[str],
    asset_class: str,
    timeframe: str,
    start: str,
    end: str,
    mode: str,
    source: str | None = None,
    dry_run: bool = True,
    provider: str | None = None,
    instrument_type: str | None = None,
    bar_type: str | None = None,
    acquisition_plan_id: str | None = None,
    operation_id: str | None = None,
    policy: DataEnsureLoadedPolicy | None = None,
    requested_by: str | None = None,
    actor: str | None = None,
    artifact_store_provider: ResearchArtifactStoreProvider | None = None,
) -> ToolEnvelope:
    """Build a Data Agent ensure-loaded envelope from MCP-native inputs.

    Args:
        event_store_provider: Provider for event-store reads and allowed local writes.
        environment: MCP environment carrying runtime mutation policy.
        symbols: Requested symbol universe.
        asset_class: Requested asset class.
        timeframe: Requested bar timeframe.
        start: Inclusive requested start timestamp as ISO-8601 text.
        end: Inclusive requested end timestamp as ISO-8601 text.
        mode: Ensure mode: existing, sample, or backfill.
        source: Optional source filter.
        dry_run: Whether backfill mode should plan only.
        acquisition_plan_id: Exact prior dry-run plan for execution.
        operation_id: Trusted orchestration operation identity.
        policy: Optional explicit loading policy. Defaults to environment policy.
        requested_by: Owning research-session identity for mutation evidence.
        actor: Public runtime actor for mutation evidence.
        artifact_store_provider: Canonical store provider for the mutation
            journal.

    Returns:
        Data Agent ensure-loaded envelope.
    """
    try:
        request = _data_ensure_loaded_request_from_inputs(
            symbols=symbols,
            asset_class=asset_class,
            timeframe=timeframe,
            start=start,
            end=end,
            mode=mode,
            source=source,
            dry_run=dry_run,
            provider=provider,
            instrument_type=instrument_type,
            bar_type=bar_type,
            acquisition_plan_id=acquisition_plan_id,
            operation_id=operation_id,
            requested_by=requested_by,
            actor=actor,
            environment=environment,
        )
    except ToolRuntimeConfigurationError as exc:
        return _tool_runtime_configuration_error_envelope(
            command=DATA_ENSURE_LOADED_TOOL,
            side_effect=SideEffect.LOCAL_MUTATING,
            error=exc,
            environment=environment,
        )
    except ValueError as exc:
        return error_envelope(
            command=DATA_ENSURE_LOADED_TOOL,
            side_effect=SideEffect.LOCAL_MUTATING,
            code="validation_error",
            message=str(exc),
        )
    try:
        event_store = event_store_provider()
    except Exception as exc:
        return _tool_runtime_configuration_error_envelope(
            command=DATA_ENSURE_LOADED_TOOL,
            side_effect=SideEffect.LOCAL_MUTATING,
            error=exc,
            environment=environment,
        )
    return result_to_envelope(
        ensure_loaded_service(
            event_store,
            request,
            policy=policy
            or DataEnsureLoadedPolicy(
                allow_data_loading=environment.allow_data_loading,
                backfill_config_path=environment.trader_config_path,
            ),
            artifact_store=(
                artifact_store_provider()
                if artifact_store_provider is not None
                else None
            ),
        )
    )


def build_data_symbol_discovery_envelope(
    *,
    event_store_provider: EventStoreProvider,
    environment: McpEnvironment,
    symbols: Sequence[str] | None = None,
    asset_class: str | None = None,
    instrument_type: str | None = None,
    bar_type: str | None = None,
    query: str | None = None,
    source: str = "local",
    provider: str | None = None,
    timeframe: str | None = None,
    source_filter: str | None = None,
    limit: int = 50,
    active_only: bool = True,
    tradable_only: bool = True,
    include_local_coverage: bool = False,
    policy: DataSymbolDiscoveryPolicy | None = None,
    policy_provider: SymbolDiscoveryPolicyProvider | None = None,
) -> ToolEnvelope:
    """Build a Data Agent symbol discovery envelope from MCP-native inputs."""
    try:
        request = _data_symbol_discovery_request_from_inputs(
            environment=environment,
            symbols=symbols,
            asset_class=asset_class,
            instrument_type=instrument_type,
            bar_type=bar_type,
            query=query,
            source=source,
            provider=provider,
            timeframe=timeframe,
            source_filter=source_filter,
            limit=limit,
            active_only=active_only,
            tradable_only=tradable_only,
            include_local_coverage=include_local_coverage,
        )
    except ToolRuntimeConfigurationError as exc:
        return _tool_runtime_configuration_error_envelope(
            command=DATA_DISCOVER_SYMBOLS_TOOL,
            side_effect=SideEffect.READ_ONLY,
            error=exc,
            environment=environment,
        )
    except ValueError as exc:
        return error_envelope(
            command=DATA_DISCOVER_SYMBOLS_TOOL,
            side_effect=SideEffect.READ_ONLY,
            code="validation_error",
            message=str(exc),
        )
    try:
        event_store = event_store_provider()
        runtime_policy = policy
        if (
            runtime_policy is None
            and policy_provider is not None
            and str(source).strip().lower()
            in {
                "provider",
                "merged",
            }
        ):
            runtime_policy = policy_provider()
    except Exception as exc:
        return _tool_runtime_configuration_error_envelope(
            command=DATA_DISCOVER_SYMBOLS_TOOL,
            side_effect=SideEffect.READ_ONLY,
            error=exc,
            environment=environment,
        )
    return result_to_envelope(
        discover_symbols_service(event_store, request, policy=runtime_policy)
    )


def _data_inventory_request_from_inputs(
    *,
    symbols: Sequence[str],
    asset_class: str,
    timeframe: str,
    start: str,
    end: str,
    source: str | None,
    provider: str | None,
    instrument_type: str | None,
    bar_type: str | None,
    environment: McpEnvironment | None,
) -> DataInventoryRequest:
    """Build a Data Agent inventory request from MCP tool inputs.

    Args:
        symbols: Requested symbol universe.
        asset_class: Requested asset class.
        timeframe: Requested bar timeframe.
        start: Inclusive requested start timestamp as ISO-8601 text.
        end: Inclusive requested end timestamp as ISO-8601 text.
        source: Optional source filter.

    Returns:
        Data inventory request with parsed datetimes.

    Raises:
        ValueError: If MCP inputs are not JSON-native values expected by the tool.
    """
    provider_context = _configured_market_data_context(environment)
    return DataInventoryRequest(
        symbols=_parse_symbols(symbols),
        asset_class=str(asset_class),
        timeframe=str(timeframe),
        start=_parse_iso_datetime(start, field_name="start"),
        end=_parse_iso_datetime(end, field_name="end"),
        source=str(source) if source is not None else None,
        provider=_optional_str(provider),
        instrument_type=_optional_str(instrument_type),
        bar_type=_optional_str(bar_type),
        configured_provider=provider_context["configured_provider"],
        configured_asset_class=provider_context["configured_asset_class"],
    )


def _data_quality_request_from_inputs(
    *,
    symbols: Sequence[str],
    asset_class: str,
    timeframe: str,
    start: str,
    end: str,
    source: str | None,
    provider: str | None,
    instrument_type: str | None,
    bar_type: str | None,
    environment: McpEnvironment | None,
) -> DataQualityRequest:
    """Build a Data Agent quality request from MCP tool inputs.

    Args:
        symbols: Requested symbol universe.
        asset_class: Requested asset class.
        timeframe: Requested bar timeframe.
        start: Inclusive requested start timestamp as ISO-8601 text.
        end: Inclusive requested end timestamp as ISO-8601 text.
        source: Optional source filter.

    Returns:
        Data quality request with parsed datetimes.

    Raises:
        ValueError: If MCP inputs are not JSON-native values expected by the tool.
    """
    provider_context = _configured_market_data_context(environment)
    return DataQualityRequest(
        symbols=_parse_symbols(symbols),
        asset_class=str(asset_class),
        timeframe=str(timeframe),
        start=_parse_iso_datetime(start, field_name="start"),
        end=_parse_iso_datetime(end, field_name="end"),
        source=str(source) if source is not None else None,
        provider=_optional_str(provider),
        instrument_type=_optional_str(instrument_type),
        bar_type=_optional_str(bar_type),
        configured_provider=provider_context["configured_provider"],
        configured_asset_class=provider_context["configured_asset_class"],
    )


def _data_ensure_loaded_request_from_inputs(
    *,
    symbols: Sequence[str],
    asset_class: str,
    timeframe: str,
    start: str,
    end: str,
    mode: str,
    source: str | None,
    dry_run: bool,
    provider: str | None,
    instrument_type: str | None,
    bar_type: str | None,
    acquisition_plan_id: str | None,
    operation_id: str | None,
    requested_by: str | None,
    actor: str | None,
    environment: McpEnvironment,
) -> DataEnsureLoadedRequest:
    """Build a Data Agent ensure-loaded request from MCP tool inputs.

    Args:
        symbols: Requested symbol universe.
        asset_class: Requested asset class.
        timeframe: Requested bar timeframe.
        start: Inclusive requested start timestamp as ISO-8601 text.
        end: Inclusive requested end timestamp as ISO-8601 text.
        mode: Ensure mode.
        source: Optional source filter.
        dry_run: Whether backfill mode should plan only.
        acquisition_plan_id: Exact prior dry-run plan for execution.
        operation_id: Trusted orchestration operation identity.
        requested_by: Owning research-session identity.
        actor: Public runtime actor.

    Returns:
        Data ensure-loaded request with parsed datetimes.

    Raises:
        ValueError: If MCP inputs are not JSON-native values expected by the tool.
    """
    provider_context = _configured_market_data_context(environment)
    return DataEnsureLoadedRequest(
        symbols=_parse_symbols(symbols),
        asset_class=str(asset_class),
        timeframe=str(timeframe),
        start=_parse_iso_datetime(start, field_name="start"),
        end=_parse_iso_datetime(end, field_name="end"),
        mode=str(mode),
        source=str(source) if source is not None else None,
        dry_run=_parse_bool(dry_run, field_name="dry_run"),
        provider=_optional_str(provider),
        instrument_type=_optional_str(instrument_type),
        bar_type=_optional_str(bar_type),
        configured_provider=provider_context["configured_provider"],
        configured_asset_class=provider_context["configured_asset_class"],
        acquisition_plan_id=_optional_str(acquisition_plan_id),
        operation_id=_optional_str(operation_id),
        requested_by=_optional_str(requested_by),
        actor=_optional_str(actor),
    )


def _data_symbol_discovery_request_from_inputs(
    *,
    environment: McpEnvironment,
    symbols: Sequence[str] | None,
    asset_class: str | None,
    instrument_type: str | None,
    bar_type: str | None,
    query: str | None,
    source: str,
    provider: str | None,
    timeframe: str | None,
    source_filter: str | None,
    limit: int,
    active_only: bool,
    tradable_only: bool,
    include_local_coverage: bool,
) -> DataSymbolDiscoveryRequest:
    """Build a Data Agent symbol discovery request from MCP tool inputs."""
    provider_context = _configured_market_data_context(environment)
    return DataSymbolDiscoveryRequest(
        symbols=_parse_optional_symbols(symbols),
        asset_class=_optional_str(asset_class),
        instrument_type=_optional_str(instrument_type),
        bar_type=_optional_str(bar_type),
        query=_optional_str(query),
        source=str(source),
        provider=_optional_str(provider),
        configured_provider=provider_context["configured_provider"],
        configured_asset_class=provider_context["configured_asset_class"],
        configured_symbols=tuple(provider_context["configured_symbols"]),
        timeframe=_optional_str(timeframe),
        source_filter=_optional_str(source_filter),
        limit=int(limit),
        active_only=_parse_bool(active_only, field_name="active_only"),
        tradable_only=_parse_bool(tradable_only, field_name="tradable_only"),
        include_local_coverage=_parse_bool(
            include_local_coverage, field_name="include_local_coverage"
        ),
        configured_universe_available=bool(
            provider_context["configured_universe_available"]
        ),
    )


def _configured_market_data_context(
    environment: McpEnvironment | None,
) -> _ConfiguredMarketDataContext:
    """Return configured market-data provider context for MCP tool requests."""
    if environment is None or environment.trader_config_path is None:
        return {
            "configured_provider": None,
            "configured_asset_class": None,
            "configured_symbols": tuple(),
            "configured_universe_available": False,
        }
    try:
        config = load_tool_config(environment)
    except ToolRuntimeConfigurationError:
        return {
            "configured_provider": None,
            "configured_asset_class": None,
            "configured_symbols": tuple(),
            "configured_universe_available": False,
        }
    return {
        "configured_provider": config.market_data_source,
        "configured_asset_class": config.market_data_asset_class,
        "configured_symbols": tuple(config.market_data_symbols),
        "configured_universe_available": True,
    }


def _tool_runtime_configuration_error_envelope(
    *,
    command: str,
    side_effect: SideEffect,
    error: Exception,
    environment: McpEnvironment | None,
) -> ToolEnvelope:
    """Return a structured tool-level failure for invalid execution config."""
    return error_envelope(
        command=command,
        side_effect=side_effect,
        code="tool_runtime_configuration_error",
        message=str(error),
        data={
            "trader_config_path": str(environment.trader_config_path)
            if environment is not None and environment.trader_config_path is not None
            else None,
        },
    )


def _parse_symbols(symbols: Sequence[str]) -> tuple[str, ...]:
    """Parse MCP symbol input into a tuple.

    Args:
        symbols: JSON array of requested symbols.

    Returns:
        Tuple of symbol strings.

    Raises:
        ValueError: If symbols are not supplied as a JSON array.
    """
    if isinstance(symbols, str) or not isinstance(symbols, Sequence):
        raise ValueError("symbols must be a JSON array of strings")
    return tuple(str(symbol) for symbol in symbols)


def _parse_optional_symbols(symbols: Sequence[str] | None) -> tuple[str, ...]:
    """Parse an optional MCP symbol input into a tuple."""
    if symbols is None:
        return tuple()
    return _parse_symbols(symbols)


def _optional_str(value: object) -> str | None:
    """Return a stripped string or None for omitted optional MCP inputs."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _parse_bool(value: object, *, field_name: str) -> bool:
    """Parse a JSON-native boolean input.

    Args:
        value: Candidate boolean value.
        field_name: Input field name used in validation errors.

    Returns:
        Parsed boolean.

    Raises:
        ValueError: If the value cannot be interpreted as a boolean.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    raise ValueError(f"{field_name} must be a boolean")


def _parse_iso_datetime(value: str, *, field_name: str) -> datetime:
    """Parse an ISO-8601 timestamp from MCP input.

    Args:
        value: Timestamp text.
        field_name: Input field name used in validation errors.

    Returns:
        Timezone-aware UTC datetime. Naive datetimes are treated as UTC.

    Raises:
        ValueError: If the value is not an ISO-8601 timestamp string.
    """
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be an ISO-8601 timestamp string")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO-8601 timestamp string") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def main() -> None:
    """Run the MCP server with protocol-safe stderr lifecycle logging."""
    local_env = load_local_environment()
    console = McpConsoleLogger(mcp_console_config())
    console.info(
        "trader.mcp.server.started",
        server=SERVER_NAME,
        transport=local_env.transport,
        tool_count=len(REGISTERED_TOOL_NAMES),
    )
    console.debug(
        "trader.mcp.server.configured",
        environment=local_env.environment,
        server=SERVER_NAME,
        transport=local_env.transport,
    )
    try:
        create_server(local_env).run(transport=local_env.transport)
    finally:
        console.info(
            "trader.mcp.server.stopped",
            server=SERVER_NAME,
            transport=local_env.transport,
        )


if __name__ == "__main__":
    main()
