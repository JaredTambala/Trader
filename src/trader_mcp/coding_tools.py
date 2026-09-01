"""MCP adapters for the isolated Strategy Engineering Coding Workspace."""

from __future__ import annotations

from collections.abc import Callable

from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult

from trader_mcp.adapters import result_to_mcp_result
from trader_mcp.constants import CODING_TOOL_DESCRIPTIONS
from trader_mcp.contracts import SideEffect, error_envelope
from trader_mcp.environment import McpEnvironment
from trader_research.coding import (
    CODING_CREATE_WORKSPACE,
    CODING_DESTROY_WORKSPACE,
    CODING_GET_WORKSPACE,
    CODING_PACKAGE_CANDIDATE,
    CODING_READ_CANDIDATE_FILE,
    CODING_READ_REPOSITORY_FILE,
    CODING_RESOLVE_DEPENDENCIES,
    CODING_RUN_CHECK,
    CODING_SEARCH_REPOSITORY,
    CODING_WRITE_CANDIDATE_FILE,
    CodingWorkspaceService,
)
from trader_research.foundation import ApplicationResult


CodingWorkspaceServiceProvider = Callable[[], CodingWorkspaceService]


def register_coding_tools(
    server: FastMCP,
    environment: McpEnvironment,
    *,
    service_provider: CodingWorkspaceServiceProvider | None,
) -> None:
    """Register bounded Coding Workspace tools on an MCP server.

    Tools remain registered when the capability is disabled so clients receive
    structured policy failures rather than a misleading missing-tool error.

    Args:
        server: FastMCP server receiving the tool registrations.
        environment: Runtime policy controlling coding mutations and checks.
        service_provider: Lazy configured workspace service, or ``None`` when
            no safe workspace runtime is configured.
    """

    def _service(command: str, side_effect: SideEffect) -> CodingWorkspaceService | CallToolResult:
        if not environment.allow_coding_workspace:
            return _blocked(
                command,
                side_effect,
                "coding_workspace_not_allowed",
                "Coding Workspace tools require TRADER_MCP_ALLOW_CODING_WORKSPACE=true.",
            )
        if service_provider is None:
            return _blocked(
                command,
                side_effect,
                "coding_workspace_not_configured",
                "Coding Workspace root, repository revision, and container image must be configured.",
            )
        try:
            return service_provider()
        except (OSError, RuntimeError, ValueError) as exc:
            return _blocked(
                command,
                side_effect,
                "coding_workspace_configuration_error",
                str(exc),
            )

    @server.tool(
        name=CODING_CREATE_WORKSPACE,
        description=CODING_TOOL_DESCRIPTIONS[CODING_CREATE_WORKSPACE],
    )
    def coding_create_workspace(
        attempt_id: str,
        build_contract_id: str,
    ) -> CallToolResult:
        """Create or reopen an exact candidate-attempt workspace."""
        service = _service(CODING_CREATE_WORKSPACE, SideEffect.LOCAL_MUTATING)
        if isinstance(service, CallToolResult):
            return service
        return _result(
            service.create_workspace(
                attempt_id=attempt_id,
                build_contract_id=build_contract_id,
            )
        )

    @server.tool(
        name=CODING_GET_WORKSPACE,
        description=CODING_TOOL_DESCRIPTIONS[CODING_GET_WORKSPACE],
    )
    def coding_get_workspace(workspace_id: str) -> CallToolResult:
        """Return bounded status for one exact workspace."""
        service = _service(CODING_GET_WORKSPACE, SideEffect.READ_ONLY)
        if isinstance(service, CallToolResult):
            return service
        return _result(service.get_workspace(workspace_id))

    @server.tool(
        name=CODING_SEARCH_REPOSITORY,
        description=CODING_TOOL_DESCRIPTIONS[CODING_SEARCH_REPOSITORY],
    )
    def coding_search_repository(
        query: str,
        roots: list[str] | None = None,
        limit: int = 20,
    ) -> CallToolResult:
        """Search bounded text in the pinned repository snapshot."""
        service = _service(CODING_SEARCH_REPOSITORY, SideEffect.READ_ONLY)
        if isinstance(service, CallToolResult):
            return service
        return _result(
            service.search_repository(
                query=query,
                roots=tuple(roots) if roots is not None else (
                    "src/trader",
                    "src/trader_standard",
                    "docs/python_code_quality.md",
                ),
                limit=limit,
            )
        )

    @server.tool(
        name=CODING_READ_REPOSITORY_FILE,
        description=CODING_TOOL_DESCRIPTIONS[CODING_READ_REPOSITORY_FILE],
    )
    def coding_read_repository_file(
        relative_path: str,
        max_bytes: int = 64_000,
    ) -> CallToolResult:
        """Read one bounded file from the pinned repository snapshot."""
        service = _service(CODING_READ_REPOSITORY_FILE, SideEffect.READ_ONLY)
        if isinstance(service, CallToolResult):
            return service
        return _result(
            service.read_repository_file(relative_path, max_bytes=max_bytes)
        )

    @server.tool(
        name=CODING_WRITE_CANDIDATE_FILE,
        description=CODING_TOOL_DESCRIPTIONS[CODING_WRITE_CANDIDATE_FILE],
    )
    def coding_write_candidate_file(
        workspace_id: str,
        relative_path: str,
        content: str,
    ) -> CallToolResult:
        """Write one complete bounded candidate file."""
        service = _service(CODING_WRITE_CANDIDATE_FILE, SideEffect.LOCAL_MUTATING)
        if isinstance(service, CallToolResult):
            return service
        return _result(
            service.write_candidate_file(workspace_id, relative_path, content)
        )

    @server.tool(
        name=CODING_READ_CANDIDATE_FILE,
        description=CODING_TOOL_DESCRIPTIONS[CODING_READ_CANDIDATE_FILE],
    )
    def coding_read_candidate_file(
        workspace_id: str,
        relative_path: str,
    ) -> CallToolResult:
        """Read one bounded candidate file."""
        service = _service(CODING_READ_CANDIDATE_FILE, SideEffect.READ_ONLY)
        if isinstance(service, CallToolResult):
            return service
        return _result(service.read_candidate_file(workspace_id, relative_path))

    @server.tool(
        name=CODING_RESOLVE_DEPENDENCIES,
        description=CODING_TOOL_DESCRIPTIONS[CODING_RESOLVE_DEPENDENCIES],
    )
    def coding_resolve_dependencies(
        workspace_id: str,
        dependencies: list[str],
    ) -> CallToolResult:
        """Validate dependencies against the pinned image policy."""
        service = _service(CODING_RESOLVE_DEPENDENCIES, SideEffect.READ_ONLY)
        if isinstance(service, CallToolResult):
            return service
        return _result(service.resolve_dependencies(workspace_id, dependencies))

    @server.tool(
        name=CODING_RUN_CHECK,
        description=CODING_TOOL_DESCRIPTIONS[CODING_RUN_CHECK],
    )
    def coding_run_check(
        workspace_id: str,
        check_name: str,
        timeout_seconds: int | None = None,
    ) -> CallToolResult:
        """Run one allowlisted isolated candidate check."""
        service = _service(CODING_RUN_CHECK, SideEffect.LOCAL_MUTATING)
        if isinstance(service, CallToolResult):
            return service
        return _result(
            service.run_check(
                workspace_id,
                check_name,
                timeout_seconds=timeout_seconds,
            )
        )

    @server.tool(
        name=CODING_PACKAGE_CANDIDATE,
        description=CODING_TOOL_DESCRIPTIONS[CODING_PACKAGE_CANDIDATE],
    )
    def coding_package_candidate(
        workspace_id: str,
        implementation_path: str = "implementation.py",
    ) -> CallToolResult:
        """Package exact inert candidate source and file hashes."""
        service = _service(CODING_PACKAGE_CANDIDATE, SideEffect.READ_ONLY)
        if isinstance(service, CallToolResult):
            return service
        return _result(
            service.package_candidate(
                workspace_id,
                implementation_path=implementation_path,
            )
        )

    @server.tool(
        name=CODING_DESTROY_WORKSPACE,
        description=CODING_TOOL_DESCRIPTIONS[CODING_DESTROY_WORKSPACE],
    )
    def coding_destroy_workspace(workspace_id: str) -> CallToolResult:
        """Destroy one exact disposable candidate workspace."""
        service = _service(CODING_DESTROY_WORKSPACE, SideEffect.LOCAL_MUTATING)
        if isinstance(service, CallToolResult):
            return service
        return _result(service.destroy_workspace(workspace_id))


def _result(result: ApplicationResult) -> CallToolResult:
    """Convert one application result without changing its semantics."""
    return CallToolResult(**result_to_mcp_result(result))


def _blocked(
    command: str,
    side_effect: SideEffect,
    code: str,
    message: str,
) -> CallToolResult:
    """Return one structured unavailable-policy result."""
    return CallToolResult(
        **result_to_mcp_result(
            error_envelope(
                command=command,
                side_effect=side_effect,
                code=code,
                message=message,
            )
        )
    )
