"""MCP contracts for Strategy Engineering catalogue and workspace tools."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import anyio

from trader_mcp.constants import (
    CODING_CREATE_WORKSPACE_TOOL,
    CODING_PACKAGE_CANDIDATE_TOOL,
    CODING_RUN_CHECK_TOOL,
    CODING_SEARCH_REPOSITORY_TOOL,
    CODING_WRITE_CANDIDATE_FILE_TOOL,
    RESEARCH_REGISTER_STRATEGY_IMPLEMENTATION_TOOL,
    RESEARCH_SEARCH_IMPLEMENTATIONS_TOOL,
)
from trader_mcp.environment import load_local_environment
from trader_mcp.server import create_server
from trader_research.coding import CodingWorkspacePolicy, CodingWorkspaceService
from trader_research.foundation import InMemoryResearchArtifactStore


def test_coding_tools_are_registered_but_fail_closed_when_disabled() -> None:
    server = create_server(load_local_environment("env.template"))

    async def _run() -> None:
        result = await server.call_tool(
            CODING_CREATE_WORKSPACE_TOOL,
            {"attempt_id": "attempt-1", "build_contract_id": "contract-1"},
        )

        assert result.isError is True
        assert result.structuredContent is not None
        assert result.structuredContent["errors"][0]["code"] == (
            "coding_workspace_not_allowed"
        )
        assert result.structuredContent["agent_owner"] == "Strategy Engineering Agent"

    anyio.run(_run)


def test_coding_tools_expose_bounded_workspace_without_host_check_fallback(
    tmp_path: Path,
) -> None:
    repository_root = tmp_path / "repository"
    (repository_root / "src").mkdir(parents=True)
    (repository_root / "src" / "contract.py").write_text(
        "# Strategy public contract\n",
        encoding="utf-8",
    )
    service = CodingWorkspaceService(
        CodingWorkspacePolicy(
            workspace_root=tmp_path / "workspaces",
            repository_root=repository_root,
            repository_revision="revision-1",
            container_image="trader-agent-coding@sha256:demo",
        )
    )
    environment = replace(
        load_local_environment("env.template"),
        allow_coding_workspace=True,
    )
    server = create_server(
        environment,
        coding_workspace_service_provider=lambda: service,
    )

    async def _run() -> None:
        created = await server.call_tool(
            CODING_CREATE_WORKSPACE_TOOL,
            {"attempt_id": "attempt-1", "build_contract_id": "contract-1"},
        )
        assert created.structuredContent is not None
        workspace_id = created.structuredContent["data"]["workspace"]["workspace_id"]
        searched = await server.call_tool(
            CODING_SEARCH_REPOSITORY_TOOL,
            {"query": "public contract", "roots": ["src"]},
        )
        written = await server.call_tool(
            CODING_WRITE_CANDIDATE_FILE_TOOL,
            {
                "workspace_id": workspace_id,
                "relative_path": "implementation.py",
                "content": "def build_strategy(**kwargs):\n    return kwargs\n",
            },
        )
        packaged = await server.call_tool(
            CODING_PACKAGE_CANDIDATE_TOOL,
            {"workspace_id": workspace_id},
        )
        check = await server.call_tool(
            CODING_RUN_CHECK_TOOL,
            {"workspace_id": workspace_id, "check_name": "compile"},
        )

        assert created.isError is False
        assert searched.isError is False
        assert written.isError is False
        assert packaged.isError is False
        assert check.isError is True
        assert check.structuredContent is not None
        assert check.structuredContent["errors"][0]["code"] == "coding_check_unavailable"

    anyio.run(_run)


def test_implementation_search_tool_requires_canonical_store() -> None:
    environment = load_local_environment("env.template")
    server = create_server(
        environment,
        research_artifact_store_provider=InMemoryResearchArtifactStore,
    )

    async def _run() -> None:
        result = await server.call_tool(
            RESEARCH_SEARCH_IMPLEMENTATIONS_TOOL,
            {"implementation_kinds": ["strategy"], "query": "trend"},
        )

        assert result.isError is False
        assert result.structuredContent is not None
        assert result.structuredContent["agent_owner"] == "Strategy Engineering Agent"
        assert result.structuredContent["side_effect"] == "read_only"
        rows = result.structuredContent["data"]["implementations"]
        assert rows
        assert all(row["direct_reuse_eligible"] is False for row in rows)

    anyio.run(_run)


def test_candidate_package_registers_without_model_relaying_source(
    tmp_path: Path,
) -> None:
    """The MCP adapter resolves retained source from an exact package ID."""
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    service = CodingWorkspaceService(
        CodingWorkspacePolicy(
            workspace_root=tmp_path / "workspaces",
            repository_root=repository_root,
            repository_revision="revision-1",
            container_image="trader-agent-coding@sha256:demo",
        )
    )
    source = "def build_strategy(**kwargs):\n    return kwargs\n"
    created = service.create_workspace(
        attempt_id="attempt-1",
        build_contract_id="contract-1",
    )
    workspace_id = created.data["workspace"]["workspace_id"]
    assert service.write_candidate_file(
        workspace_id,
        "implementation.py",
        source,
    ).ok
    packaged = service.package_candidate(workspace_id)
    package_id = packaged.data["candidate_package"]["package_id"]
    assert service.destroy_workspace(workspace_id).ok

    artifact_store = InMemoryResearchArtifactStore()
    environment = replace(
        load_local_environment("env.template"),
        allow_coding_workspace=True,
    )
    server = create_server(
        environment,
        coding_workspace_service_provider=lambda: service,
        research_artifact_store_provider=lambda: artifact_store,
    )

    async def _run() -> None:
        registered = await server.call_tool(
            RESEARCH_REGISTER_STRATEGY_IMPLEMENTATION_TOOL,
            {
                "name": "PackageBackedStrategy",
                "version": "1.0.0",
                "factory_name": "build_strategy",
                "candidate_package_id": package_id,
                "authoring_origin": "agent_authored",
                "metadata": {"candidate_package_id": package_id},
            },
        )
        assert registered.isError is False
        assert registered.structuredContent is not None
        implementation = registered.structuredContent["data"][
            "implementation_version"
        ]
        assert "source_code" not in implementation
        assert implementation["source_hash"] == packaged.data[
            "candidate_package"
        ]["source_hash"]
        assert implementation["metadata"]["candidate_package_id"] == package_id

        conflicted = await server.call_tool(
            RESEARCH_REGISTER_STRATEGY_IMPLEMENTATION_TOOL,
            {
                "name": "PackageBackedStrategy",
                "version": "1.0.0",
                "factory_name": "build_strategy",
                "source_code": source,
                "candidate_package_id": package_id,
            },
        )
        assert conflicted.isError is True
        assert conflicted.structuredContent is not None
        assert conflicted.structuredContent["errors"][0]["code"] == (
            "implementation_source_selector_invalid"
        )

    anyio.run(_run)
