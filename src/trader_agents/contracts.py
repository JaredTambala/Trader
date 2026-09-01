"""Strict public contracts for the model-backed research-agent runtime.

The contracts in this module are the only model-produced values allowed to
influence orchestration. They contain public decisions and bounded evidence,
never prompts, hidden reasoning, credentials, or raw tool transcripts.
"""

from __future__ import annotations

from enum import Enum
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from trader_research.foundation import stable_research_id


class StrictPublicModel(BaseModel):
    """Base model for immutable public agent values with no unknown fields."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )


class AgentRole(str, Enum):
    """Model-backed roles admitted by the first agentic slice."""

    RESEARCH_COORDINATOR = "research_coordinator"
    DATA_RESEARCH = "data_research"
    STRATEGY_ENGINEERING = "strategy_engineering"


class AgentPhase(str, Enum):
    """Policy-relevant phase of one agent invocation."""

    INTERPRET = "interpret"
    INVESTIGATE = "investigate"
    REMEDIATE = "remediate"
    CONSTRUCT = "construct"
    ADMIT = "admit"
    REVIEW = "review"
    AWAITING_OPERATOR = "awaiting_operator"
    TERMINAL = "terminal"


class PublicIssue(StrictPublicModel):
    """Bounded actionable warning, blocker, or error."""

    code: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=1_000)
    details: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_details(self) -> "PublicIssue":
        """Require JSON-safe bounded issue details."""
        _validate_json_mapping(self.details, "issue details", max_bytes=8_000)
        return self


class CanonicalEvidenceRef(StrictPublicModel):
    """Exact canonical research artifact identity cited by an agent."""

    artifact_type: str = Field(min_length=1, max_length=100)
    artifact_id: str = Field(min_length=1, max_length=200)
    domain_owner: str = Field(min_length=1, max_length=100)
    uri: str = Field(min_length=1, max_length=500)
    source_hash: str | None = Field(default=None, min_length=64, max_length=64)

    @model_validator(mode="after")
    def validate_uri_identity(self) -> "CanonicalEvidenceRef":
        """Require the URI to encode the declared exact type and identity."""
        expected = f"research://postgres/{self.artifact_type}/{self.artifact_id}"
        if self.uri != expected:
            raise ValueError("canonical evidence URI does not match type and identity")
        return self


class BudgetUsage(StrictPublicModel):
    """Cumulative public resource use at an accepted runtime transition."""

    model_calls: int = Field(default=0, ge=0)
    tool_calls: int = Field(default=0, ge=0)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    duration_ms: int = Field(default=0, ge=0)
    mutations: int = Field(default=0, ge=0)
    revisions: int = Field(default=0, ge=0)

    @property
    def total_tokens(self) -> int:
        """Return aggregate provider input and output tokens."""
        return self.input_tokens + self.output_tokens


class ToolCallProposal(StrictPublicModel):
    """One model-proposed MCP call awaiting deterministic authorization."""

    call_id: str = Field(min_length=1, max_length=200)
    tool_name: str = Field(min_length=1, max_length=150)
    arguments: dict[str, Any]
    purpose: str = Field(min_length=1, max_length=600)
    expected_evidence: list[str] = Field(min_length=1, max_length=8)
    mutation_reason: str | None = Field(default=None, max_length=600)

    @model_validator(mode="after")
    def validate_arguments(self) -> "ToolCallProposal":
        """Require bounded JSON-native arguments and mutation explanation."""
        _validate_json_mapping(self.arguments, "tool arguments", max_bytes=64_000)
        return self


class ToolObservation(StrictPublicModel):
    """Bounded normalized observation returned to a model after an MCP call."""

    call_id: str = Field(min_length=1, max_length=200)
    tool_name: str = Field(min_length=1, max_length=150)
    ok: bool
    command: str = Field(min_length=1, max_length=150)
    agent_owner: str = Field(min_length=1, max_length=100)
    side_effect: Literal["read_only", "local_mutating", "external_research_mutating"]
    summary: dict[str, Any] = Field(default_factory=dict)
    evidence_refs: list[CanonicalEvidenceRef] = Field(
        default_factory=list, max_length=16
    )
    warnings: list[PublicIssue] = Field(default_factory=list, max_length=16)
    errors: list[PublicIssue] = Field(default_factory=list, max_length=16)

    @model_validator(mode="after")
    def validate_observation(self) -> "ToolObservation":
        """Require consistent success/error state and bounded public summary."""
        _validate_json_mapping(
            self.summary, "tool observation summary", max_bytes=32_000
        )
        if self.ok and self.errors:
            raise ValueError("successful tool observation cannot contain errors")
        if not self.ok and not self.errors:
            raise ValueError("failed tool observation requires at least one error")
        return self


class AgendaTaskProposal(StrictPublicModel):
    """One model-proposed specialist task on the visible research agenda."""

    task_id: str = Field(min_length=1, max_length=200)
    role: Literal["data_research", "strategy_engineering"]
    work_kind: Literal[
        "complete",
        "investigate",
        "reconcile",
        "catalogue",
        "construct",
    ] = "complete"
    join_mode: Literal["soft", "hard"] = "hard"
    scope_item_ids: list[str] = Field(default_factory=list, max_length=12)
    question: str = Field(min_length=1, max_length=800)
    required_evidence: list[str] = Field(min_length=1, max_length=12)
    dependencies: list[str] = Field(default_factory=list, max_length=12)
    expected_information_gain: str = Field(min_length=1, max_length=600)
    mutation_requested: bool = False

    @model_validator(mode="after")
    def validate_role_work(self) -> "AgendaTaskProposal":
        """Reject work kinds that cross specialist ownership boundaries."""
        allowed = {
            AgentRole.DATA_RESEARCH.value: {
                "complete",
                "investigate",
                "reconcile",
            },
            AgentRole.STRATEGY_ENGINEERING.value: {
                "complete",
                "catalogue",
                "construct",
            },
        }
        if self.work_kind not in allowed[self.role]:
            raise ValueError(f"{self.work_kind} is not valid for role {self.role}")
        if self.role == AgentRole.STRATEGY_ENGINEERING.value and self.scope_item_ids:
            raise ValueError("Strategy tasks cannot claim Data scope items")
        if len(set(self.scope_item_ids)) != len(self.scope_item_ids):
            raise ValueError("scope_item_ids must be unique")
        return self


class CoordinatorAgenda(StrictPublicModel):
    """Model-produced visible agenda for the approved session boundary."""

    objective_summary: str = Field(min_length=1, max_length=1_200)
    material_ambiguities: list[str] = Field(default_factory=list, max_length=12)
    tasks: list[AgendaTaskProposal] = Field(default_factory=list, max_length=16)

    @model_validator(mode="after")
    def validate_task_graph(self) -> "CoordinatorAgenda":
        """Reject duplicate, unknown, self-referential, or cyclic tasks."""
        task_ids = [task.task_id for task in self.tasks]
        if len(set(task_ids)) != len(task_ids):
            raise ValueError("agenda task IDs must be unique")
        known = set(task_ids)
        for task in self.tasks:
            unknown = set(task.dependencies) - known
            if unknown:
                raise ValueError(
                    "agenda task dependencies are unknown: "
                    + ", ".join(sorted(unknown))
                )
            if task.task_id in task.dependencies:
                raise ValueError("agenda task cannot depend on itself")
        dependencies = {task.task_id: set(task.dependencies) for task in self.tasks}
        while dependencies:
            ready = {
                task_id for task_id, required in dependencies.items() if not required
            }
            if not ready:
                raise ValueError("agenda task dependencies contain a cycle")
            dependencies = {
                task_id: required - ready
                for task_id, required in dependencies.items()
                if task_id not in ready
            }
        if not self.material_ambiguities and not self.tasks:
            raise ValueError("agenda requires tasks or a material ambiguity")
        return self


class SpecialistDelegation(StrictPublicModel):
    """Deterministically admitted specialist invocation boundary."""

    delegation_id: str = Field(min_length=1, max_length=200)
    session_id: str = Field(min_length=1, max_length=200)
    branch_id: str = Field(min_length=1, max_length=200)
    attempt_id: str = Field(min_length=1, max_length=200)
    task: AgendaTaskProposal
    required_input_refs: list[CanonicalEvidenceRef] = Field(
        default_factory=list, max_length=16
    )
    permitted_side_effects: list[
        Literal["read_only", "local_mutating", "external_research_mutating"]
    ] = Field(min_length=1, max_length=3)
    reserved_model_calls: int = Field(gt=0, le=24)
    reserved_tool_calls: int = Field(gt=0, le=24)
    reserved_tokens: int = Field(gt=0, le=12_000)
    expected_information_gain: str = Field(min_length=1, max_length=600)


class SpecialistStatus(str, Enum):
    """Terminal status of one isolated specialist invocation."""

    READY = "ready"
    CONDITIONAL = "conditional"
    PARTIAL = "partial"
    BLOCKED = "blocked"
    FAILED = "failed"


class SpecialistReturn(StrictPublicModel):
    """Bounded public result returned through the coordinator."""

    delegation_id: str = Field(min_length=1, max_length=200)
    session_id: str = Field(min_length=1, max_length=200)
    branch_id: str = Field(min_length=1, max_length=200)
    attempt_id: str = Field(min_length=1, max_length=200)
    role: Literal["data_research", "strategy_engineering"]
    program_id: str = Field(min_length=1, max_length=200)
    model_profile_id: str = Field(min_length=1, max_length=200)
    tool_catalog_id: str = Field(min_length=1, max_length=200)
    status: SpecialistStatus
    answered_questions: list[str] = Field(default_factory=list, max_length=16)
    unresolved_questions: list[str] = Field(default_factory=list, max_length=16)
    findings: list[str] = Field(default_factory=list, max_length=24)
    evidence_refs: list[CanonicalEvidenceRef] = Field(
        default_factory=list, max_length=24
    )
    assumptions: list[str] = Field(default_factory=list, max_length=12)
    uncertainty: list[str] = Field(default_factory=list, max_length=12)
    blockers: list[PublicIssue] = Field(default_factory=list, max_length=16)
    advisory_next_actions: list[str] = Field(default_factory=list, max_length=12)
    budget_used: BudgetUsage

    @model_validator(mode="after")
    def validate_status_evidence(self) -> "SpecialistReturn":
        """Reject terminal states that contradict blockers or evidence."""
        if self.status is SpecialistStatus.READY and self.blockers:
            raise ValueError("ready specialist return cannot contain blockers")
        if (
            self.status in {SpecialistStatus.BLOCKED, SpecialistStatus.FAILED}
            and not self.blockers
        ):
            raise ValueError("blocked or failed specialist return requires blockers")
        if self.status is SpecialistStatus.READY and not self.evidence_refs:
            raise ValueError("ready specialist return requires canonical evidence")
        uris = [reference.uri for reference in self.evidence_refs]
        if len(set(uris)) != len(uris):
            raise ValueError("specialist evidence refs must be unique")
        return self


class SpecialistConclusion(StrictPublicModel):
    """Model-owned domain verdict without runtime-controlled identities."""

    status: SpecialistStatus
    answered_questions: list[str] = Field(default_factory=list, max_length=16)
    unresolved_questions: list[str] = Field(default_factory=list, max_length=16)
    findings: list[str] = Field(default_factory=list, max_length=24)
    evidence_refs: list[CanonicalEvidenceRef] = Field(
        default_factory=list, max_length=24
    )
    assumptions: list[str] = Field(default_factory=list, max_length=12)
    uncertainty: list[str] = Field(default_factory=list, max_length=12)
    blockers: list[PublicIssue] = Field(default_factory=list, max_length=16)
    advisory_next_actions: list[str] = Field(default_factory=list, max_length=12)

    @model_validator(mode="after")
    def validate_status_evidence(self) -> "SpecialistConclusion":
        """Apply the same evidence invariants as a returned specialist result."""
        if self.status is SpecialistStatus.READY and self.blockers:
            raise ValueError("ready specialist conclusion cannot contain blockers")
        if self.status in {SpecialistStatus.BLOCKED, SpecialistStatus.FAILED}:
            if not self.blockers:
                raise ValueError("blocked or failed conclusion requires blockers")
        if self.status is SpecialistStatus.READY and not self.evidence_refs:
            raise ValueError("ready specialist conclusion requires canonical evidence")
        uris = [reference.uri for reference in self.evidence_refs]
        if len(set(uris)) != len(uris):
            raise ValueError("specialist conclusion evidence refs must be unique")
        return self


class CoordinatorAction(str, Enum):
    """Evidence-review action available to the first-slice coordinator."""

    ADVANCE = "advance"
    REVISE = "revise"
    REVISIT = "revisit"
    FORK = "fork"
    ASK_OPERATOR = "ask_operator"
    CONCLUDE = "conclude"
    STOP_FAIL_CLOSED = "stop_fail_closed"


class CoordinatorDecision(StrictPublicModel):
    """One model-proposed public transition after evidence review."""

    action: CoordinatorAction
    summary: str = Field(min_length=1, max_length=1_500)
    reviewed_delegation_ids: list[str] = Field(default_factory=list, max_length=16)
    cited_evidence_refs: list[CanonicalEvidenceRef] = Field(
        default_factory=list, max_length=24
    )
    criteria_applied: list[str] = Field(min_length=1, max_length=16)
    affected_task_ids: list[str] = Field(default_factory=list, max_length=16)
    expected_information_gain: str | None = Field(default=None, max_length=600)
    operator_question: str | None = Field(default=None, max_length=800)
    blockers: list[PublicIssue] = Field(default_factory=list, max_length=16)
    permitted_next_actions: list[str] = Field(default_factory=list, max_length=12)

    @model_validator(mode="after")
    def validate_action_fields(self) -> "CoordinatorDecision":
        """Require action-specific public evidence and escalation fields."""
        if self.action is CoordinatorAction.ASK_OPERATOR and not self.operator_question:
            raise ValueError("ask_operator decision requires operator_question")
        if self.action is not CoordinatorAction.ASK_OPERATOR and self.operator_question:
            raise ValueError("operator_question is allowed only for ask_operator")
        if (
            self.action
            in {
                CoordinatorAction.REVISE,
                CoordinatorAction.REVISIT,
                CoordinatorAction.FORK,
            }
            and not self.expected_information_gain
        ):
            raise ValueError(
                "revision, revisit, or fork requires expected information gain"
            )
        if self.action is CoordinatorAction.STOP_FAIL_CLOSED and not self.blockers:
            raise ValueError("stop_fail_closed requires blockers")
        if self.action is CoordinatorAction.CONCLUDE and not self.cited_evidence_refs:
            raise ValueError("conclude requires canonical evidence")
        return self


class DataAgentTurn(StrictPublicModel):
    """One model-owned Data Research control-loop decision."""

    action: Literal["call_tool", "change_phase", "return_result"]
    public_rationale: str = Field(min_length=1, max_length=800)
    tool_call: ToolCallProposal | None = None
    next_phase: Literal["remediate", "review"] | None = None
    final_conclusion: SpecialistConclusion | None = None

    @model_validator(mode="after")
    def validate_action_payload(self) -> "DataAgentTurn":
        """Require exactly the payload belonging to the selected action."""
        expected = {
            "call_tool": (self.tool_call is not None),
            "change_phase": (self.next_phase is not None),
            "return_result": (self.final_conclusion is not None),
        }
        if not expected[self.action]:
            raise ValueError(f"{self.action} requires its matching payload")
        populated = sum(
            value is not None
            for value in (self.tool_call, self.next_phase, self.final_conclusion)
        )
        if populated != 1:
            raise ValueError("Data turn must contain exactly one action payload")
        return self


class StrategyAgentTurn(StrictPublicModel):
    """One model-owned Strategy Engineering control-loop decision."""

    action: Literal[
        "call_tool",
        "choose_build",
        "change_phase",
        "return_result",
    ]
    public_rationale: str = Field(min_length=1, max_length=800)
    tool_call: ToolCallProposal | None = None
    build_decision: Literal["reuse", "adapt", "author"] | None = None
    next_phase: Literal["construct", "admit"] | None = None
    final_conclusion: SpecialistConclusion | None = None

    @model_validator(mode="after")
    def validate_action_payload(self) -> "StrategyAgentTurn":
        """Require exactly the payload belonging to the selected action."""
        expected = {
            "call_tool": self.tool_call is not None,
            "choose_build": self.build_decision is not None,
            "change_phase": self.next_phase is not None,
            "return_result": self.final_conclusion is not None,
        }
        if not expected[self.action]:
            raise ValueError(f"{self.action} requires its matching payload")
        populated = sum(
            value is not None
            for value in (
                self.tool_call,
                self.build_decision,
                self.next_phase,
                self.final_conclusion,
            )
        )
        if populated != 1:
            raise ValueError("Strategy turn must contain exactly one action payload")
        return self


class AgenticSliceResult(StrictPublicModel):
    """Grounded terminal or interrupted result returned to an operator."""

    session_id: str = Field(min_length=1, max_length=200)
    branch_id: str = Field(min_length=1, max_length=200)
    status: Literal[
        "completed",
        "awaiting_operator",
        "blocked",
        "cancelled",
        "failed",
    ]
    summary: str = Field(min_length=1, max_length=2_000)
    data_return: SpecialistReturn | None = None
    strategy_return: SpecialistReturn | None = None
    decision: CoordinatorDecision
    decision_receipt_ref: CanonicalEvidenceRef | None = None
    budget_used: BudgetUsage
    permitted_next_actions: list[str] = Field(default_factory=list, max_length=12)

    @model_validator(mode="after")
    def validate_terminal_result(self) -> "AgenticSliceResult":
        """Require status and coordinator action to agree."""
        expected_actions = {
            "completed": {CoordinatorAction.CONCLUDE},
            "awaiting_operator": {CoordinatorAction.ASK_OPERATOR},
            "blocked": {CoordinatorAction.STOP_FAIL_CLOSED},
            "cancelled": {CoordinatorAction.STOP_FAIL_CLOSED},
            "failed": {CoordinatorAction.STOP_FAIL_CLOSED},
        }
        if self.decision.action not in expected_actions[self.status]:
            raise ValueError("slice status contradicts coordinator decision")
        return self


class OperatorInterrupt(StrictPublicModel):
    """Bounded request returned when coordinator authority is insufficient."""

    session_id: str = Field(min_length=1, max_length=200)
    kind: str = Field(min_length=1, max_length=100)
    question: str = Field(min_length=1, max_length=800)
    requested_action: str = Field(min_length=1, max_length=200)
    resume_schema: dict[str, Any]

    @model_validator(mode="after")
    def validate_resume_schema(self) -> "OperatorInterrupt":
        """Require a bounded JSON-native resume schema."""
        _validate_json_mapping(
            self.resume_schema,
            "operator resume schema",
            max_bytes=8_000,
        )
        return self


class OperatorResponse(StrictPublicModel):
    """Bounded public value used to resume one operator interrupt."""

    approved: bool
    answer: str = Field(min_length=1, max_length=2_000)
    operator_id: str = Field(min_length=1, max_length=200)


class OperatorCancellation(StrictPublicModel):
    """Explicit operator request to terminate one checkpointed session."""

    operator_id: str = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=1, max_length=2_000)


class DataScopeItem(StrictPublicModel):
    """One role-labelled item in a composite market-data requirement."""

    item_id: str = Field(min_length=1, max_length=200)
    data_role: str = Field(min_length=1, max_length=100)
    symbols: list[str] = Field(default_factory=list, max_length=500)
    universe_rule: str | None = Field(default=None, max_length=600)
    asset_class: str = Field(min_length=1, max_length=100)
    data_type: str = Field(min_length=1, max_length=100)
    fields: list[str] = Field(min_length=1, max_length=64)
    timeframe: str = Field(min_length=1, max_length=50)
    start: str = Field(min_length=1, max_length=100)
    end: str = Field(min_length=1, max_length=100)
    warmup_bars: int = Field(default=0, ge=0, le=1_000_000)
    permitted_providers: list[str] = Field(min_length=1, max_length=16)
    quality_requirements: list[str] = Field(min_length=1, max_length=24)
    requirement_sources: list[str] = Field(min_length=1, max_length=16)

    @model_validator(mode="after")
    def validate_scope_selector(self) -> "DataScopeItem":
        """Require exactly one fixed-symbol or universe-rule selector."""
        if bool(self.symbols) == bool(self.universe_rule):
            raise ValueError("scope item requires symbols or universe_rule, not both")
        if len(set(self.symbols)) != len(self.symbols):
            raise ValueError("scope item symbols must be unique")
        return self


class CompositeDataScope(StrictPublicModel):
    """Complete approved Data requirement for one research session."""

    scope_id: str = Field(min_length=1, max_length=200)
    session_id: str = Field(min_length=1, max_length=200)
    items: list[DataScopeItem] = Field(min_length=1, max_length=64)
    loading_approved: bool
    max_loading_cost: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_items(self) -> "CompositeDataScope":
        """Reject duplicate items or an unbounded approved acquisition."""
        item_ids = [item.item_id for item in self.items]
        if len(set(item_ids)) != len(item_ids):
            raise ValueError("composite Data scope item IDs must be unique")
        if self.loading_approved and self.max_loading_cost is None:
            raise ValueError(
                "an approved Data loading scope requires max_loading_cost"
            )
        return self


class DataInputRole(StrictPublicModel):
    """One implementation input and its required Data semantics."""

    role: str = Field(min_length=1, max_length=100)
    fields: list[str] = Field(min_length=1, max_length=32)
    timeframe: str = Field(min_length=1, max_length=50)
    units: str = Field(min_length=1, max_length=100)
    timing: str = Field(min_length=1, max_length=300)


class ParameterContract(StrictPublicModel):
    """Typed parameter semantics pinned before source authoring."""

    name: str = Field(min_length=1, max_length=100)
    value_type: Literal["integer", "number", "boolean", "string"]
    default: int | float | bool | str
    minimum: int | float | None = None
    maximum: int | float | None = None
    tunable: bool
    semantics: str = Field(min_length=1, max_length=600)

    @model_validator(mode="after")
    def validate_bounds(self) -> "ParameterContract":
        """Reject type mismatches, invalid bounds, and out-of-range defaults."""
        if self.value_type == "integer":
            if isinstance(self.default, bool) or not isinstance(self.default, int):
                raise ValueError("integer parameter default must be an integer")
        elif self.value_type == "number":
            if isinstance(self.default, bool) or not isinstance(
                self.default,
                (int, float),
            ):
                raise ValueError("number parameter default must be numeric")
        elif self.value_type == "boolean" and not isinstance(self.default, bool):
            raise ValueError("boolean parameter default must be a boolean")
        elif self.value_type == "string" and not isinstance(self.default, str):
            raise ValueError("string parameter default must be a string")
        if self.minimum is not None and self.maximum is not None:
            if self.minimum > self.maximum:
                raise ValueError("parameter minimum cannot exceed maximum")
        if self.minimum is not None or self.maximum is not None:
            if self.value_type not in {"integer", "number"}:
                raise ValueError("only numeric parameters may declare bounds")
            numeric_default = float(self.default)
            if self.minimum is not None and numeric_default < self.minimum:
                raise ValueError("parameter default is below minimum")
            if self.maximum is not None and numeric_default > self.maximum:
                raise ValueError("parameter default is above maximum")
        return self


class StrategyBuildContract(StrictPublicModel):
    """Behaviorally complete deterministic input to Strategy Engineering."""

    contract_id: str = Field(min_length=1, max_length=200)
    session_id: str = Field(min_length=1, max_length=200)
    branch_id: str = Field(min_length=1, max_length=200)
    approval_id: str = Field(min_length=1, max_length=200)
    provenance: Literal["source_backed", "operator_specified"]
    implementation_kind: Literal["strategy", "risk_manager"]
    name: str = Field(min_length=1, max_length=200)
    runtime_interface: str = Field(min_length=1, max_length=200)
    portfolio_mode: str = Field(min_length=1, max_length=100)
    decision_rules: list[str] = Field(min_length=1, max_length=32)
    state_transitions: list[str] = Field(min_length=1, max_length=32)
    timing: str = Field(min_length=1, max_length=600)
    warmup_bars: int = Field(ge=0, le=1_000_000)
    missing_value_policy: str = Field(min_length=1, max_length=600)
    failure_behavior: str = Field(min_length=1, max_length=600)
    input_roles: list[DataInputRole] = Field(min_length=1, max_length=32)
    parameters: list[ParameterContract] = Field(default_factory=list, max_length=64)
    responsibilities: list[str] = Field(min_length=1, max_length=32)
    permitted_dependencies: list[str] = Field(default_factory=list, max_length=32)
    required_fixtures: list[str] = Field(min_length=1, max_length=32)
    trader_interface_version: str = Field(min_length=1, max_length=100)
    python_version: str = Field(min_length=1, max_length=50)
    code_quality_ref: str = Field(min_length=1, max_length=300)
    repository_revision: str = Field(min_length=7, max_length=64)
    max_repairs: int = Field(ge=0, le=2)

    @model_validator(mode="after")
    def validate_unique_contract_fields(self) -> "StrategyBuildContract":
        """Reject duplicate input roles and parameter names."""
        roles = [item.role for item in self.input_roles]
        parameters = [item.name for item in self.parameters]
        if len(set(roles)) != len(roles):
            raise ValueError("build contract input roles must be unique")
        if len(set(parameters)) != len(parameters):
            raise ValueError("build contract parameter names must be unique")
        return self


def build_delegation(
    *,
    session_id: str,
    branch_id: str,
    task: AgendaTaskProposal,
    required_input_refs: list[CanonicalEvidenceRef],
    permitted_side_effects: list[
        Literal["read_only", "local_mutating", "external_research_mutating"]
    ],
    reserved_model_calls: int,
    reserved_tool_calls: int,
    reserved_tokens: int,
    attempt: int,
) -> SpecialistDelegation:
    """Build one content-derived specialist delegation.

    Args:
        session_id: Owning immutable research session.
        branch_id: Owning research branch.
        task: Accepted agenda task.
        required_input_refs: Exact canonical inputs available to the specialist.
        permitted_side_effects: Maximum admitted side-effect classes.
        reserved_model_calls: Model-call reservation for the invocation.
        reserved_tool_calls: MCP-call reservation for the invocation.
        reserved_tokens: Token reservation for the invocation.
        attempt: Positive immutable attempt number for the task.

    Returns:
        Strict delegation with content-derived delegation and attempt IDs.
    """
    if attempt <= 0:
        raise ValueError("delegation attempt must be positive")
    identity = {
        "session_id": session_id,
        "branch_id": branch_id,
        "task": task.model_dump(mode="json"),
        "required_input_refs": [
            reference.model_dump(mode="json") for reference in required_input_refs
        ],
        "permitted_side_effects": permitted_side_effects,
        "attempt": attempt,
    }
    delegation_id = stable_research_id("specialist_delegation", identity)
    attempt_id = stable_research_id(
        "specialist_attempt",
        {"delegation_id": delegation_id, "attempt": attempt},
    )
    return SpecialistDelegation(
        delegation_id=delegation_id,
        session_id=session_id,
        branch_id=branch_id,
        attempt_id=attempt_id,
        task=task,
        required_input_refs=required_input_refs,
        permitted_side_effects=permitted_side_effects,
        reserved_model_calls=reserved_model_calls,
        reserved_tool_calls=reserved_tool_calls,
        reserved_tokens=reserved_tokens,
        expected_information_gain=task.expected_information_gain,
    )


def build_specialist_return(
    *,
    delegation: SpecialistDelegation,
    role: Literal["data_research", "strategy_engineering"],
    program_id: str,
    model_profile_id: str,
    tool_catalog_id: str,
    conclusion: SpecialistConclusion,
    budget_used: BudgetUsage,
    available_evidence_refs: list[CanonicalEvidenceRef],
) -> SpecialistReturn:
    """Attach trusted identities and measured usage to a model conclusion.

    Args:
        delegation: Exact accepted specialist boundary.
        role: Active specialist role.
        program_id: Code-owned versioned agent program.
        model_profile_id: Code-owned model profile identity.
        tool_catalog_id: Code-owned MCP catalogue identity.
        conclusion: Strict model-owned evidence verdict.
        budget_used: Deterministically metered invocation usage.
        available_evidence_refs: Canonical refs observed through MCP.

    Returns:
        Complete trusted specialist return.

    Raises:
        ValueError: If the conclusion cites evidence it never observed.
    """
    available_by_uri = {
        reference.uri: reference for reference in available_evidence_refs
    }
    cited_uris = {reference.uri for reference in conclusion.evidence_refs}
    unavailable = cited_uris - set(available_by_uri)
    if unavailable:
        raise ValueError(
            "specialist conclusion cites unavailable evidence: "
            + ", ".join(sorted(unavailable))
        )
    trusted_evidence = [
        available_by_uri[reference.uri] for reference in conclusion.evidence_refs
    ]
    return SpecialistReturn(
        delegation_id=delegation.delegation_id,
        session_id=delegation.session_id,
        branch_id=delegation.branch_id,
        attempt_id=delegation.attempt_id,
        role=role,
        program_id=program_id,
        model_profile_id=model_profile_id,
        tool_catalog_id=tool_catalog_id,
        status=conclusion.status,
        answered_questions=conclusion.answered_questions,
        unresolved_questions=conclusion.unresolved_questions,
        findings=conclusion.findings,
        evidence_refs=trusted_evidence,
        assumptions=conclusion.assumptions,
        uncertainty=conclusion.uncertainty,
        blockers=conclusion.blockers,
        advisory_next_actions=conclusion.advisory_next_actions,
        budget_used=budget_used,
    )


def _validate_json_mapping(
    payload: dict[str, Any],
    label: str,
    *,
    max_bytes: int,
) -> None:
    """Reject non-JSON or oversized mapping content."""
    try:
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be JSON-native") from exc
    if len(encoded) > max_bytes:
        raise ValueError(f"{label} exceeds {max_bytes} bytes")
