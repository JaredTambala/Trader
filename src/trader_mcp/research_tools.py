"""MCP registrations for canonical Supervisor research tools."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import anyio
from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult

from trader.config import Config
from trader.event_store import EventStore
from trader.predictions import PredictionRuntimeResolver
from trader_mcp.adapters import result_to_mcp_result
from trader_mcp.contracts import SideEffect, ToolEnvelope, error_envelope
from trader_mcp.constants import (
    MATH_TOOL_DESCRIPTIONS,
    RESEARCH_COMPARE_BACKTEST_RESULTS_TOOL,
    RESEARCH_COMPARE_IMPLEMENTATION_TOOL,
    RESEARCH_CREATE_BACKTEST_SPECIFICATION_TOOL,
    RESEARCH_CREATE_PARAMETER_OPTIMIZATION_PLAN_TOOL,
    RESEARCH_CREATE_RISK_STACK_SPECIFICATION_TOOL,
    RESEARCH_CREATE_STRATEGY_SPECIFICATION_TOOL,
    RESEARCH_GET_BACKTEST_RESULTS_TOOL,
    RESEARCH_GET_IMPLEMENTATION_TOOL,
    RESEARCH_GET_OPTIMIZER_RUNTIME_TOOL,
    RESEARCH_GET_PARAMETER_OPTIMIZATION_RESULTS_TOOL,
    RESEARCH_LIST_RISK_MANAGER_TEMPLATES_TOOL,
    RESEARCH_LIST_STRATEGY_TEMPLATES_TOOL,
    RESEARCH_PROJECT_EXPERIMENT_TRACKING_TOOL,
    RESEARCH_REGISTER_OPTIMIZATION_OBJECTIVE_TOOL,
    RESEARCH_REGISTER_RISK_MANAGER_IMPLEMENTATION_TOOL,
    RESEARCH_REGISTER_STRATEGY_IMPLEMENTATION_TOOL,
    RESEARCH_RUN_BACKTEST_SPECIFICATION_TOOL,
    RESEARCH_RUN_PARAMETER_OPTIMIZATION_TOOL,
    RESEARCH_RUN_PARAMETER_OPTIMIZATION_VARIANTS_TOOL,
    RESEARCH_SEARCH_IMPLEMENTATIONS_TOOL,
    RESEARCH_TOOL_DESCRIPTIONS,
    RESEARCH_VALIDATE_BACKTEST_SPECIFICATION_TOOL,
    RESEARCH_VALIDATE_OPTIMIZATION_OBJECTIVE_TOOL,
    RESEARCH_VALIDATE_RISK_MANAGER_IMPLEMENTATION_TOOL,
    RESEARCH_VALIDATE_RISK_STACK_SPECIFICATION_TOOL,
    RESEARCH_VALIDATE_STRATEGY_IMPLEMENTATION_TOOL,
    RESEARCH_VALIDATE_STRATEGY_SPECIFICATION_TOOL,
)
from trader_mcp.environment import McpEnvironment
from trader_research.experiments import (
    ExperimentTrackingSinkRegistry,
    ImplementationComparisonRequest,
    ImplementationSearchRequest,
    OptimizationEngineRegistry,
    compare_backtest_results,
    compare_implementation,
    create_backtest_specification,
    create_parameter_optimization_plan,
    create_risk_stack_specification,
    create_strategy_specification,
    get_backtest_results,
    get_implementation,
    get_optimizer_runtime,
    get_parameter_optimization_results,
    list_risk_manager_templates,
    list_strategy_templates,
    project_experiment_tracking,
    register_optimization_objective,
    register_risk_manager_implementation,
    register_strategy_implementation,
    required_optimizer_profiles_for_variants,
    run_backtest_specification,
    run_parameter_optimization,
    run_parameter_optimization_variants,
    search_implementations,
    validate_backtest_specification,
    validate_optimization_objective,
    validate_risk_manager_implementation,
    validate_risk_stack_specification,
    validate_strategy_implementation,
    validate_strategy_specification,
)
from trader_research.foundation import (
    ApplicationResult,
    ContextualResearchArtifactStore,
    PredictionDeploymentReader,
    PredictionMapperCatalog,
    ResearchArtifactStore,
)
from trader_research.infrastructure.execution import (
    PostgresBacktestOptimizationTrialExecutor,
)


EventStoreProvider = Callable[[], EventStore]
ToolConfigProvider = Callable[[], Config]
ResearchArtifactStoreProvider = Callable[[], ResearchArtifactStore]
PredictionDeploymentReaderProvider = Callable[[], PredictionDeploymentReader]
PredictionRuntimeResolverProvider = Callable[[], PredictionRuntimeResolver]
ServiceResult = ApplicationResult | ToolEnvelope


def register_research_tools(
    server: FastMCP,
    environment: McpEnvironment,
    *,
    event_store_provider: EventStoreProvider | None = None,
    backtest_config_provider: ToolConfigProvider | None = None,
    artifact_store_provider: ResearchArtifactStoreProvider | None = None,
    optimizer_registry: OptimizationEngineRegistry | None = None,
    tracking_sink_registry: ExperimentTrackingSinkRegistry | None = None,
    prediction_deployment_reader_provider: PredictionDeploymentReaderProvider | None = None,
    prediction_mapper_catalog: PredictionMapperCatalog | None = None,
    prediction_runtime_resolver_provider: PredictionRuntimeResolverProvider | None = None,
) -> None:
    """Register implementation, specification, backtest, and optimisation tools."""
    engines = optimizer_registry or OptimizationEngineRegistry()
    sinks = tracking_sink_registry or ExperimentTrackingSinkRegistry()

    def _store(
        requested_by: str | None = None,
        actor: str | None = None,
    ) -> ResearchArtifactStore | None:
        if (requested_by is None) != (actor is None):
            raise ValueError(
                "requested_by and actor must be supplied together"
            )
        if artifact_store_provider is None:
            return None
        store = artifact_store_provider()
        if requested_by is None and actor is None:
            return store
        assert requested_by is not None and actor is not None
        return ContextualResearchArtifactStore(
            store,
            requested_by=requested_by,
            actor=actor,
        )

    def _result(result: ServiceResult) -> CallToolResult:
        return CallToolResult(**result_to_mcp_result(result))

    def _prediction_reader() -> PredictionDeploymentReader | None:
        return (
            prediction_deployment_reader_provider()
            if prediction_deployment_reader_provider is not None
            else None
        )

    def _blocked(
        command: str, code: str, message: str, side_effect: SideEffect
    ) -> CallToolResult:
        return _result(
            error_envelope(
                command=command, side_effect=side_effect, code=code, message=message
            )
        )

    def _implementation_registration(
        service: Callable[..., ApplicationResult], **kwargs: Any
    ) -> CallToolResult:
        return _result(service(**kwargs, artifact_store=_store()))

    def _runtime_error(
        command: str, *, optimization: bool = False
    ) -> CallToolResult | None:
        if event_store_provider is None or backtest_config_provider is None:
            return _blocked(
                command,
                "tool_runtime_configuration_error",
                "Execution requires configured event-store and Trader config providers.",
                SideEffect.LOCAL_MUTATING,
            )
        if not environment.allow_backtests:
            return _blocked(
                command,
                "backtests_not_allowed",
                "Backtest execution requires TRADER_MCP_ALLOW_BACKTESTS=true.",
                SideEffect.LOCAL_MUTATING,
            )
        if optimization and not environment.allow_optimization:
            return _blocked(
                command,
                "optimization_not_allowed",
                "Optimization execution requires TRADER_MCP_ALLOW_OPTIMIZATION=true.",
                SideEffect.LOCAL_MUTATING,
            )
        return None

    @server.tool(
        name=RESEARCH_LIST_STRATEGY_TEMPLATES_TOOL,
        description=RESEARCH_TOOL_DESCRIPTIONS[RESEARCH_LIST_STRATEGY_TEMPLATES_TOOL],
    )
    def research_list_strategy_templates(
        families: list[str] | None = None,
    ) -> CallToolResult:
        return _result(list_strategy_templates(families=families))

    @server.tool(
        name=RESEARCH_LIST_RISK_MANAGER_TEMPLATES_TOOL,
        description=RESEARCH_TOOL_DESCRIPTIONS[
            RESEARCH_LIST_RISK_MANAGER_TEMPLATES_TOOL
        ],
    )
    def research_list_risk_manager_templates(
        families: list[str] | None = None,
    ) -> CallToolResult:
        return _result(list_risk_manager_templates(families=families))

    @server.tool(
        name=RESEARCH_SEARCH_IMPLEMENTATIONS_TOOL,
        description=RESEARCH_TOOL_DESCRIPTIONS[
            RESEARCH_SEARCH_IMPLEMENTATIONS_TOOL
        ],
    )
    def research_search_implementations(
        query: str = "",
        implementation_kinds: list[str] | None = None,
        capabilities: list[str] | None = None,
        runtime_contract: str | None = None,
        include_unadmitted: bool = False,
        limit: int = 20,
    ) -> CallToolResult:
        """Search maintained and canonical implementation catalogue tiers."""
        store = _store()
        if store is None:
            return _blocked(
                RESEARCH_SEARCH_IMPLEMENTATIONS_TOOL,
                "research_artifact_store_required",
                "Implementation search requires a configured ResearchArtifactStore.",
                SideEffect.READ_ONLY,
            )
        try:
            search_request = ImplementationSearchRequest(
                query=query,
                implementation_kinds=tuple(
                    implementation_kinds or ("strategy", "risk_manager")
                ),
                capabilities=tuple(capabilities or ()),
                runtime_contract=runtime_contract,
                include_unadmitted=include_unadmitted,
                limit=limit,
            )
        except ValueError as exc:
            return _blocked(
                RESEARCH_SEARCH_IMPLEMENTATIONS_TOOL,
                "invalid_implementation_search",
                str(exc),
                SideEffect.READ_ONLY,
            )
        return _result(search_implementations(store, search_request))

    @server.tool(
        name=RESEARCH_GET_IMPLEMENTATION_TOOL,
        description=RESEARCH_TOOL_DESCRIPTIONS[RESEARCH_GET_IMPLEMENTATION_TOOL],
    )
    def research_get_implementation(
        implementation_ref: str,
        include_source: bool = False,
    ) -> CallToolResult:
        """Resolve one exact implementation and its reuse eligibility."""
        store = _store()
        if store is None:
            return _blocked(
                RESEARCH_GET_IMPLEMENTATION_TOOL,
                "research_artifact_store_required",
                "Implementation resolution requires a configured ResearchArtifactStore.",
                SideEffect.READ_ONLY,
            )
        return _result(
            get_implementation(
                store,
                implementation_ref,
                include_source=include_source,
            )
        )

    @server.tool(
        name=RESEARCH_COMPARE_IMPLEMENTATION_TOOL,
        description=RESEARCH_TOOL_DESCRIPTIONS[
            RESEARCH_COMPARE_IMPLEMENTATION_TOOL
        ],
    )
    def research_compare_implementation(
        implementation_ref: str,
        build_contract: dict[str, Any],
    ) -> CallToolResult:
        """Compare one exact version with a normalized build contract."""
        store = _store()
        if store is None:
            return _blocked(
                RESEARCH_COMPARE_IMPLEMENTATION_TOOL,
                "research_artifact_store_required",
                "Implementation comparison requires a configured ResearchArtifactStore.",
                SideEffect.READ_ONLY,
            )
        try:
            comparison_request = ImplementationComparisonRequest(
                implementation_ref=implementation_ref,
                build_contract=build_contract,
            )
        except ValueError as exc:
            return _blocked(
                RESEARCH_COMPARE_IMPLEMENTATION_TOOL,
                "invalid_implementation_comparison",
                str(exc),
                SideEffect.READ_ONLY,
            )
        return _result(compare_implementation(store, comparison_request))

    def _register(
        service: Callable[..., ApplicationResult],
        *,
        name: str,
        version: str,
        source_code: str,
        factory_name: str,
        class_name: str | None,
        parameter_schema: dict[str, Any] | None,
        dependencies: list[str] | None,
        authoring_origin: str,
        capabilities: list[str] | None,
        runtime_requirements: dict[str, Any] | None,
        resource_bounds: dict[str, Any] | None,
        provenance_refs: list[dict[str, Any]] | None,
        metadata: dict[str, Any] | None,
    ) -> CallToolResult:
        return _implementation_registration(
            service,
            name=name,
            version=version,
            source_code=source_code,
            factory_name=factory_name,
            class_name=class_name,
            parameter_schema=parameter_schema,
            dependencies=dependencies,
            authoring_origin=authoring_origin,
            capabilities=capabilities,
            runtime_requirements=runtime_requirements,
            resource_bounds=resource_bounds,
            provenance_refs=provenance_refs,
            metadata=metadata,
        )

    @server.tool(
        name=RESEARCH_REGISTER_STRATEGY_IMPLEMENTATION_TOOL,
        description=RESEARCH_TOOL_DESCRIPTIONS[
            RESEARCH_REGISTER_STRATEGY_IMPLEMENTATION_TOOL
        ],
    )
    def research_register_strategy_implementation(
        name: str,
        version: str,
        source_code: str,
        factory_name: str,
        class_name: str | None = None,
        parameter_schema: dict[str, Any] | None = None,
        dependencies: list[str] | None = None,
        authoring_origin: str = "supplied",
        capabilities: list[str] | None = None,
        runtime_requirements: dict[str, Any] | None = None,
        resource_bounds: dict[str, Any] | None = None,
        provenance_refs: list[dict[str, Any]] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> CallToolResult:
        return _register(
            register_strategy_implementation,
            name=name,
            version=version,
            source_code=source_code,
            factory_name=factory_name,
            class_name=class_name,
            parameter_schema=parameter_schema,
            dependencies=dependencies,
            authoring_origin=authoring_origin,
            capabilities=capabilities,
            runtime_requirements=runtime_requirements,
            resource_bounds=resource_bounds,
            provenance_refs=provenance_refs,
            metadata=metadata,
        )

    @server.tool(
        name=RESEARCH_REGISTER_RISK_MANAGER_IMPLEMENTATION_TOOL,
        description=RESEARCH_TOOL_DESCRIPTIONS[
            RESEARCH_REGISTER_RISK_MANAGER_IMPLEMENTATION_TOOL
        ],
    )
    def research_register_risk_manager_implementation(
        name: str,
        version: str,
        source_code: str,
        factory_name: str,
        class_name: str | None = None,
        parameter_schema: dict[str, Any] | None = None,
        dependencies: list[str] | None = None,
        authoring_origin: str = "supplied",
        capabilities: list[str] | None = None,
        runtime_requirements: dict[str, Any] | None = None,
        resource_bounds: dict[str, Any] | None = None,
        provenance_refs: list[dict[str, Any]] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> CallToolResult:
        return _register(
            register_risk_manager_implementation,
            name=name,
            version=version,
            source_code=source_code,
            factory_name=factory_name,
            class_name=class_name,
            parameter_schema=parameter_schema,
            dependencies=dependencies,
            authoring_origin=authoring_origin,
            capabilities=capabilities,
            runtime_requirements=runtime_requirements,
            resource_bounds=resource_bounds,
            provenance_refs=provenance_refs,
            metadata=metadata,
        )

    @server.tool(
        name=RESEARCH_REGISTER_OPTIMIZATION_OBJECTIVE_TOOL,
        description=MATH_TOOL_DESCRIPTIONS[
            RESEARCH_REGISTER_OPTIMIZATION_OBJECTIVE_TOOL
        ],
    )
    def research_register_optimization_objective(
        name: str,
        version: str,
        source_code: str,
        factory_name: str,
        class_name: str | None = None,
        parameter_schema: dict[str, Any] | None = None,
        dependencies: list[str] | None = None,
        authoring_origin: str = "supplied",
        capabilities: list[str] | None = None,
        runtime_requirements: dict[str, Any] | None = None,
        resource_bounds: dict[str, Any] | None = None,
        provenance_refs: list[dict[str, Any]] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> CallToolResult:
        return _register(
            register_optimization_objective,
            name=name,
            version=version,
            source_code=source_code,
            factory_name=factory_name,
            class_name=class_name,
            parameter_schema=parameter_schema,
            dependencies=dependencies,
            authoring_origin=authoring_origin,
            capabilities=capabilities,
            runtime_requirements=runtime_requirements,
            resource_bounds=resource_bounds,
            provenance_refs=provenance_refs,
            metadata=metadata,
        )

    def _validate(
        service: Callable[..., ApplicationResult],
        *,
        implementation_version_id: str | None,
        implementation_version_uri: str | None,
        implementation_version: dict[str, Any] | None,
        fixture_parameters: dict[str, Any] | None,
        requested_by: str | None,
        actor: str | None,
    ) -> CallToolResult:
        return _result(
            service(
                implementation_version_id=implementation_version_id,
                implementation_version_uri=implementation_version_uri,
                implementation_version=implementation_version,
                fixture_parameters=fixture_parameters,
                artifact_store=_store(requested_by, actor),
            )
        )

    @server.tool(
        name=RESEARCH_VALIDATE_STRATEGY_IMPLEMENTATION_TOOL,
        description=RESEARCH_TOOL_DESCRIPTIONS[
            RESEARCH_VALIDATE_STRATEGY_IMPLEMENTATION_TOOL
        ],
    )
    def research_validate_strategy_implementation(
        implementation_version_id: str | None = None,
        implementation_version_uri: str | None = None,
        implementation_version: dict[str, Any] | None = None,
        fixture_parameters: dict[str, Any] | None = None,
        requested_by: str | None = None,
        actor: str | None = None,
    ) -> CallToolResult:
        return _validate(
            validate_strategy_implementation,
            implementation_version_id=implementation_version_id,
            implementation_version_uri=implementation_version_uri,
            implementation_version=implementation_version,
            fixture_parameters=fixture_parameters,
            requested_by=requested_by,
            actor=actor,
        )

    @server.tool(
        name=RESEARCH_VALIDATE_RISK_MANAGER_IMPLEMENTATION_TOOL,
        description=RESEARCH_TOOL_DESCRIPTIONS[
            RESEARCH_VALIDATE_RISK_MANAGER_IMPLEMENTATION_TOOL
        ],
    )
    def research_validate_risk_manager_implementation(
        implementation_version_id: str | None = None,
        implementation_version_uri: str | None = None,
        implementation_version: dict[str, Any] | None = None,
        fixture_parameters: dict[str, Any] | None = None,
        requested_by: str | None = None,
        actor: str | None = None,
    ) -> CallToolResult:
        return _validate(
            validate_risk_manager_implementation,
            implementation_version_id=implementation_version_id,
            implementation_version_uri=implementation_version_uri,
            implementation_version=implementation_version,
            fixture_parameters=fixture_parameters,
            requested_by=requested_by,
            actor=actor,
        )

    @server.tool(
        name=RESEARCH_VALIDATE_OPTIMIZATION_OBJECTIVE_TOOL,
        description=MATH_TOOL_DESCRIPTIONS[
            RESEARCH_VALIDATE_OPTIMIZATION_OBJECTIVE_TOOL
        ],
    )
    def research_validate_optimization_objective(
        implementation_version_id: str | None = None,
        implementation_version_uri: str | None = None,
        implementation_version: dict[str, Any] | None = None,
        fixture_parameters: dict[str, Any] | None = None,
        requested_by: str | None = None,
        actor: str | None = None,
    ) -> CallToolResult:
        return _validate(
            validate_optimization_objective,
            implementation_version_id=implementation_version_id,
            implementation_version_uri=implementation_version_uri,
            implementation_version=implementation_version,
            fixture_parameters=fixture_parameters,
            requested_by=requested_by,
            actor=actor,
        )

    @server.tool(
        name=RESEARCH_CREATE_STRATEGY_SPECIFICATION_TOOL,
        description=RESEARCH_TOOL_DESCRIPTIONS[
            RESEARCH_CREATE_STRATEGY_SPECIFICATION_TOOL
        ],
    )
    def research_create_strategy_specification(
        implementation_validation_ref: str,
        parameters: dict[str, Any] | None = None,
        sizing: dict[str, Any] | None = None,
        portfolio_mode: str = "single_or_multi_asset",
        required_runtime_context: dict[str, Any] | None = None,
        execution_assumptions: dict[str, Any] | None = None,
        tunable_fields: list[str] | None = None,
        provenance_refs: list[dict[str, Any]] | None = None,
        prediction_bindings: list[dict[str, Any]] | None = None,
        requested_by: str | None = None,
        actor: str | None = None,
    ) -> CallToolResult:
        return _result(
            create_strategy_specification(
                implementation_validation_ref=implementation_validation_ref,
                parameters=parameters,
                sizing=sizing,
                portfolio_mode=portfolio_mode,
                required_runtime_context=required_runtime_context,
                execution_assumptions=execution_assumptions,
                tunable_fields=tunable_fields,
                provenance_refs=provenance_refs,
                prediction_bindings=prediction_bindings,
                prediction_deployment_reader=_prediction_reader(),
                prediction_mapper_catalog=prediction_mapper_catalog,
                artifact_store=_store(requested_by, actor),
            )
        )

    @server.tool(
        name=RESEARCH_VALIDATE_STRATEGY_SPECIFICATION_TOOL,
        description=RESEARCH_TOOL_DESCRIPTIONS[
            RESEARCH_VALIDATE_STRATEGY_SPECIFICATION_TOOL
        ],
    )
    def research_validate_strategy_specification(
        strategy_specification_id: str | None = None,
        strategy_specification_uri: str | None = None,
        strategy_specification: dict[str, Any] | None = None,
        requested_by: str | None = None,
        actor: str | None = None,
    ) -> CallToolResult:
        return _result(
            validate_strategy_specification(
                strategy_specification_id=strategy_specification_id,
                strategy_specification_uri=strategy_specification_uri,
                strategy_specification=strategy_specification,
                prediction_deployment_reader=_prediction_reader(),
                prediction_mapper_catalog=prediction_mapper_catalog,
                artifact_store=_store(requested_by, actor),
            )
        )

    @server.tool(
        name=RESEARCH_CREATE_RISK_STACK_SPECIFICATION_TOOL,
        description=RESEARCH_TOOL_DESCRIPTIONS[
            RESEARCH_CREATE_RISK_STACK_SPECIFICATION_TOOL
        ],
    )
    def research_create_risk_stack_specification(
        risk_managers: list[dict[str, Any]],
        execution_assumptions: dict[str, Any] | None = None,
        provenance_refs: list[dict[str, Any]] | None = None,
        requested_by: str | None = None,
        actor: str | None = None,
    ) -> CallToolResult:
        return _result(
            create_risk_stack_specification(
                risk_managers=risk_managers,
                execution_assumptions=execution_assumptions,
                provenance_refs=provenance_refs,
                artifact_store=_store(requested_by, actor),
            )
        )

    @server.tool(
        name=RESEARCH_VALIDATE_RISK_STACK_SPECIFICATION_TOOL,
        description=RESEARCH_TOOL_DESCRIPTIONS[
            RESEARCH_VALIDATE_RISK_STACK_SPECIFICATION_TOOL
        ],
    )
    def research_validate_risk_stack_specification(
        risk_stack_specification_id: str | None = None,
        risk_stack_specification_uri: str | None = None,
        risk_stack_specification: dict[str, Any] | None = None,
        requested_by: str | None = None,
        actor: str | None = None,
    ) -> CallToolResult:
        return _result(
            validate_risk_stack_specification(
                risk_stack_specification_id=risk_stack_specification_id,
                risk_stack_specification_uri=risk_stack_specification_uri,
                risk_stack_specification=risk_stack_specification,
                artifact_store=_store(requested_by, actor),
            )
        )

    @server.tool(
        name=RESEARCH_CREATE_BACKTEST_SPECIFICATION_TOOL,
        description=RESEARCH_TOOL_DESCRIPTIONS[
            RESEARCH_CREATE_BACKTEST_SPECIFICATION_TOOL
        ],
    )
    def research_create_backtest_specification(
        strategy_specification_validation_ref: str,
        dataset_manifest: dict[str, Any],
        data_quality_report: dict[str, Any],
        risk_stack_specification_validation_ref: str | None = None,
        assumptions: dict[str, Any] | None = None,
        initial_cash: float = 100_000.0,
        initial_positions: list[dict[str, Any]] | None = None,
        benchmark: dict[str, Any] | None = None,
        deterministic_seed: int = 0,
        max_runs: int | None = None,
        log_cycle_details: bool = False,
        runtime_limits: dict[str, Any] | None = None,
        parent_specification_ref: str | None = None,
        selection_origin_ref: str | None = None,
        variant_reason: str | None = None,
        requested_by: str | None = None,
        actor: str | None = None,
    ) -> CallToolResult:
        return _result(
            create_backtest_specification(
                strategy_specification_validation_ref=strategy_specification_validation_ref,
                dataset_manifest=dataset_manifest,
                data_quality_report=data_quality_report,
                risk_stack_specification_validation_ref=risk_stack_specification_validation_ref,
                assumptions=assumptions,
                initial_cash=initial_cash,
                initial_positions=initial_positions,
                benchmark=benchmark,
                deterministic_seed=deterministic_seed,
                max_runs=max_runs,
                log_cycle_details=log_cycle_details,
                runtime_limits=runtime_limits,
                parent_specification_ref=parent_specification_ref,
                selection_origin_ref=selection_origin_ref,
                variant_reason=variant_reason,
                prediction_deployment_reader=_prediction_reader(),
                prediction_mapper_catalog=prediction_mapper_catalog,
                artifact_store=_store(requested_by, actor),
            )
        )

    @server.tool(
        name=RESEARCH_VALIDATE_BACKTEST_SPECIFICATION_TOOL,
        description=RESEARCH_TOOL_DESCRIPTIONS[
            RESEARCH_VALIDATE_BACKTEST_SPECIFICATION_TOOL
        ],
    )
    def research_validate_backtest_specification(
        backtest_specification_id: str | None = None,
        backtest_specification_uri: str | None = None,
        backtest_specification: dict[str, Any] | None = None,
        requested_by: str | None = None,
        actor: str | None = None,
    ) -> CallToolResult:
        return _result(
            validate_backtest_specification(
                backtest_specification_id=backtest_specification_id,
                backtest_specification_uri=backtest_specification_uri,
                backtest_specification=backtest_specification,
                prediction_deployment_reader=_prediction_reader(),
                prediction_mapper_catalog=prediction_mapper_catalog,
                artifact_store=_store(requested_by, actor),
            )
        )

    @server.tool(
        name=RESEARCH_RUN_BACKTEST_SPECIFICATION_TOOL,
        description=RESEARCH_TOOL_DESCRIPTIONS[
            RESEARCH_RUN_BACKTEST_SPECIFICATION_TOOL
        ],
    )
    async def research_run_backtest_specification(
        backtest_specification_validation_ref: str,
        requested_by: str | None = None,
        actor: str | None = None,
    ) -> CallToolResult:
        blocked = _runtime_error(RESEARCH_RUN_BACKTEST_SPECIFICATION_TOOL)
        if blocked is not None:
            return blocked

        def _run() -> ApplicationResult:
            assert (
                event_store_provider is not None
                and backtest_config_provider is not None
            )
            return run_backtest_specification(
                event_store=event_store_provider(),
                config=backtest_config_provider(),
                backtest_specification_validation_ref=backtest_specification_validation_ref,
                prediction_deployment_reader=_prediction_reader(),
                prediction_mapper_catalog=prediction_mapper_catalog,
                prediction_runtime_resolver=(
                    prediction_runtime_resolver_provider()
                    if environment.allow_ml_runtime
                    and prediction_runtime_resolver_provider is not None
                    else None
                ),
                artifact_store=_store(requested_by, actor),
            )

        return _result(await anyio.to_thread.run_sync(_run))

    @server.tool(
        name=RESEARCH_GET_BACKTEST_RESULTS_TOOL,
        description=RESEARCH_TOOL_DESCRIPTIONS[RESEARCH_GET_BACKTEST_RESULTS_TOOL],
    )
    def research_get_backtest_results(
        run_id: str | None = None,
        backtest_run_uri: str | None = None,
    ) -> CallToolResult:
        return _result(
            get_backtest_results(
                run_id=run_id,
                backtest_run_uri=backtest_run_uri,
                artifact_store=_store(),
            )
        )

    @server.tool(
        name=RESEARCH_COMPARE_BACKTEST_RESULTS_TOOL,
        description=RESEARCH_TOOL_DESCRIPTIONS[RESEARCH_COMPARE_BACKTEST_RESULTS_TOOL],
    )
    def research_compare_backtest_results(
        backtest_run_refs: list[str],
        ranking_metric: str = "sharpe",
        sort_order: str = "descending",
    ) -> CallToolResult:
        return _result(
            compare_backtest_results(
                backtest_run_refs=backtest_run_refs,
                ranking_metric=ranking_metric,
                sort_order=sort_order,
                artifact_store=_store(),
            )
        )

    @server.tool(
        name=RESEARCH_GET_OPTIMIZER_RUNTIME_TOOL,
        description=RESEARCH_TOOL_DESCRIPTIONS[RESEARCH_GET_OPTIMIZER_RUNTIME_TOOL],
    )
    def research_get_optimizer_runtime() -> CallToolResult:
        return _result(get_optimizer_runtime(engine_registry=engines))

    @server.tool(
        name=RESEARCH_CREATE_PARAMETER_OPTIMIZATION_PLAN_TOOL,
        description=RESEARCH_TOOL_DESCRIPTIONS[
            RESEARCH_CREATE_PARAMETER_OPTIMIZATION_PLAN_TOOL
        ],
    )
    def research_create_parameter_optimization_plan(
        base_backtest_specification_validation_ref: str,
        holdout_dataset_manifest: dict[str, Any],
        holdout_data_quality_report: dict[str, Any],
        objective_validation_ref: str,
        search_space: list[dict[str, Any]],
        direction: str = "maximize",
        constraints: list[dict[str, Any]] | None = None,
        seed: int = 0,
        max_trials: int = 25,
        resource_limits: dict[str, Any] | None = None,
        parent_plan_ref: str | None = None,
        variant_reason: str | None = None,
        requested_by: str | None = None,
        actor: str | None = None,
    ) -> CallToolResult:
        return _result(
            create_parameter_optimization_plan(
                base_backtest_specification_validation_ref=base_backtest_specification_validation_ref,
                holdout_dataset_manifest=holdout_dataset_manifest,
                holdout_data_quality_report=holdout_data_quality_report,
                objective_validation_ref=objective_validation_ref,
                search_space=search_space,
                direction=direction,
                constraints=constraints,
                seed=seed,
                max_trials=max_trials,
                resource_limits=resource_limits,
                parent_plan_ref=parent_plan_ref,
                variant_reason=variant_reason,
                artifact_store=_store(requested_by, actor),
            )
        )

    @server.tool(
        name=RESEARCH_RUN_PARAMETER_OPTIMIZATION_TOOL,
        description=RESEARCH_TOOL_DESCRIPTIONS[
            RESEARCH_RUN_PARAMETER_OPTIMIZATION_TOOL
        ],
    )
    async def research_run_parameter_optimization(
        optimization_plan_ref: str,
        optimizer_profile: str = "builtin_random",
        max_new_trials: int | None = None,
        requested_by: str | None = None,
        actor: str | None = None,
    ) -> CallToolResult:
        blocked = _runtime_error(
            RESEARCH_RUN_PARAMETER_OPTIMIZATION_TOOL, optimization=True
        )
        if blocked is not None:
            return blocked
        if _is_optuna_profile(engines, optimizer_profile) and (
            not environment.allow_external_research_writes
            or not environment.allow_optuna_writes
        ):
            return _blocked(
                RESEARCH_RUN_PARAMETER_OPTIMIZATION_TOOL,
                "optuna_writes_not_allowed",
                (
                    "Optuna execution requires TRADER_MCP_ALLOW_EXTERNAL_RESEARCH_WRITES=true "
                    "and TRADER_MCP_ALLOW_OPTUNA_WRITES=true."
                ),
                SideEffect.LOCAL_MUTATING,
            )

        def _run() -> ServiceResult:
            assert (
                event_store_provider is not None
                and backtest_config_provider is not None
            )
            store = _store(requested_by, actor)
            if store is None:
                return _blocked_envelope(
                    RESEARCH_RUN_PARAMETER_OPTIMIZATION_TOOL,
                    "research_artifact_store_required",
                    "A ResearchArtifactStore is required.",
                )
            executor = PostgresBacktestOptimizationTrialExecutor(
                event_store=event_store_provider(),
                config=backtest_config_provider(),
                artifact_store=store,
            )
            return run_parameter_optimization(
                optimization_plan_ref=optimization_plan_ref,
                optimizer_profile=optimizer_profile,
                trial_executor=executor,
                artifact_store=store,
                engine_registry=engines,
                max_new_trials=max_new_trials,
            )

        return _result(await anyio.to_thread.run_sync(_run))

    @server.tool(
        name=RESEARCH_GET_PARAMETER_OPTIMIZATION_RESULTS_TOOL,
        description=RESEARCH_TOOL_DESCRIPTIONS[
            RESEARCH_GET_PARAMETER_OPTIMIZATION_RESULTS_TOOL
        ],
    )
    def research_get_parameter_optimization_results(
        optimization_run_ref: str,
    ) -> CallToolResult:
        return _result(
            get_parameter_optimization_results(
                optimization_run_ref=optimization_run_ref,
                artifact_store=_store(),
            )
        )

    @server.tool(
        name=RESEARCH_RUN_PARAMETER_OPTIMIZATION_VARIANTS_TOOL,
        description=RESEARCH_TOOL_DESCRIPTIONS[
            RESEARCH_RUN_PARAMETER_OPTIMIZATION_VARIANTS_TOOL
        ],
    )
    async def research_run_parameter_optimization_variants(
        audit_plan_ref: str,
        requested_by: str | None = None,
        actor: str | None = None,
    ) -> CallToolResult:
        blocked = _runtime_error(
            RESEARCH_RUN_PARAMETER_OPTIMIZATION_VARIANTS_TOOL, optimization=True
        )
        if blocked is not None:
            return blocked

        def _run() -> ServiceResult:
            assert (
                event_store_provider is not None
                and backtest_config_provider is not None
            )
            store = _store(requested_by, actor)
            if store is None:
                return _blocked_envelope(
                    RESEARCH_RUN_PARAMETER_OPTIMIZATION_VARIANTS_TOOL,
                    "research_artifact_store_required",
                    "A ResearchArtifactStore is required.",
                )
            try:
                profiles = required_optimizer_profiles_for_variants(
                    audit_plan_ref=audit_plan_ref,
                    artifact_store=store,
                )
            except Exception as exc:
                return _blocked_envelope(
                    RESEARCH_RUN_PARAMETER_OPTIMIZATION_VARIANTS_TOOL,
                    "parameter_optimization_variants_failed",
                    str(exc),
                )
            if any(_is_optuna_profile(engines, profile) for profile in profiles) and (
                not environment.allow_external_research_writes
                or not environment.allow_optuna_writes
            ):
                return _blocked_envelope(
                    RESEARCH_RUN_PARAMETER_OPTIMIZATION_VARIANTS_TOOL,
                    "optuna_writes_not_allowed",
                    (
                        "Optuna variant execution requires TRADER_MCP_ALLOW_EXTERNAL_RESEARCH_WRITES=true "
                        "and TRADER_MCP_ALLOW_OPTUNA_WRITES=true."
                    ),
                )
            executor = PostgresBacktestOptimizationTrialExecutor(
                event_store=event_store_provider(),
                config=backtest_config_provider(),
                artifact_store=store,
            )
            return run_parameter_optimization_variants(
                audit_plan_ref=audit_plan_ref,
                trial_executor=executor,
                artifact_store=store,
                engine_registry=engines,
            )

        return _result(await anyio.to_thread.run_sync(_run))

    @server.tool(
        name=RESEARCH_PROJECT_EXPERIMENT_TRACKING_TOOL,
        description=RESEARCH_TOOL_DESCRIPTIONS[
            RESEARCH_PROJECT_EXPERIMENT_TRACKING_TOOL
        ],
    )
    async def research_project_experiment_tracking(
        canonical_run_ref: str,
        tracking_profile: str,
    ) -> CallToolResult:
        if (
            not environment.allow_external_research_writes
            or not environment.allow_experiment_tracking_writes
        ):
            return _blocked(
                RESEARCH_PROJECT_EXPERIMENT_TRACKING_TOOL,
                "experiment_tracking_writes_not_allowed",
                (
                    "Tracking projection requires TRADER_MCP_ALLOW_EXTERNAL_RESEARCH_WRITES=true "
                    "and TRADER_MCP_ALLOW_EXPERIMENT_TRACKING_WRITES=true."
                ),
                SideEffect.EXTERNAL_RESEARCH_MUTATING,
            )

        def _run() -> ApplicationResult:
            return project_experiment_tracking(
                canonical_run_ref=canonical_run_ref,
                tracking_profile=tracking_profile,
                artifact_store=_store(),
                sink_registry=sinks,
            )

        return _result(await anyio.to_thread.run_sync(_run))


def _blocked_envelope(command: str, code: str, message: str) -> ToolEnvelope:
    return error_envelope(
        command=command,
        side_effect=SideEffect.LOCAL_MUTATING,
        code=code,
        message=message,
    )


def _is_optuna_profile(registry: OptimizationEngineRegistry, profile_name: str) -> bool:
    return any(
        profile.profile_name == profile_name and profile.provider == "optuna"
        for profile in registry.profiles()
    )
