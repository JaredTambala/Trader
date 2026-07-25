"""MCP registrations for ML-owned raw-inference deployment evidence."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult

from trader_mcp.adapters import result_to_mcp_result
from trader_mcp.constants import (
    ML_CREATE_DEPLOYMENT_MANIFEST_TOOL,
    ML_TOOL_DESCRIPTIONS,
    ML_VALIDATE_DEPLOYMENT_TOOL,
)
from trader_mcp.contracts import SideEffect, error_envelope
from trader_mcp.environment import McpEnvironment
from trader_research.foundation import ResearchArtifactStore
from trader_research.ml import (
    InferenceAdapterRegistry,
    create_deployment_manifest,
    validate_deployment,
)


ResearchArtifactStoreProvider = Callable[[], ResearchArtifactStore]


def register_ml_tools(
    server: FastMCP,
    environment: McpEnvironment,
    *,
    artifact_store_provider: ResearchArtifactStoreProvider | None,
    adapter_registry: InferenceAdapterRegistry,
) -> None:
    """Register DB-first deployment creation and gated parity validation."""

    def _store() -> ResearchArtifactStore | None:
        return artifact_store_provider() if artifact_store_provider is not None else None

    def _result(value: object) -> CallToolResult:
        return CallToolResult(**result_to_mcp_result(value))  # type: ignore[arg-type]

    @server.tool(
        name=ML_CREATE_DEPLOYMENT_MANIFEST_TOOL,
        description=ML_TOOL_DESCRIPTIONS[ML_CREATE_DEPLOYMENT_MANIFEST_TOOL],
    )
    def ml_create_deployment_manifest(
        model_version_ref: str,
        feature_set_validation_ref: str,
        adapter_profile: str,
        output_contract: list[dict[str, Any]],
        inference_scope: str,
        inference_policy: dict[str, Any] | None = None,
        environment_config: dict[str, Any] | None = None,
        parity_fixture: dict[str, Any] | None = None,
        eligibility: list[str] | None = None,
    ) -> CallToolResult:
        return _result(
            create_deployment_manifest(
                model_version_ref=model_version_ref,
                feature_set_validation_ref=feature_set_validation_ref,
                adapter_profile=adapter_profile,
                output_contract=output_contract,
                inference_scope=inference_scope,
                inference_policy=inference_policy,
                environment=environment_config,
                parity_fixture=parity_fixture,
                eligibility=tuple(eligibility or ("backtest",)),
                artifact_store=_store(),
                adapter_registry=adapter_registry,
            )
        )

    @server.tool(
        name=ML_VALIDATE_DEPLOYMENT_TOOL,
        description=ML_TOOL_DESCRIPTIONS[ML_VALIDATE_DEPLOYMENT_TOOL],
    )
    def ml_validate_deployment(
        deployment_id: str | None = None,
        deployment_uri: str | None = None,
        deployment_manifest: dict[str, Any] | None = None,
    ) -> CallToolResult:
        if not environment.allow_ml_runtime:
            return _result(
                error_envelope(
                    command=ML_VALIDATE_DEPLOYMENT_TOOL,
                    side_effect=SideEffect.LOCAL_MUTATING,
                    code="ml_runtime_not_allowed",
                    message=(
                        "Deployment parity validation requires "
                        "TRADER_MCP_ALLOW_ML_RUNTIME=true."
                    ),
                )
            )
        return _result(
            validate_deployment(
                deployment_id=deployment_id,
                deployment_uri=deployment_uri,
                deployment_manifest=deployment_manifest,
                artifact_store=_store(),
                adapter_registry=adapter_registry,
            )
        )
