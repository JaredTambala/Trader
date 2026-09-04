"""Trusted composition of concrete dependencies for the Trader MCP runtime.

This module is the only ``trader_mcp`` source module allowed to import concrete
provider infrastructure, optional adapter packages, or maintained platform
implementations. Protocol registration consumes the resolved dependency bundle
and therefore remains independent of those construction choices.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from dotenv import load_dotenv

from trader.config import Config, build_config, load_yaml_config
from trader.event_store import EventStore, NoOpEventStore, build_event_store
from trader_mlflow import MLflowLocalPyfuncAdapter
from trader_standard.predictions import MaintainedPredictionMapperCatalog
from trader_mcp.catalogue.policy import McpEnvironment, load_local_environment
from trader_research.coding import (
    CodingWorkspacePolicy,
    CodingWorkspaceService,
    DockerContainerRunner,
)
from trader_research.data import (
    DataEnsureLoadedPolicy,
    DataSymbolDiscoveryPolicy,
)
from trader_research.experiments import (
    ExperimentTrackingSinkRegistry,
    OptimizationEngineRegistry,
    OptimizationTrialExecutor,
)
from trader_research.foundation import (
    PredictionMapperCatalog,
    ResearchArtifactStore,
    UnavailableResearchArtifactStore,
)
from trader_research.infrastructure.execution import (
    PostgresBacktestOptimizationTrialExecutor,
)
from trader_research.infrastructure.postgres import (
    PostgresKnowledgeStore,
    PostgresResearchArtifactStore,
)
from trader_research.infrastructure.providers.alpaca import AlpacaSymbolCatalogProvider
from trader_research.infrastructure.providers.mlflow import MLflowExperimentTrackingSink
from trader_research.infrastructure.providers.optuna import OptunaOptimizationEngine
from trader_research.knowledge import KnowledgeStore, UnavailableKnowledgeStore
from trader_research.ml import InferenceAdapterRegistry


EventStoreProvider = Callable[[], EventStore]
"""Callable that returns the event store used by MCP capabilities."""

ToolConfigProvider = Callable[[], Config]
"""Callable that returns configuration for tools executing platform code."""

KnowledgeStoreProvider = Callable[[], KnowledgeStore]
"""Callable that returns the Quantitative Methods knowledge store."""

ResearchArtifactStoreProvider = Callable[[], ResearchArtifactStore]
"""Callable that returns the canonical research artifact store."""

CodingWorkspaceServiceProvider = Callable[[], CodingWorkspaceService]
"""Callable that returns the isolated Coding Workspace service."""

SymbolDiscoveryPolicyProvider = Callable[[], DataSymbolDiscoveryPolicy]
"""Callable that returns the Data Agent symbol-discovery policy."""

OptimizationTrialExecutorFactory = Callable[
    [EventStore, Config, ResearchArtifactStore], OptimizationTrialExecutor
]
"""Callable that composes the concrete optimization trial executor."""


class ToolRuntimeConfigurationError(ValueError):
    """Raised when a registered tool's execution environment is invalid."""


@dataclass(frozen=True)
class McpRuntimeDependencies:
    """Resolved runtime dependencies consumed by MCP tool registration.

    Attributes:
        event_store_provider: Lazy provider for market-data and backtest storage.
        backtest_config_provider: Lazy provider for normalized Trader config.
        data_loading_policy: Environment-derived Data loading policy.
        symbol_discovery_policy_provider: Lazy provider for symbol discovery.
        knowledge_store_provider: Lazy provider for research knowledge storage.
        research_artifact_store_provider: Lazy canonical artifact-store provider.
        optimizer_registry: Admitted parameter-optimization engines.
        tracking_sink_registry: Admitted experiment-tracking projections.
        inference_adapter_registry: Admitted model-inference adapters.
        prediction_mapper_catalog: Maintained prediction-to-signal mappings.
        coding_workspace_service_provider: Optional isolated coding service.
        optimization_trial_executor_factory: Concrete trial-executor factory.
    """

    event_store_provider: EventStoreProvider
    backtest_config_provider: ToolConfigProvider
    data_loading_policy: DataEnsureLoadedPolicy
    symbol_discovery_policy_provider: SymbolDiscoveryPolicyProvider
    knowledge_store_provider: KnowledgeStoreProvider
    research_artifact_store_provider: ResearchArtifactStoreProvider
    optimizer_registry: OptimizationEngineRegistry
    tracking_sink_registry: ExperimentTrackingSinkRegistry
    inference_adapter_registry: InferenceAdapterRegistry
    prediction_mapper_catalog: PredictionMapperCatalog
    coding_workspace_service_provider: CodingWorkspaceServiceProvider | None
    optimization_trial_executor_factory: OptimizationTrialExecutorFactory


def compose_runtime_dependencies(
    environment: McpEnvironment,
    *,
    event_store_provider: EventStoreProvider | None = None,
    data_loading_policy: DataEnsureLoadedPolicy | None = None,
    symbol_discovery_policy: DataSymbolDiscoveryPolicy | None = None,
    knowledge_store_provider: KnowledgeStoreProvider | None = None,
    research_artifact_store_provider: ResearchArtifactStoreProvider | None = None,
    backtest_config_provider: ToolConfigProvider | None = None,
    optimizer_registry: OptimizationEngineRegistry | None = None,
    tracking_sink_registry: ExperimentTrackingSinkRegistry | None = None,
    inference_adapter_registry: InferenceAdapterRegistry | None = None,
    prediction_mapper_catalog: PredictionMapperCatalog | None = None,
    coding_workspace_service_provider: CodingWorkspaceServiceProvider | None = None,
    optimization_trial_executor_factory: OptimizationTrialExecutorFactory | None = None,
) -> McpRuntimeDependencies:
    """Resolve injected overrides and trusted default runtime dependencies.

    Args:
        environment: Resolved MCP policy and configuration paths.
        event_store_provider: Optional event-store override.
        data_loading_policy: Optional Data loading-policy override.
        symbol_discovery_policy: Optional symbol-discovery policy override.
        knowledge_store_provider: Optional knowledge-store override.
        research_artifact_store_provider: Optional artifact-store override.
        backtest_config_provider: Optional Trader configuration override.
        optimizer_registry: Optional optimization-engine registry override.
        tracking_sink_registry: Optional tracking-sink registry override.
        inference_adapter_registry: Optional inference-adapter registry override.
        prediction_mapper_catalog: Optional prediction-mapper override.
        coding_workspace_service_provider: Optional Coding Workspace override.
        optimization_trial_executor_factory: Optional trial-executor override.

    Returns:
        Fully resolved dependency bundle for protocol registration.
    """
    return McpRuntimeDependencies(
        event_store_provider=event_store_provider
        or build_event_store_provider(environment),
        backtest_config_provider=backtest_config_provider
        or (lambda: load_tool_config(environment)),
        data_loading_policy=data_loading_policy
        or DataEnsureLoadedPolicy(
            allow_data_loading=environment.allow_data_loading,
            backfill_config_path=environment.trader_config_path,
        ),
        symbol_discovery_policy_provider=(
            (lambda: symbol_discovery_policy)
            if symbol_discovery_policy is not None
            else build_symbol_discovery_policy_provider(environment)
        ),
        knowledge_store_provider=knowledge_store_provider
        or build_knowledge_store_provider(environment),
        research_artifact_store_provider=research_artifact_store_provider
        or build_research_artifact_store_provider(environment),
        optimizer_registry=optimizer_registry or build_optimizer_registry(environment),
        tracking_sink_registry=tracking_sink_registry
        or build_tracking_sink_registry(environment),
        inference_adapter_registry=inference_adapter_registry
        or build_inference_adapter_registry(environment),
        prediction_mapper_catalog=prediction_mapper_catalog
        or MaintainedPredictionMapperCatalog(),
        coding_workspace_service_provider=(
            coding_workspace_service_provider
            if coding_workspace_service_provider is not None
            else build_coding_workspace_service_provider(environment)
        ),
        optimization_trial_executor_factory=(
            optimization_trial_executor_factory or build_optimization_trial_executor
        ),
    )


def build_event_store_provider(
    environment: McpEnvironment | None = None,
) -> EventStoreProvider:
    """Build the lazy event-store provider used by MCP capabilities."""
    local_env = environment or load_local_environment()
    if local_env.trader_config_path is None:
        return NoOpEventStore

    event_store: EventStore | None = None

    def _provider() -> EventStore:
        nonlocal event_store
        if event_store is None:
            event_store = build_event_store(load_tool_config(local_env))
        return event_store

    return _provider


def build_knowledge_store_provider(
    environment: McpEnvironment | None = None,
) -> KnowledgeStoreProvider:
    """Build the lazy knowledge-store provider used by knowledge capabilities."""
    local_env = environment or load_local_environment()
    backend = local_env.knowledge_store.strip().lower()
    if backend != "postgres":
        return lambda: UnavailableKnowledgeStore(
            f"Unsupported knowledge store backend: {local_env.knowledge_store}"
        )
    if local_env.trader_config_path is None:
        return lambda: UnavailableKnowledgeStore(
            "Postgres knowledge store requires TRADER_MCP_TRADER_CONFIG_PATH"
        )

    store: KnowledgeStore | None = None

    def _provider() -> KnowledgeStore:
        nonlocal store
        if store is None:
            try:
                config = load_tool_config(local_env)
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
    """Build the lazy canonical research-artifact store provider."""
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
                config = load_tool_config(local_env)
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
    """Build the lazy isolated Coding Workspace service provider."""
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


def build_symbol_discovery_policy_provider(
    environment: McpEnvironment | None = None,
) -> SymbolDiscoveryPolicyProvider:
    """Build the lazy symbol-discovery policy provider."""
    local_env = environment or load_local_environment()
    policy: DataSymbolDiscoveryPolicy | None = None

    def _provider() -> DataSymbolDiscoveryPolicy:
        nonlocal policy
        if policy is None:
            policy = build_symbol_discovery_policy(local_env)
        return policy

    return _provider


def build_symbol_discovery_policy(
    environment: McpEnvironment | None = None,
) -> DataSymbolDiscoveryPolicy:
    """Build the read-only symbol-discovery policy for the MCP runtime."""
    local_env = environment or load_local_environment()
    if (
        not local_env.allow_symbol_provider_discovery
        or local_env.trader_config_path is None
    ):
        return DataSymbolDiscoveryPolicy(
            allow_provider_discovery=local_env.allow_symbol_provider_discovery,
        )
    config = load_tool_config(local_env)
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


def build_optimizer_registry(environment: McpEnvironment) -> OptimizationEngineRegistry:
    """Build the registry of admitted optimization engines."""
    return OptimizationEngineRegistry(
        engines=[
            OptunaOptimizationEngine(
                storage_url=environment.optuna_storage_url,
                study_prefix=environment.optuna_study_prefix,
                schema_name=environment.optuna_schema,
                role_name=environment.optuna_role,
            )
        ]
    )


def build_tracking_sink_registry(
    environment: McpEnvironment,
) -> ExperimentTrackingSinkRegistry:
    """Build the registry of admitted experiment-tracking sinks."""
    return ExperimentTrackingSinkRegistry(
        sinks=[
            MLflowExperimentTrackingSink(
                tracking_uri=environment.mlflow_tracking_uri,
                experiment_name=environment.mlflow_optimization_experiment,
            )
        ]
    )


def build_inference_adapter_registry(
    environment: McpEnvironment,
) -> InferenceAdapterRegistry:
    """Build the registry of admitted model-inference adapters."""
    adapters = (
        (
            MLflowLocalPyfuncAdapter(
                profile_name=environment.mlflow_inference_profile,
                tracking_uri=environment.mlflow_tracking_uri,
            ),
        )
        if environment.mlflow_tracking_uri
        else ()
    )
    return InferenceAdapterRegistry(adapters=adapters)


def build_optimization_trial_executor(
    event_store: EventStore,
    config: Config,
    artifact_store: ResearchArtifactStore,
) -> OptimizationTrialExecutor:
    """Compose the Postgres-backed executor for one optimization trial."""
    return PostgresBacktestOptimizationTrialExecutor(
        event_store=event_store,
        config=config,
        artifact_store=artifact_store,
    )


def load_tool_config(environment: McpEnvironment) -> Config:
    """Load Trader config lazily without making MCP startup depend on it."""
    if environment.trader_config_path is None:
        raise ToolRuntimeConfigurationError(
            "Tool execution requires a trader config path."
        )
    _load_tool_env(environment)
    try:
        return build_config(load_yaml_config(environment.trader_config_path))
    except (OSError, ValueError) as exc:
        raise ToolRuntimeConfigurationError(
            f"Unable to build tool execution config from {environment.trader_config_path}: {exc}"
        ) from exc


def _load_tool_env(environment: McpEnvironment) -> None:
    """Load the optional tool-runtime env file used by Trader YAML expansion."""
    if environment.tool_env_path is None:
        return
    if not environment.tool_env_path.exists():
        raise ToolRuntimeConfigurationError(
            f"Tool runtime env file not found: {environment.tool_env_path}"
        )
    load_dotenv(environment.tool_env_path, override=False)
