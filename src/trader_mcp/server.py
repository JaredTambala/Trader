"""Stdio MCP server skeleton for research tools."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from typing import Any, TypedDict

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult

from trader.config import Config, build_config, load_yaml_config
from trader.event_store import EventStore, NoOpEventStore, build_event_store
from trader_mcp.adapters import result_to_mcp_result
from trader_mcp.adversarial_tools import register_adversarial_tools
from trader_mcp.coding_tools import (
    CodingWorkspaceServiceProvider,
    register_coding_tools,
)
from trader_mcp.constants import (
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
    MATH_GENERATE_PYTHON_METHOD_TOOL,
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
from trader_mcp.environment import McpEnvironment, load_local_environment
from trader_mcp.evaluation_tools import register_evaluation_tools
from trader_mcp.knowledge_tools import register_quant_methods_tools
from trader_mcp.ml_tools import register_ml_tools
from trader_mcp.orchestration_tools import register_orchestration_tools
from trader_mcp.research_tools import register_research_tools
from trader_research.governance import agent_owner_for_tool
from trader_research.foundation import (
    ContextualResearchArtifactStore,
    ResearchArtifactStore,
    UnavailableResearchArtifactStore,
)
from trader_mcp.contracts import (
    SCHEMA_VERSION,
    SideEffect,
    ToolEnvelope,
    error_envelope,
    result_to_envelope,
    side_effect_for_operation,
    success_envelope,
)
from trader_research.coding import (
    CodingWorkspacePolicy,
    CodingWorkspaceService,
    DockerContainerRunner,
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
    KnowledgeStore,
    PostgresKnowledgeStore,
    UnavailableKnowledgeStore,
    embedding_runtime_summary,
)
from trader_research.experiments import ExperimentTrackingSinkRegistry, OptimizationEngineRegistry
from trader_research.ml import (
    ArtifactPredictionDeploymentReader,
    ArtifactPredictionRuntimeResolver,
    InferenceAdapterRegistry,
)
from trader_mlflow import MLflowLocalPyfuncAdapter
from trader_standard.predictions import MaintainedPredictionMapperCatalog
from trader_research.infrastructure.providers.alpaca import AlpacaSymbolCatalogProvider
from trader_research.infrastructure.providers.mlflow import MLflowExperimentTrackingSink
from trader_research.infrastructure.providers.optuna import OptunaOptimizationEngine
from trader_research.infrastructure.postgres import PostgresResearchArtifactStore


EventStoreProvider = Callable[[], EventStore]
"""Callable that returns the event store used by read-only MCP tools."""

ToolConfigProvider = Callable[[], Config]
"""Callable that returns runtime config for tools that execute platform code."""

KnowledgeStoreProvider = Callable[[], KnowledgeStore]
"""Callable that returns the store used by Quant Methods knowledge tools."""

ResearchArtifactStoreProvider = Callable[[], ResearchArtifactStore]
"""Callable that returns the DB-first research artifact store."""

SymbolDiscoveryPolicyProvider = Callable[[], DataSymbolDiscoveryPolicy]
"""Callable that returns the symbol-discovery policy for Data Agent tools."""


class _ConfiguredMarketDataContext(TypedDict):
    """Typed config values copied into bounded Data Agent requests."""

    configured_provider: str | None
    configured_asset_class: str | None
    configured_symbols: tuple[str, ...]
    configured_universe_available: bool


class ToolRuntimeConfigurationError(ValueError):
    """Raised when a registered tool's execution environment is invalid."""


def create_server(
    environment: McpEnvironment | None = None,
    event_store_provider: EventStoreProvider | None = None,
    data_loading_policy: DataEnsureLoadedPolicy | None = None,
    symbol_discovery_policy: DataSymbolDiscoveryPolicy | None = None,
    knowledge_embedding_provider: EmbeddingProvider | None = None,
    knowledge_store_provider: KnowledgeStoreProvider | None = None,
    research_artifact_store_provider: ResearchArtifactStoreProvider | None = None,
    method_generation_llm_client: Any | None = None,
    backtest_config_provider: ToolConfigProvider | None = None,
    optimizer_registry: OptimizationEngineRegistry | None = None,
    tracking_sink_registry: ExperimentTrackingSinkRegistry | None = None,
    inference_adapter_registry: InferenceAdapterRegistry | None = None,
    prediction_mapper_catalog: MaintainedPredictionMapperCatalog | None = None,
    coding_workspace_service_provider: CodingWorkspaceServiceProvider | None = None,
) -> FastMCP:
    """Create the MCP server and register the configured bounded tool catalog.

    Args:
        environment: Optional resolved local MCP environment.
        event_store_provider: Optional provider for read-only event-store queries.
        data_loading_policy: Optional explicit data-loading policy for tests or
            controlled embedding.
        coding_workspace_service_provider: Optional isolated Coding Workspace
            service provider for Strategy Engineering tools.

    Returns:
        Configured FastMCP server instance.
    """
    local_env = environment or load_local_environment()
    data_event_store_provider = event_store_provider or build_event_store_provider(local_env)
    resolved_backtest_config_provider = backtest_config_provider or (lambda: _load_tool_config(local_env))
    resolved_knowledge_store_provider = knowledge_store_provider or build_knowledge_store_provider(local_env)
    resolved_research_artifact_store_provider = research_artifact_store_provider or build_research_artifact_store_provider(
        local_env
    )
    resolved_optimizer_registry = optimizer_registry or OptimizationEngineRegistry(
        engines=[
            OptunaOptimizationEngine(
                storage_url=local_env.optuna_storage_url,
                study_prefix=local_env.optuna_study_prefix,
                schema_name=local_env.optuna_schema,
                role_name=local_env.optuna_role,
            )
        ]
    )
    resolved_tracking_sink_registry = tracking_sink_registry or ExperimentTrackingSinkRegistry(
        sinks=[
            MLflowExperimentTrackingSink(
                tracking_uri=local_env.mlflow_tracking_uri,
                experiment_name=local_env.mlflow_optimization_experiment,
            )
        ]
    )
    resolved_inference_adapter_registry = inference_adapter_registry or InferenceAdapterRegistry(
        adapters=(
            MLflowLocalPyfuncAdapter(
                profile_name=local_env.mlflow_inference_profile,
                tracking_uri=local_env.mlflow_tracking_uri,
            ),
        )
        if local_env.mlflow_tracking_uri
        else ()
    )
    resolved_prediction_mapper_catalog = (
        prediction_mapper_catalog or MaintainedPredictionMapperCatalog()
    )
    resolved_coding_workspace_service_provider = (
        coding_workspace_service_provider
        if coding_workspace_service_provider is not None
        else build_coding_workspace_service_provider(local_env)
    )

    def _prediction_deployment_reader() -> ArtifactPredictionDeploymentReader:
        return ArtifactPredictionDeploymentReader(resolved_research_artifact_store_provider())

    def _prediction_runtime_resolver() -> ArtifactPredictionRuntimeResolver:
        return ArtifactPredictionRuntimeResolver(
            artifact_store=resolved_research_artifact_store_provider(),
            adapter_registry=resolved_inference_adapter_registry,
            mapper_catalog=resolved_prediction_mapper_catalog,
        )
    resolved_data_loading_policy = data_loading_policy or DataEnsureLoadedPolicy(
        allow_data_loading=local_env.allow_data_loading,
        backfill_config_path=local_env.trader_config_path,
    )
    resolved_symbol_discovery_policy_provider = (
        (lambda: symbol_discovery_policy)
        if symbol_discovery_policy is not None
        else build_symbol_discovery_policy_provider(local_env)
    )
    server = FastMCP(SERVER_NAME)

    @server.tool(name=MCP_HEALTH_TOOL, description=SUPPORT_TOOL_DESCRIPTIONS[MCP_HEALTH_TOOL])
    def mcp_health() -> CallToolResult:
        """Return read-only MCP server health.

        Returns:
            MCP call result containing a read-only health envelope.
        """
        return CallToolResult(**result_to_mcp_result(build_health_envelope(local_env)))

    @server.tool(name=MCP_CONFIG_TOOL, description=SUPPORT_TOOL_DESCRIPTIONS[MCP_CONFIG_TOOL])
    def mcp_get_config() -> CallToolResult:
        """Return read-only MCP server configuration.

        Returns:
            MCP call result containing a read-only configuration envelope.
        """
        return CallToolResult(
            **result_to_mcp_result(
                build_config_envelope(
                    local_env,
                    knowledge_store_provider_configured=knowledge_store_provider is not None,
                    research_artifact_store_provider_configured=research_artifact_store_provider is not None,
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
            policy=resolved_data_loading_policy,
        )
        return CallToolResult(**result_to_mcp_result(envelope))

    register_quant_methods_tools(
        server,
        local_env,
        embedding_provider=knowledge_embedding_provider,
        knowledge_store_provider=resolved_knowledge_store_provider,
        artifact_store_provider=resolved_research_artifact_store_provider,
        method_generation_llm_client=method_generation_llm_client,
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
    register_research_tools(
        server,
        local_env,
        event_store_provider=data_event_store_provider,
        backtest_config_provider=resolved_backtest_config_provider,
        artifact_store_provider=resolved_research_artifact_store_provider,
        optimizer_registry=resolved_optimizer_registry,
        tracking_sink_registry=resolved_tracking_sink_registry,
        prediction_deployment_reader_provider=_prediction_deployment_reader,
        prediction_mapper_catalog=resolved_prediction_mapper_catalog,
        prediction_runtime_resolver_provider=_prediction_runtime_resolver,
    )
    register_orchestration_tools(
        server,
        artifact_store_provider=resolved_research_artifact_store_provider,
    )
    register_evaluation_tools(server, local_env, artifact_store_provider=resolved_research_artifact_store_provider)
    register_adversarial_tools(server, artifact_store_provider=resolved_research_artifact_store_provider)

    return server


def build_event_store_provider(environment: McpEnvironment | None = None) -> EventStoreProvider:
    """Build the lazy event-store provider used by Data Agent tools.

    Args:
        environment: Optional resolved local MCP environment.

    Returns:
        Provider that returns a configured event store, or a no-op store when no
        trader config path is configured.
    """
    local_env = environment or load_local_environment()
    if local_env.trader_config_path is None:
        return NoOpEventStore

    event_store: EventStore | None = None

    def _provider() -> EventStore:
        nonlocal event_store
        if event_store is None:
            event_store = build_event_store(_load_tool_config(local_env))
        return event_store

    return _provider


def build_knowledge_store_provider(environment: McpEnvironment | None = None) -> KnowledgeStoreProvider:
    """Build the lazy knowledge-store provider used by Quant Methods tools."""
    local_env = environment or load_local_environment()
    backend = local_env.knowledge_store.strip().lower()
    if backend != "postgres":
        return lambda: UnavailableKnowledgeStore(f"Unsupported knowledge store backend: {local_env.knowledge_store}")
    if local_env.trader_config_path is None:
        return lambda: UnavailableKnowledgeStore(
            "Postgres knowledge store requires TRADER_MCP_TRADER_CONFIG_PATH"
        )

    store: KnowledgeStore | None = None

    def _provider() -> KnowledgeStore:
        nonlocal store
        if store is None:
            try:
                config = _load_tool_config(local_env)
            except ToolRuntimeConfigurationError as exc:
                return UnavailableKnowledgeStore(str(exc))
            store = PostgresKnowledgeStore(
                dsn=getattr(config, "pg_dsn", None) or None,
                host=getattr(config, "pg_host", None) or None,
                port=getattr(config, "pg_port", None) or None,
                dbname=getattr(config, "pg_db", None) or None,
                user=getattr(config, "pg_user", None) or None,
                password=getattr(config, "pg_password", None) or None,
            )
        return store

    return _provider


def build_research_artifact_store_provider(
    environment: McpEnvironment | None = None,
) -> ResearchArtifactStoreProvider:
    """Build the lazy structured research-artifact store provider."""
    local_env = environment or load_local_environment()
    if local_env.trader_config_path is None:
        return lambda: UnavailableResearchArtifactStore(
            "Postgres research artifact store requires TRADER_MCP_TRADER_CONFIG_PATH"
        )

    store: ResearchArtifactStore | None = None

    def _provider() -> ResearchArtifactStore:
        nonlocal store
        if store is None:
            try:
                config = _load_tool_config(local_env)
            except ToolRuntimeConfigurationError as exc:
                return UnavailableResearchArtifactStore(str(exc))
            store = PostgresResearchArtifactStore(
                dsn=getattr(config, "pg_dsn", None) or None,
                host=getattr(config, "pg_host", None) or None,
                port=getattr(config, "pg_port", None) or None,
                dbname=getattr(config, "pg_db", None) or None,
                user=getattr(config, "pg_user", None) or None,
                password=getattr(config, "pg_password", None) or None,
            )
        return store

    return _provider


def build_coding_workspace_service_provider(
    environment: McpEnvironment | None = None,
) -> CodingWorkspaceServiceProvider | None:
    """Build the lazy isolated Coding Workspace service provider.

    The provider is unavailable unless the environment explicitly enables the
    capability and pins dedicated workspace, repository, revision, and image
    values. Generated code is never executed by the host process.

    Args:
        environment: Optional resolved local MCP environment.

    Returns:
        Lazy workspace-service provider, or ``None`` when disabled or incomplete.
    """
    local_env = environment or load_local_environment()
    if not local_env.allow_coding_workspace:
        return None
    workspace_root = local_env.coding_workspace_root
    repository_root = local_env.coding_repository_root
    if (
        workspace_root is None
        or repository_root is None
        or not local_env.coding_repository_revision
        or not local_env.coding_container_image
    ):
        return None
    service: CodingWorkspaceService | None = None

    def _provider() -> CodingWorkspaceService:
        nonlocal service
        if service is None:
            policy = CodingWorkspacePolicy(
                workspace_root=workspace_root,
                repository_root=repository_root,
                repository_revision=local_env.coding_repository_revision,
                container_image=local_env.coding_container_image,
                allowed_dependencies=("trader",),
            )
            service = CodingWorkspaceService(
                policy,
                runner=DockerContainerRunner(policy.container_image),
            )
        return service

    return _provider


def build_symbol_discovery_policy_provider(environment: McpEnvironment | None = None) -> SymbolDiscoveryPolicyProvider:
    """Build the lazy symbol-discovery policy provider used by Data Agent tools."""
    local_env = environment or load_local_environment()
    policy: DataSymbolDiscoveryPolicy | None = None

    def _provider() -> DataSymbolDiscoveryPolicy:
        nonlocal policy
        if policy is None:
            policy = build_symbol_discovery_policy(local_env)
        return policy

    return _provider


def build_symbol_discovery_policy(environment: McpEnvironment | None = None) -> DataSymbolDiscoveryPolicy:
    """Build the read-only symbol discovery policy for the MCP runtime."""
    local_env = environment or load_local_environment()
    if not local_env.allow_symbol_provider_discovery or local_env.trader_config_path is None:
        return DataSymbolDiscoveryPolicy(
            allow_provider_discovery=local_env.allow_symbol_provider_discovery,
        )
    config = _load_tool_config(local_env)
    providers = {}
    if config.market_data_source.strip().lower() == "alpaca":
        providers["alpaca"] = AlpacaSymbolCatalogProvider(
            api_key=config.alpaca_api_key,
            secret_key=config.alpaca_secret_key,
            base_url=config.alpaca_base_url,
        )
    return DataSymbolDiscoveryPolicy(
        allow_provider_discovery=local_env.allow_symbol_provider_discovery,
        catalog_providers=providers,
    )


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
            "agent_owner": agent_owner_for_tool(
                DATA_CREATE_RESEARCH_SNAPSHOT_TOOL
            ),
            "side_effect": SideEffect.LOCAL_MUTATING.value,
            "description": DATA_TOOL_DESCRIPTIONS[
                DATA_CREATE_RESEARCH_SNAPSHOT_TOOL
            ],
        },
    ]
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
                MATH_GENERATE_PYTHON_METHOD_TOOL,
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
            "trader_config_path": str(local_env.trader_config_path) if local_env.trader_config_path else None,
            "tool_runtime": {
                "trader_config_path": str(local_env.trader_config_path) if local_env.trader_config_path else None,
                "env_path": str(local_env.tool_env_path) if local_env.tool_env_path else None,
                "config_loaded_at_startup": False,
                "event_store_provider": "configured" if local_env.trader_config_path else "noop",
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
                "workspace_root_configured": local_env.coding_workspace_root is not None,
                "repository_root_configured": local_env.coding_repository_root is not None,
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
    configured = provider_injected or (backend == "postgres" and environment.trader_config_path is not None)
    return {
        "backend": backend,
        "configured": configured,
        "provider": "injected" if provider_injected else "trader_config_path" if configured else "unconfigured",
        "trader_config_path": str(environment.trader_config_path) if environment.trader_config_path else None,
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
        "provider": "injected" if provider_injected else "trader_config_path" if configured else "unconfigured",
        "trader_config_path": str(environment.trader_config_path) if environment.trader_config_path else None,
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
    policy: DataEnsureLoadedPolicy | None = None,
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
        policy: Optional explicit loading policy. Defaults to environment policy.

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
        if runtime_policy is None and policy_provider is not None and str(source).strip().lower() in {
            "provider",
            "merged",
        }:
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
        include_local_coverage=_parse_bool(include_local_coverage, field_name="include_local_coverage"),
        configured_universe_available=bool(provider_context["configured_universe_available"]),
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
        config = _load_tool_config(environment)
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


def _load_tool_config(environment: McpEnvironment) -> Config:
    """Load trader config for tool execution without making MCP startup depend on it."""
    if environment.trader_config_path is None:
        raise ToolRuntimeConfigurationError("Tool execution requires a trader config path.")
    _load_tool_env(environment)
    try:
        return build_config(load_yaml_config(environment.trader_config_path))
    except (OSError, ValueError) as exc:
        raise ToolRuntimeConfigurationError(
            f"Unable to build tool execution config from {environment.trader_config_path}: {exc}"
        ) from exc


def _load_tool_env(environment: McpEnvironment) -> None:
    """Load the optional tool-runtime env file used by trader YAML expansion."""
    if environment.tool_env_path is None:
        return
    if not environment.tool_env_path.exists():
        raise ToolRuntimeConfigurationError(f"Tool runtime env file not found: {environment.tool_env_path}")
    load_dotenv(environment.tool_env_path, override=False)


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
    """Run the MCP server over stdio transport."""
    local_env = load_local_environment()
    create_server(local_env).run(transport=local_env.transport)


if __name__ == "__main__":
    main()
