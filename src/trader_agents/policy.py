"""Deterministic authority, scope, budget, and loop policy for agent actions."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from trader_mcp.contracts import SideEffect
from trader_research.foundation import json_payload_hash
from trader_research.governance import AgentBudget, ResearchSession

from .catalogue import ToolCatalogue, ToolDefinition
from .contracts import (
    AgentPhase,
    AgentRole,
    BudgetUsage,
    CompositeDataScope,
    SpecialistDelegation,
    StrategyBuildContract,
    ToolCallProposal,
)


class PolicyViolation(ValueError):
    """Raised when a model proposal crosses deterministic runtime policy."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        """Create one actionable fail-closed policy error."""
        super().__init__(message)
        self.code = code
        self.details = dict(details or {})


@dataclass(frozen=True)
class PolicyContext:
    """Trusted state used to authorize one model-proposed tool call.

    Attributes:
        session: Immutable operator-approved research session.
        role: Active model-backed role.
        phase: Current invocation lifecycle phase.
        program_id: Exact admitted program identity.
        tool_catalogue: Code-owned role catalogue.
        usage: Cumulative accepted session resource usage.
        runtime_state: Bounded public lifecycle facts.
        loop_fingerprints: Semantic action fingerprints and prior counts.
        delegation: Owning specialist delegation when applicable.
        data_scope: Exact composite scope for Data Research.
        build_contract: Exact implementation contract for Strategy Engineering.
    """

    session: ResearchSession
    role: AgentRole
    phase: AgentPhase
    program_id: str
    tool_catalogue: ToolCatalogue
    usage: BudgetUsage
    runtime_state: Mapping[str, Any]
    loop_fingerprints: Mapping[str, int]
    delegation: SpecialistDelegation | None = None
    data_scope: CompositeDataScope | None = None
    build_contract: StrategyBuildContract | None = None


@dataclass(frozen=True)
class AuthorizedToolCall:
    """Deterministically admitted MCP call ready for transport."""

    proposal: ToolCallProposal
    definition: ToolDefinition
    fingerprint: str


class ToolPolicy:
    """Fail-closed policy over model-proposed MCP operations."""

    def authorize(
        self,
        proposal: ToolCallProposal,
        context: PolicyContext,
    ) -> AuthorizedToolCall:
        """Authorize one exact model-proposed MCP call.

        Args:
            proposal: Strict model output naming an MCP operation and arguments.
            context: Trusted session, role, phase, lifecycle, and budget state.

        Returns:
            Authorized call carrying code-owned operation metadata.

        Raises:
            PolicyViolation: If any authority, scope, lifecycle, budget, or
                loop rule fails.
        """
        self._validate_session_pins(context)
        try:
            definition = context.tool_catalogue.resolve(
                context.role,
                proposal.tool_name,
            )
        except KeyError as exc:
            raise PolicyViolation("tool_not_allowed", str(exc)) from exc
        available = context.tool_catalogue.available(
            role=context.role,
            phase=context.phase,
            approval_policy=context.session.approval_policy,
        )
        if definition not in available:
            raise PolicyViolation(
                "tool_not_available",
                f"{proposal.tool_name} is unavailable in phase {context.phase.value}",
            )
        self._validate_budget(definition, context)
        self._validate_delegation(definition, context)
        self._validate_role_scope(proposal, definition, context)
        fingerprint = json_payload_hash(
            {
                "role": context.role.value,
                "phase": context.phase.value,
                "tool_name": proposal.tool_name,
                "arguments": proposal.arguments,
            }
        )
        prior_count = int(context.loop_fingerprints.get(fingerprint, 0))
        if prior_count > context.session.budget.max_revisions:
            raise PolicyViolation(
                "low_information_loop",
                "materially equivalent action exceeded the revision limit",
                details={"fingerprint": fingerprint, "prior_count": prior_count},
            )
        return AuthorizedToolCall(
            proposal=proposal,
            definition=definition,
            fingerprint=fingerprint,
        )

    @staticmethod
    def _validate_session_pins(context: PolicyContext) -> None:
        """Require exact program, model, and tool-catalogue session pins."""
        if context.program_id not in context.session.agent_program_ids:
            raise PolicyViolation(
                "program_not_admitted",
                "active agent program is not admitted by the research session",
            )
        if context.session.tool_catalog_id != context.tool_catalogue.catalogue_id:
            raise PolicyViolation(
                "tool_catalogue_drift",
                "runtime tool catalogue does not match the research session",
            )

    @staticmethod
    def _validate_budget(
        definition: ToolDefinition,
        context: PolicyContext,
    ) -> None:
        """Reject calls that would exceed session tool/mutation budgets."""
        budget = context.session.budget
        if context.usage.tool_calls + 1 > budget.max_tool_calls:
            raise PolicyViolation("tool_budget_exhausted", "tool-call budget is exhausted")
        if (
            definition.side_effect is not SideEffect.READ_ONLY
            and context.usage.mutations + 1 > budget.max_mutations
        ):
            raise PolicyViolation("mutation_budget_exhausted", "mutation budget is exhausted")
        if context.usage.total_tokens > budget.max_tokens:
            raise PolicyViolation("token_budget_exhausted", "token budget is exhausted")
        if context.usage.duration_ms > budget.max_duration_seconds * 1_000:
            raise PolicyViolation("duration_budget_exhausted", "duration budget is exhausted")

    @staticmethod
    def _validate_delegation(
        definition: ToolDefinition,
        context: PolicyContext,
    ) -> None:
        """Require specialist calls to remain inside delegated side effects."""
        if context.role is AgentRole.RESEARCH_COORDINATOR:
            if context.delegation is not None:
                raise PolicyViolation(
                    "unexpected_delegation",
                    "coordinator tool calls cannot borrow specialist delegation authority",
                )
            return
        if context.delegation is None:
            raise PolicyViolation(
                "delegation_required",
                "specialist MCP calls require an admitted delegation",
            )
        if context.delegation.task.role != context.role.value:
            raise PolicyViolation(
                "delegation_role_mismatch",
                "delegation role does not match the active specialist",
            )
        if definition.side_effect.value not in context.delegation.permitted_side_effects:
            raise PolicyViolation(
                "side_effect_not_delegated",
                f"{definition.side_effect.value} is outside delegated authority",
            )
        if context.usage.tool_calls + 1 > context.delegation.reserved_tool_calls:
            raise PolicyViolation(
                "delegation_tool_budget_exhausted",
                "specialist tool-call reservation is exhausted",
            )
        if context.usage.total_tokens > context.delegation.reserved_tokens:
            raise PolicyViolation(
                "delegation_token_budget_exhausted",
                "specialist token reservation is exhausted",
            )

    def _validate_role_scope(
        self,
        proposal: ToolCallProposal,
        definition: ToolDefinition,
        context: PolicyContext,
    ) -> None:
        """Dispatch role-specific scope and lifecycle checks."""
        if context.role is AgentRole.DATA_RESEARCH:
            self._validate_data_scope(proposal, definition, context)
        elif context.role is AgentRole.STRATEGY_ENGINEERING:
            self._validate_strategy_lifecycle(proposal, context)
        elif context.role is AgentRole.RESEARCH_COORDINATOR:
            self._validate_coordinator_call(proposal, context)

    @staticmethod
    def _validate_data_scope(
        proposal: ToolCallProposal,
        definition: ToolDefinition,
        context: PolicyContext,
    ) -> None:
        """Reject Data calls outside the exact composite scope."""
        scope = context.data_scope
        if scope is None:
            raise PolicyViolation("data_scope_required", "Data Research requires a composite scope")
        if scope.session_id != context.session.session_id:
            raise PolicyViolation("data_scope_session_mismatch", "Data scope belongs to another session")
        if proposal.tool_name in {MCP_HEALTH, MCP_CONFIG}:
            return
        if proposal.tool_name == "data_ensure_loaded" and not scope.loading_approved:
            raise PolicyViolation(
                "data_loading_not_approved",
                "composite Data scope does not approve loading",
            )
        arguments = proposal.arguments
        requested_symbols = _string_sequence(arguments.get("symbols"), "symbols")
        if requested_symbols:
            allowed_symbols = {
                symbol
                for item in scope.items
                for symbol in item.symbols
            }
            outside = set(requested_symbols) - allowed_symbols
            if outside:
                raise PolicyViolation(
                    "data_scope_expansion",
                    "Data call contains symbols outside approved scope",
                    details={"outside_symbols": sorted(outside)},
                )
        provider = arguments.get("provider")
        if provider is not None:
            permitted = {
                item_provider
                for item in scope.items
                for item_provider in item.permitted_providers
            }
            if str(provider) not in permitted:
                raise PolicyViolation(
                    "data_provider_not_approved",
                    "Data call provider is outside the acquisition envelope",
                )
        for key in ("timeframe", "start", "end", "asset_class"):
            value = arguments.get(key)
            if value is None:
                continue
            if not any(str(getattr(item, key)) == str(value) for item in scope.items):
                raise PolicyViolation(
                    "data_scope_mismatch",
                    f"Data call {key} is outside approved scope",
                )
        if definition.side_effect is not SideEffect.READ_ONLY and not proposal.mutation_reason:
            raise PolicyViolation(
                "mutation_reason_required",
                "mutating Data call requires a public mutation reason",
            )

    @staticmethod
    def _validate_strategy_lifecycle(
        proposal: ToolCallProposal,
        context: PolicyContext,
    ) -> None:
        """Enforce catalogue-first, workspace, package, and admission ordering."""
        contract = context.build_contract
        if contract is None:
            raise PolicyViolation(
                "build_contract_required",
                "Strategy Engineering requires an accepted build contract",
            )
        if contract.session_id != context.session.session_id:
            raise PolicyViolation(
                "build_contract_session_mismatch",
                "build contract belongs to another research session",
            )
        name = proposal.tool_name
        state = context.runtime_state
        if name in {MCP_HEALTH, MCP_CONFIG}:
            return
        if name in {
            "research_get_implementation",
            "research_compare_implementation",
        } and not state.get("catalogue_searched"):
            raise PolicyViolation(
                "catalogue_search_required",
                "implementation resolution/comparison requires prior catalogue search",
            )
        if name == "coding_create_workspace":
            if state.get("build_decision") not in {"adapt", "author"}:
                raise PolicyViolation(
                    "build_decision_required",
                    "workspace creation requires an adapt or author decision",
                )
            _require_argument(
                proposal.arguments,
                "build_contract_id",
                contract.contract_id,
            )
            _require_argument(
                proposal.arguments,
                "attempt_id",
                context.delegation.attempt_id if context.delegation else "",
            )
        workspace_operations = {
            "coding_get_workspace",
            "coding_search_repository",
            "coding_read_repository_file",
            "coding_write_candidate_file",
            "coding_read_candidate_file",
            "coding_resolve_dependencies",
            "coding_run_check",
            "coding_package_candidate",
            "coding_destroy_workspace",
        }
        if name in workspace_operations and name not in {
            "coding_search_repository",
            "coding_read_repository_file",
        }:
            workspace_id = str(state.get("workspace_id") or "")
            if not workspace_id:
                raise PolicyViolation(
                    "workspace_required",
                    f"{name} requires an active workspace",
                )
            _require_argument(proposal.arguments, "workspace_id", workspace_id)
        if name.startswith("research_register_") and not state.get("package_id"):
            raise PolicyViolation(
                "candidate_package_required",
                "implementation registration requires an exact candidate package",
            )
        if name.startswith("research_validate_") and not state.get("implementation_ref"):
            raise PolicyViolation(
                "implementation_ref_required",
                "independent admission requires an exact implementation ref",
            )

    @staticmethod
    def _validate_coordinator_call(
        proposal: ToolCallProposal,
        context: PolicyContext,
    ) -> None:
        """Keep coordinator persistence and reads bound to its own session."""
        arguments = proposal.arguments
        if proposal.tool_name == "research_create_agent_session":
            session_payload = arguments.get("session")
            if not isinstance(session_payload, Mapping):
                raise PolicyViolation(
                    "session_payload_required",
                    "session creation requires a structured session payload",
                )
            if session_payload.get("session_id") != context.session.session_id:
                raise PolicyViolation(
                    "session_identity_mismatch",
                    "coordinator cannot create a different research session",
                )
        if proposal.tool_name == "research_get_agent_session":
            session_ref = str(arguments.get("session_ref") or "")
            allowed = {
                context.session.session_id,
                f"research://postgres/research_session/{context.session.session_id}",
            }
            if session_ref not in allowed:
                raise PolicyViolation(
                    "session_identity_mismatch",
                    "coordinator can resolve only its owning research session",
                )


@dataclass
class BudgetLedger:
    """Mutable in-process ledger for accepted model and MCP resource use."""

    budget: AgentBudget
    usage: BudgetUsage = field(default_factory=BudgetUsage)

    def record_model_call(
        self,
        *,
        input_tokens: int,
        output_tokens: int,
        duration_ms: int,
    ) -> BudgetUsage:
        """Record one completed model call and enforce hard limits."""
        candidate = self.usage.model_copy(
            update={
                "model_calls": self.usage.model_calls + 1,
                "input_tokens": self.usage.input_tokens + input_tokens,
                "output_tokens": self.usage.output_tokens + output_tokens,
                "duration_ms": self.usage.duration_ms + duration_ms,
            }
        )
        self._validate(candidate)
        self.usage = candidate
        return candidate

    def record_tool_call(
        self,
        *,
        side_effect: SideEffect,
        duration_ms: int,
    ) -> BudgetUsage:
        """Record one accepted MCP call and enforce hard limits."""
        candidate = self.usage.model_copy(
            update={
                "tool_calls": self.usage.tool_calls + 1,
                "duration_ms": self.usage.duration_ms + duration_ms,
                "mutations": self.usage.mutations
                + (0 if side_effect is SideEffect.READ_ONLY else 1),
            }
        )
        self._validate(candidate)
        self.usage = candidate
        return candidate

    def record_revision(self) -> BudgetUsage:
        """Record one material model/tool loop revision."""
        candidate = self.usage.model_copy(
            update={"revisions": self.usage.revisions + 1}
        )
        self._validate(candidate)
        self.usage = candidate
        return candidate

    def _validate(self, usage: BudgetUsage) -> None:
        """Reject usage beyond the immutable session budget."""
        exceeded = []
        if usage.model_calls > self.budget.max_model_calls:
            exceeded.append("model_calls")
        if usage.tool_calls > self.budget.max_tool_calls:
            exceeded.append("tool_calls")
        if usage.total_tokens > self.budget.max_tokens:
            exceeded.append("tokens")
        if usage.duration_ms > self.budget.max_duration_seconds * 1_000:
            exceeded.append("duration")
        if usage.mutations > self.budget.max_mutations:
            exceeded.append("mutations")
        if usage.revisions > self.budget.max_revisions:
            exceeded.append("revisions")
        if exceeded:
            raise PolicyViolation(
                "session_budget_exceeded",
                "session budget exceeded: " + ", ".join(exceeded),
            )


MCP_HEALTH = "mcp_health"
MCP_CONFIG = "mcp_get_config"


def _string_sequence(value: object, label: str) -> tuple[str, ...]:
    """Normalize an optional JSON string sequence."""
    if value is None:
        return ()
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise PolicyViolation("invalid_tool_arguments", f"{label} must be a list")
    normalized = tuple(str(item).strip() for item in value)
    if any(not item for item in normalized):
        raise PolicyViolation("invalid_tool_arguments", f"{label} contains an empty value")
    return normalized


def _require_argument(
    arguments: Mapping[str, Any],
    key: str,
    expected: str,
) -> None:
    """Require one exact lifecycle-bound model argument."""
    if not expected or str(arguments.get(key) or "") != expected:
        raise PolicyViolation(
            "lifecycle_identity_mismatch",
            f"tool argument {key} does not match accepted runtime state",
        )
