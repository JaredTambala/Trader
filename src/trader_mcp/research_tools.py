"""MCP registrations for Quant Research Supervisor research tools."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import anyio
from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult

from trader.config import Config
from trader.event_store import EventStore
from trader_mcp.adapters import envelope_to_mcp_result
from trader_mcp.constants import (
    RESEARCH_COMPARE_BACKTEST_RESULTS_TOOL,
    RESEARCH_CREATE_RISK_MANAGER_CANDIDATE_TOOL,
    RESEARCH_CREATE_STRATEGY_RISK_STACK_TOOL,
    RESEARCH_CREATE_STRATEGY_CANDIDATE_TOOL,
    RESEARCH_GET_BACKTEST_RESULTS_TOOL,
    RESEARCH_LIST_RISK_MANAGER_TEMPLATES_TOOL,
    RESEARCH_LIST_STRATEGY_TEMPLATES_TOOL,
    RESEARCH_RUN_BACKTEST_TOOL,
    RESEARCH_RUN_PORTFOLIO_BACKTEST_TOOL,
    RESEARCH_TOOL_DESCRIPTIONS,
    RESEARCH_VALIDATE_RISK_MANAGER_CANDIDATE_TOOL,
    RESEARCH_VALIDATE_STRATEGY_RISK_STACK_TOOL,
    RESEARCH_VALIDATE_STRATEGY_CANDIDATE_TOOL,
)
from trader_mcp.environment import McpEnvironment
from trader_research.backtests import (
    compare_backtest_results as compare_backtest_results_service,
    get_backtest_results as get_backtest_results_service,
    run_baseline_backtest as run_baseline_backtest_service,
    run_portfolio_backtest as run_portfolio_backtest_service,
)
from trader_research.artifact_store import ResearchArtifactStore, ResearchArtifactStoreError
from trader_research.contracts import SideEffect, error_envelope
from trader_research.portfolio_stacks import (
    create_strategy_risk_stack as create_strategy_risk_stack_service,
    validate_strategy_risk_stack as validate_strategy_risk_stack_service,
)
from trader_research.risk_managers import (
    create_risk_manager_candidate as create_risk_manager_candidate_service,
    list_risk_manager_templates as list_risk_manager_templates_service,
    validate_risk_manager_candidate as validate_risk_manager_candidate_service,
)
from trader_research.strategy_candidates import (
    create_strategy_candidate as create_strategy_candidate_service,
    list_strategy_templates as list_strategy_templates_service,
)
from trader_research.strategy_candidates import validate_strategy_candidate as validate_strategy_candidate_service


EventStoreProvider = Callable[[], EventStore]
ToolConfigProvider = Callable[[], Config]
ResearchArtifactStoreProvider = Callable[[], ResearchArtifactStore]


def register_research_tools(
    server: FastMCP,
    environment: McpEnvironment,
    *,
    event_store_provider: EventStoreProvider | None = None,
    backtest_config_provider: ToolConfigProvider | None = None,
    artifact_store_provider: ResearchArtifactStoreProvider | None = None,
) -> None:
    """Register Quant Research Supervisor research tools on an MCP server."""

    def _artifact_store() -> ResearchArtifactStore | None:
        return artifact_store_provider() if artifact_store_provider is not None else None

    def _artifact_store_error(command: str, error: ResearchArtifactStoreError) -> CallToolResult:
        envelope = error_envelope(
            command=command,
            side_effect=SideEffect.LOCAL_MUTATING,
            code="research_artifact_store_unavailable",
            message=str(error),
        )
        return CallToolResult(**envelope_to_mcp_result(envelope))

    @server.tool(
        name=RESEARCH_LIST_STRATEGY_TEMPLATES_TOOL,
        description=RESEARCH_TOOL_DESCRIPTIONS[RESEARCH_LIST_STRATEGY_TEMPLATES_TOOL],
    )
    def research_list_strategy_templates(families: list[str] | None = None) -> CallToolResult:
        envelope = list_strategy_templates_service(families=families)
        return CallToolResult(**envelope_to_mcp_result(envelope))

    @server.tool(
        name=RESEARCH_CREATE_STRATEGY_CANDIDATE_TOOL,
        description=RESEARCH_TOOL_DESCRIPTIONS[RESEARCH_CREATE_STRATEGY_CANDIDATE_TOOL],
    )
    def research_create_strategy_candidate(
        template_family: str,
        method_package_refs: list[dict[str, Any]],
        parameters: dict[str, Any] | None = None,
        sizing: dict[str, Any] | None = None,
        risk_assumptions: dict[str, Any] | None = None,
        execution_assumptions: dict[str, Any] | None = None,
    ) -> CallToolResult:
        try:
            envelope = create_strategy_candidate_service(
                artifact_root=environment.artifact_root,
                template_family=template_family,
                method_package_refs=method_package_refs,
                parameters=parameters,
                sizing=sizing,
                risk_assumptions=risk_assumptions,
                execution_assumptions=execution_assumptions,
                artifact_store=_artifact_store(),
            )
        except ResearchArtifactStoreError as exc:
            return _artifact_store_error(RESEARCH_CREATE_STRATEGY_CANDIDATE_TOOL, exc)
        return CallToolResult(**envelope_to_mcp_result(envelope))

    @server.tool(
        name=RESEARCH_VALIDATE_STRATEGY_CANDIDATE_TOOL,
        description=RESEARCH_TOOL_DESCRIPTIONS[RESEARCH_VALIDATE_STRATEGY_CANDIDATE_TOOL],
    )
    def research_validate_strategy_candidate(
        candidate_id: str | None = None,
        path: str | None = None,
        strategy_candidate_manifest: dict[str, Any] | None = None,
    ) -> CallToolResult:
        try:
            envelope = validate_strategy_candidate_service(
                artifact_root=environment.artifact_root,
                candidate_id=candidate_id,
                path=path,
                strategy_candidate_manifest=strategy_candidate_manifest,
                artifact_store=_artifact_store(),
            )
        except ResearchArtifactStoreError as exc:
            return _artifact_store_error(RESEARCH_VALIDATE_STRATEGY_CANDIDATE_TOOL, exc)
        return CallToolResult(**envelope_to_mcp_result(envelope))

    @server.tool(
        name=RESEARCH_RUN_BACKTEST_TOOL,
        description=RESEARCH_TOOL_DESCRIPTIONS[RESEARCH_RUN_BACKTEST_TOOL],
    )
    async def research_run_backtest(
        candidate_id: str | None = None,
        candidate_path: str | None = None,
        strategy_candidate_manifest: dict[str, Any] | None = None,
        validation_id: str | None = None,
        validation_report_path: str | None = None,
        strategy_candidate_validation_report: dict[str, Any] | None = None,
        dataset_manifest: dict[str, Any] | None = None,
        dataset_manifest_path: str | None = None,
        dataset_manifest_ref: dict[str, Any] | None = None,
        data_quality_report: dict[str, Any] | None = None,
        data_quality_report_path: str | None = None,
        assumptions: dict[str, Any] | None = None,
        initial_cash: float = 100_000.0,
        initial_positions: list[dict[str, Any]] | None = None,
        max_runs: int | None = None,
        log_cycle_details: bool = False,
    ) -> CallToolResult:
        """Run one gated baseline backtest over a Data Agent manifest."""
        if not environment.allow_backtests:
            envelope = error_envelope(
                command=RESEARCH_RUN_BACKTEST_TOOL,
                side_effect=SideEffect.LOCAL_MUTATING,
                code="backtests_not_allowed",
                message="Backtest execution requires TRADER_MCP_ALLOW_BACKTESTS=true.",
            )
            return CallToolResult(**envelope_to_mcp_result(envelope))
        if event_store_provider is None or backtest_config_provider is None:
            envelope = error_envelope(
                command=RESEARCH_RUN_BACKTEST_TOOL,
                side_effect=SideEffect.LOCAL_MUTATING,
                code="tool_runtime_configuration_error",
                message="Backtest tools require configured event-store and config providers.",
            )
            return CallToolResult(**envelope_to_mcp_result(envelope))

        def _run_service() -> Any:
            event_store = event_store_provider()
            config = backtest_config_provider()
            return run_baseline_backtest_service(
                artifact_root=environment.artifact_root,
                event_store=event_store,
                config=config,
                candidate_id=candidate_id,
                candidate_path=candidate_path,
                strategy_candidate_manifest=strategy_candidate_manifest,
                validation_id=validation_id,
                validation_report_path=validation_report_path,
                strategy_candidate_validation_report=strategy_candidate_validation_report,
                dataset_manifest=dataset_manifest,
                dataset_manifest_path=dataset_manifest_path,
                dataset_manifest_ref=dataset_manifest_ref,
                data_quality_report=data_quality_report,
                data_quality_report_path=data_quality_report_path,
                assumptions=assumptions,
                initial_cash=initial_cash,
                initial_positions=initial_positions,
                max_runs=max_runs,
                log_cycle_details=log_cycle_details,
                artifact_store=_artifact_store(),
            )

        try:
            envelope = await anyio.to_thread.run_sync(_run_service)
        except Exception as exc:
            envelope = error_envelope(
                command=RESEARCH_RUN_BACKTEST_TOOL,
                side_effect=SideEffect.LOCAL_MUTATING,
                code="tool_runtime_configuration_error",
                message=str(exc),
            )
            return CallToolResult(**envelope_to_mcp_result(envelope))
        return CallToolResult(**envelope_to_mcp_result(envelope))

    @server.tool(
        name=RESEARCH_RUN_PORTFOLIO_BACKTEST_TOOL,
        description=RESEARCH_TOOL_DESCRIPTIONS[RESEARCH_RUN_PORTFOLIO_BACKTEST_TOOL],
    )
    async def research_run_portfolio_backtest(
        strategy_risk_stack_validation_id: str | None = None,
        strategy_risk_stack_validation_report_path: str | None = None,
        strategy_risk_stack_validation_report: dict[str, Any] | None = None,
        dataset_manifest: dict[str, Any] | None = None,
        dataset_manifest_path: str | None = None,
        dataset_manifest_ref: dict[str, Any] | None = None,
        data_quality_report: dict[str, Any] | None = None,
        data_quality_report_path: str | None = None,
        assumptions: dict[str, Any] | None = None,
        initial_cash: float = 100_000.0,
        initial_positions: list[dict[str, Any]] | None = None,
        max_runs: int | None = None,
        log_cycle_details: bool = False,
    ) -> CallToolResult:
        """Run one gated risk-scoped portfolio backtest over a Data Agent manifest."""
        if not environment.allow_backtests:
            envelope = error_envelope(
                command=RESEARCH_RUN_PORTFOLIO_BACKTEST_TOOL,
                side_effect=SideEffect.LOCAL_MUTATING,
                code="backtests_not_allowed",
                message="Backtest execution requires TRADER_MCP_ALLOW_BACKTESTS=true.",
            )
            return CallToolResult(**envelope_to_mcp_result(envelope))
        if event_store_provider is None or backtest_config_provider is None:
            envelope = error_envelope(
                command=RESEARCH_RUN_PORTFOLIO_BACKTEST_TOOL,
                side_effect=SideEffect.LOCAL_MUTATING,
                code="tool_runtime_configuration_error",
                message="Backtest tools require configured event-store and config providers.",
            )
            return CallToolResult(**envelope_to_mcp_result(envelope))

        def _run_service() -> Any:
            event_store = event_store_provider()
            config = backtest_config_provider()
            return run_portfolio_backtest_service(
                artifact_root=environment.artifact_root,
                event_store=event_store,
                config=config,
                strategy_risk_stack_validation_id=strategy_risk_stack_validation_id,
                strategy_risk_stack_validation_report_path=strategy_risk_stack_validation_report_path,
                strategy_risk_stack_validation_report=strategy_risk_stack_validation_report,
                dataset_manifest=dataset_manifest,
                dataset_manifest_path=dataset_manifest_path,
                dataset_manifest_ref=dataset_manifest_ref,
                data_quality_report=data_quality_report,
                data_quality_report_path=data_quality_report_path,
                assumptions=assumptions,
                initial_cash=initial_cash,
                initial_positions=initial_positions,
                max_runs=max_runs,
                log_cycle_details=log_cycle_details,
                artifact_store=_artifact_store(),
            )

        try:
            envelope = await anyio.to_thread.run_sync(_run_service)
        except Exception as exc:
            envelope = error_envelope(
                command=RESEARCH_RUN_PORTFOLIO_BACKTEST_TOOL,
                side_effect=SideEffect.LOCAL_MUTATING,
                code="tool_runtime_configuration_error",
                message=str(exc),
            )
            return CallToolResult(**envelope_to_mcp_result(envelope))
        return CallToolResult(**envelope_to_mcp_result(envelope))

    @server.tool(
        name=RESEARCH_GET_BACKTEST_RESULTS_TOOL,
        description=RESEARCH_TOOL_DESCRIPTIONS[RESEARCH_GET_BACKTEST_RESULTS_TOOL],
    )
    def research_get_backtest_results(
        run_id: str | None = None,
        artifact_dir: str | None = None,
        backtest_run_ref: dict[str, Any] | None = None,
    ) -> CallToolResult:
        """Read one persisted baseline backtest bundle."""
        envelope = get_backtest_results_service(
            artifact_root=environment.artifact_root,
            run_id=run_id,
            artifact_dir=artifact_dir,
            backtest_run_ref=backtest_run_ref,
        )
        return CallToolResult(**envelope_to_mcp_result(envelope))

    @server.tool(
        name=RESEARCH_COMPARE_BACKTEST_RESULTS_TOOL,
        description=RESEARCH_TOOL_DESCRIPTIONS[RESEARCH_COMPARE_BACKTEST_RESULTS_TOOL],
    )
    def research_compare_backtest_results(
        backtest_runs: list[dict[str, Any]],
        ranking_metric: str = "sharpe",
        sort_order: str | None = None,
    ) -> CallToolResult:
        """Compare persisted baseline backtest bundles and write a comparison report."""
        envelope = compare_backtest_results_service(
            artifact_root=environment.artifact_root,
            backtest_runs=backtest_runs,
            ranking_metric=ranking_metric,
            sort_order=sort_order,
        )
        return CallToolResult(**envelope_to_mcp_result(envelope))

    @server.tool(
        name=RESEARCH_LIST_RISK_MANAGER_TEMPLATES_TOOL,
        description=RESEARCH_TOOL_DESCRIPTIONS[RESEARCH_LIST_RISK_MANAGER_TEMPLATES_TOOL],
    )
    def research_list_risk_manager_templates(families: list[str] | None = None) -> CallToolResult:
        """List source-generatable risk-manager templates."""
        envelope = list_risk_manager_templates_service(families=families)
        return CallToolResult(**envelope_to_mcp_result(envelope))

    @server.tool(
        name=RESEARCH_CREATE_RISK_MANAGER_CANDIDATE_TOOL,
        description=RESEARCH_TOOL_DESCRIPTIONS[RESEARCH_CREATE_RISK_MANAGER_CANDIDATE_TOOL],
    )
    def research_create_risk_manager_candidate(
        template_family: str,
        parameters: dict[str, Any] | None = None,
        method_package_refs: list[dict[str, Any]] | None = None,
        execution_assumptions: dict[str, Any] | None = None,
    ) -> CallToolResult:
        """Create one source-backed risk-manager candidate artifact."""
        try:
            envelope = create_risk_manager_candidate_service(
                artifact_root=environment.artifact_root,
                template_family=template_family,
                parameters=parameters,
                method_package_refs=method_package_refs,
                execution_assumptions=execution_assumptions,
                artifact_store=_artifact_store(),
            )
        except ResearchArtifactStoreError as exc:
            return _artifact_store_error(RESEARCH_CREATE_RISK_MANAGER_CANDIDATE_TOOL, exc)
        return CallToolResult(**envelope_to_mcp_result(envelope))

    @server.tool(
        name=RESEARCH_VALIDATE_RISK_MANAGER_CANDIDATE_TOOL,
        description=RESEARCH_TOOL_DESCRIPTIONS[RESEARCH_VALIDATE_RISK_MANAGER_CANDIDATE_TOOL],
    )
    def research_validate_risk_manager_candidate(
        candidate_id: str | None = None,
        path: str | None = None,
        risk_manager_candidate_manifest: dict[str, Any] | None = None,
    ) -> CallToolResult:
        """Validate one source-backed risk-manager candidate artifact."""
        try:
            envelope = validate_risk_manager_candidate_service(
                artifact_root=environment.artifact_root,
                candidate_id=candidate_id,
                path=path,
                risk_manager_candidate_manifest=risk_manager_candidate_manifest,
                artifact_store=_artifact_store(),
            )
        except ResearchArtifactStoreError as exc:
            return _artifact_store_error(RESEARCH_VALIDATE_RISK_MANAGER_CANDIDATE_TOOL, exc)
        return CallToolResult(**envelope_to_mcp_result(envelope))

    @server.tool(
        name=RESEARCH_CREATE_STRATEGY_RISK_STACK_TOOL,
        description=RESEARCH_TOOL_DESCRIPTIONS[RESEARCH_CREATE_STRATEGY_RISK_STACK_TOOL],
    )
    def research_create_strategy_risk_stack(
        strategy_validation_id: str | None = None,
        strategy_validation_report_path: str | None = None,
        strategy_candidate_validation_report: dict[str, Any] | None = None,
        risk_manager_validation_refs: list[dict[str, Any]] | None = None,
        execution_assumptions: dict[str, Any] | None = None,
    ) -> CallToolResult:
        """Compose a validated strategy candidate and ordered risk-manager candidates."""
        try:
            envelope = create_strategy_risk_stack_service(
                artifact_root=environment.artifact_root,
                strategy_validation_id=strategy_validation_id,
                strategy_validation_report_path=strategy_validation_report_path,
                strategy_candidate_validation_report=strategy_candidate_validation_report,
                risk_manager_validation_refs=risk_manager_validation_refs or (),
                execution_assumptions=execution_assumptions,
                artifact_store=_artifact_store(),
            )
        except ResearchArtifactStoreError as exc:
            return _artifact_store_error(RESEARCH_CREATE_STRATEGY_RISK_STACK_TOOL, exc)
        return CallToolResult(**envelope_to_mcp_result(envelope))

    @server.tool(
        name=RESEARCH_VALIDATE_STRATEGY_RISK_STACK_TOOL,
        description=RESEARCH_TOOL_DESCRIPTIONS[RESEARCH_VALIDATE_STRATEGY_RISK_STACK_TOOL],
    )
    def research_validate_strategy_risk_stack(
        stack_id: str | None = None,
        path: str | None = None,
        strategy_risk_stack_manifest: dict[str, Any] | None = None,
    ) -> CallToolResult:
        """Validate one strategy/risk stack with deterministic fixture bars."""
        try:
            envelope = validate_strategy_risk_stack_service(
                artifact_root=environment.artifact_root,
                stack_id=stack_id,
                path=path,
                strategy_risk_stack_manifest=strategy_risk_stack_manifest,
                artifact_store=_artifact_store(),
            )
        except ResearchArtifactStoreError as exc:
            return _artifact_store_error(RESEARCH_VALIDATE_STRATEGY_RISK_STACK_TOOL, exc)
        return CallToolResult(**envelope_to_mcp_result(envelope))
