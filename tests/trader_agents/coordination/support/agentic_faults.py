"""Controlled transport faults for fresh-process agentic qualification.

Faults wrap an already opened production MCP client. They never alter tool
arguments, responses, or canonical stores; they interrupt the owning agent
process immediately before or after one reviewed boundary so the next process
must recover from Postgres state.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from trader_agents.contracts.domain import AgentRole
from trader_agents.application.runtime import McpClientDecorator
from trader_agents.mcp.client import McpToolClient, McpToolDescription


NO_FAULT = "none"
BEFORE_DATA_MUTATION = "before_data_mutation"
AFTER_DATA_MUTATION = "after_data_mutation"
BEFORE_RETURN_RECONCILIATION = "before_return_reconciliation"
BEFORE_STRATEGY_PACKAGE = "before_strategy_package"
AFTER_STRATEGY_PACKAGE = "after_strategy_package"
BEFORE_STRATEGY_REGISTRATION = "before_strategy_registration"
AFTER_STRATEGY_REGISTRATION = "after_strategy_registration"
BEFORE_STRATEGY_ADMISSION = "before_strategy_admission"
AFTER_STRATEGY_ADMISSION_FAILURE = "after_strategy_admission_failure"
BEFORE_STRATEGY_REPAIR_WRITE = "before_strategy_repair_write"
AFTER_STRATEGY_ADMISSION_SUCCESS = "after_strategy_admission_success"
RECOVERY_FAULT_MODES = frozenset(
    {
        NO_FAULT,
        BEFORE_DATA_MUTATION,
        AFTER_DATA_MUTATION,
        BEFORE_RETURN_RECONCILIATION,
        BEFORE_STRATEGY_PACKAGE,
        AFTER_STRATEGY_PACKAGE,
        BEFORE_STRATEGY_REGISTRATION,
        AFTER_STRATEGY_REGISTRATION,
        BEFORE_STRATEGY_ADMISSION,
        AFTER_STRATEGY_ADMISSION_FAILURE,
        BEFORE_STRATEGY_REPAIR_WRITE,
        AFTER_STRATEGY_ADMISSION_SUCCESS,
    }
)


class InjectedProcessFault(BaseException):
    """Terminate one qualification worker at an exact public boundary.

    The exception derives directly from ``BaseException`` so agent loops cannot
    reinterpret the injected process failure as a domain or model failure.

    Attributes:
        mode: Reviewed fault mode that fired.
        role: Role-labelled MCP client on which it fired.
        tool_name: Exact authorized MCP operation at the boundary.
    """

    def __init__(self, *, mode: str, role: AgentRole, tool_name: str) -> None:
        """Create a source-free process fault marker."""
        super().__init__(f"injected {mode} at {role.value}/{tool_name}")
        self.mode = mode
        self.role = role
        self.tool_name = tool_name


@dataclass
class FaultInjectingMcpClient:
    """Wrap one role client and fire its configured fault at most once."""

    client: McpToolClient
    role: AgentRole
    mode: str
    _triggered: bool = False
    _admission_failure_observed: bool = False

    def __post_init__(self) -> None:
        """Reject unknown fault modes before any transport opens."""
        if self.mode not in RECOVERY_FAULT_MODES:
            raise ValueError(f"unknown agentic recovery fault mode: {self.mode}")

    async def list_tools(self) -> Sequence[McpToolDescription]:
        """Delegate exact transport schema discovery without faulting."""
        return await self.client.list_tools()

    async def call_tool(
        self,
        tool_name: str,
        arguments: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        """Interrupt before or after the configured accepted tool boundary."""
        if self._matches_before(tool_name, arguments):
            self._raise_fault(tool_name)
        result = await self.client.call_tool(tool_name, arguments)
        if (
            self.role is AgentRole.STRATEGY_ENGINEERING
            and tool_name == "research_validate_strategy_implementation"
            and _structured_result_ok(result) is False
        ):
            self._admission_failure_observed = True
        if self._matches_after(tool_name, arguments, result):
            self._raise_fault(tool_name)
        return result

    def _matches_before(
        self,
        tool_name: str,
        arguments: Mapping[str, Any],
    ) -> bool:
        """Return whether this call is the configured pre-dispatch boundary."""
        if self._triggered:
            return False
        if self.mode == BEFORE_DATA_MUTATION:
            return self.role is AgentRole.DATA_RESEARCH and _is_data_mutation(
                tool_name,
                arguments,
            )
        if self.role is AgentRole.STRATEGY_ENGINEERING:
            if self.mode == BEFORE_STRATEGY_PACKAGE:
                return tool_name == "coding_package_candidate"
            if self.mode == BEFORE_STRATEGY_REGISTRATION:
                return tool_name == "research_register_strategy_implementation"
            if self.mode == BEFORE_STRATEGY_ADMISSION:
                return tool_name == "research_validate_strategy_implementation"
            if self.mode == BEFORE_STRATEGY_REPAIR_WRITE:
                return (
                    self._admission_failure_observed
                    and tool_name == "coding_write_candidate_file"
                )
        return (
            self.mode == BEFORE_RETURN_RECONCILIATION
            and self.role is AgentRole.RESEARCH_COORDINATOR
            and tool_name == "research_read_artifact"
        )

    def _matches_after(
        self,
        tool_name: str,
        arguments: Mapping[str, Any],
        result: Mapping[str, Any],
    ) -> bool:
        """Return whether this accepted response is the post-mutation boundary."""
        if self._triggered:
            return False
        result_ok = _structured_result_ok(result)
        if self.mode == AFTER_DATA_MUTATION:
            return (
                self.role is AgentRole.DATA_RESEARCH
                and _is_data_mutation(tool_name, arguments)
                and result_ok is True
            )
        if self.role is not AgentRole.STRATEGY_ENGINEERING:
            return False
        if self.mode == AFTER_STRATEGY_PACKAGE:
            return tool_name == "coding_package_candidate" and result_ok is True
        if self.mode == AFTER_STRATEGY_REGISTRATION:
            return (
                tool_name == "research_register_strategy_implementation"
                and result_ok is True
            )
        if self.mode == AFTER_STRATEGY_ADMISSION_FAILURE:
            return (
                tool_name == "research_validate_strategy_implementation"
                and result_ok is False
            )
        if self.mode == AFTER_STRATEGY_ADMISSION_SUCCESS:
            return (
                tool_name == "research_validate_strategy_implementation"
                and result_ok is True
            )
        return False

    def _raise_fault(self, tool_name: str) -> None:
        """Mark this wrapper fired and raise a process-level fault."""
        self._triggered = True
        raise InjectedProcessFault(
            mode=self.mode,
            role=self.role,
            tool_name=tool_name,
        )


def recovery_mcp_client_decorator(mode: str) -> McpClientDecorator:
    """Build a role-aware client decorator for one process attempt.

    Args:
        mode: One exact member of :data:`RECOVERY_FAULT_MODES`.

    Returns:
        Runtime decorator that preserves each opened transport's ownership.

    Raises:
        ValueError: If ``mode`` is not a reviewed recovery fixture.
    """
    if mode not in RECOVERY_FAULT_MODES:
        raise ValueError(f"unknown agentic recovery fault mode: {mode}")

    def _decorate(role: AgentRole, client: McpToolClient) -> McpToolClient:
        return FaultInjectingMcpClient(client=client, role=role, mode=mode)

    return _decorate


def _is_data_mutation(
    tool_name: str,
    arguments: Mapping[str, Any],
) -> bool:
    """Identify an actual provider-backed Data mutation, not its dry run."""
    mode = str(arguments.get("mode") or "").strip().lower()
    return (
        tool_name == "data_ensure_loaded"
        and mode in {"sample", "backfill"}
        and arguments.get("dry_run") is False
    )


def _structured_result_ok(result: Mapping[str, Any]) -> bool | None:
    """Return the strict MCP success verdict when one is present."""
    structured = result.get("structuredContent")
    if not isinstance(structured, Mapping):
        return None
    value = structured.get("ok")
    return value if isinstance(value, bool) else None
