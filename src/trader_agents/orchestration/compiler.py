"""Deterministic compiler for the supplied-implementation evidence workflow."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Sequence

from trader_mcp.constants import (
    ADVERSARIAL_CREATE_PARAMETER_OPTIMIZATION_AUDIT_PLAN_TOOL,
    ADVERSARIAL_GENERATE_PARAMETER_OPTIMIZATION_AUDIT_TOOL,
    EVALUATION_GENERATE_PARAMETER_OPTIMIZATION_REPORT_TOOL,
    RESEARCH_CREATE_BACKTEST_SPECIFICATION_TOOL,
    RESEARCH_CREATE_PARAMETER_OPTIMIZATION_PLAN_TOOL,
    RESEARCH_CREATE_RISK_STACK_SPECIFICATION_TOOL,
    RESEARCH_CREATE_STRATEGY_SPECIFICATION_TOOL,
    RESEARCH_RUN_BACKTEST_SPECIFICATION_TOOL,
    RESEARCH_RUN_PARAMETER_OPTIMIZATION_TOOL,
    RESEARCH_RUN_PARAMETER_OPTIMIZATION_VARIANTS_TOOL,
    RESEARCH_VALIDATE_BACKTEST_SPECIFICATION_TOOL,
    RESEARCH_VALIDATE_RISK_MANAGER_IMPLEMENTATION_TOOL,
    RESEARCH_VALIDATE_RISK_STACK_SPECIFICATION_TOOL,
    RESEARCH_VALIDATE_STRATEGY_IMPLEMENTATION_TOOL,
    RESEARCH_VALIDATE_STRATEGY_SPECIFICATION_TOOL,
)
from trader_research.foundation import (
    ResearchArtifactStore,
    ResearchArtifactStoreError,
    json_payload_hash,
    stable_research_id,
)
from trader_research.governance import (
    ApprovalStatus,
    ArtifactCardinality,
    ArtifactReportRef,
    ArtifactSlot,
    ArtifactSlotStatus,
    BACKTEST_RUN,
    BACKTEST_SPECIFICATION,
    BACKTEST_SPECIFICATION_VALIDATION_REPORT,
    CapabilityDefinition,
    CapabilitySideEffect,
    DOMAIN_OWNER_BY_ARTIFACT_TYPE,
    DatasetRole,
    EXPERIMENT_PROTOCOL,
    ExperimentProtocol,
    ExperimentProtocolStatus,
    IMPLEMENTATION_VALIDATION_REPORT,
    PARAMETER_OPTIMIZATION_AUDIT_PLAN,
    PARAMETER_OPTIMIZATION_EVALUATION_REPORT,
    PARAMETER_OPTIMIZATION_PLAN,
    PARAMETER_OPTIMIZATION_ROBUSTNESS_REPORT,
    PARAMETER_OPTIMIZATION_RUN,
    RESEARCH_OBJECTIVE,
    RISK_STACK_SPECIFICATION,
    RISK_STACK_SPECIFICATION_VALIDATION_REPORT,
    ResearchObjective,
    ResearchObjectiveStatus,
    STRATEGY_SPECIFICATION,
    STRATEGY_SPECIFICATION_VALIDATION_REPORT,
    WorkflowPlan,
    WorkflowPlanStatus,
    WorkflowStep,
    artifact_report_ref,
)


WORKFLOW_TEMPLATE_ID = "supplied_implementation_to_evidence"
WORKFLOW_TEMPLATE_VERSION = "1"
_INVOCATION_CONFIGURATION_KEY = "invocation"


class InvocationMode(str, Enum):
    """Closed invocation-building modes understood by the executor."""

    DIRECT = "direct"
    RISK_STACK = "risk_stack"
    SELECTED_HOLDOUT_BACKTEST = "selected_holdout_backtest"


@dataclass(frozen=True)
class ToolInvocation:
    """Closed MCP argument recipe embedded in a compiled workflow step."""

    tool_name: str
    mode: InvocationMode = InvocationMode.DIRECT
    static_arguments: Mapping[str, Any] = field(default_factory=dict)
    ref_arguments: Mapping[str, str] = field(default_factory=dict)
    payload_arguments: Mapping[str, str] = field(default_factory=dict)
    ref_list_arguments: Mapping[str, str] = field(default_factory=dict)
    risk_entries: tuple[Mapping[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """Serialize the closed argument recipe into the workflow plan."""
        return {
            "tool_name": self.tool_name,
            "mode": self.mode.value,
            "static_arguments": dict(self.static_arguments),
            "ref_arguments": dict(self.ref_arguments),
            "payload_arguments": dict(self.payload_arguments),
            "ref_list_arguments": dict(self.ref_list_arguments),
            "risk_entries": [dict(item) for item in self.risk_entries],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ToolInvocation":
        """Parse a closed argument recipe from a compiled workflow step."""
        return cls(
            tool_name=_required_text(payload.get("tool_name"), "tool_name"),
            mode=InvocationMode(
                _required_text(payload.get("mode"), "invocation mode")
            ),
            static_arguments=_mapping(payload.get("static_arguments")),
            ref_arguments=_text_mapping(payload.get("ref_arguments")),
            payload_arguments=_text_mapping(payload.get("payload_arguments")),
            ref_list_arguments=_text_mapping(
                payload.get("ref_list_arguments")
            ),
            risk_entries=tuple(
                _mapping(item)
                for item in _sequence(payload.get("risk_entries"))
            ),
        )


@dataclass(frozen=True)
class CompiledResearchWorkflow:
    """Approved protocol plus its deterministic executable workflow plan."""

    objective: ResearchObjective
    protocol: ExperimentProtocol
    plan: WorkflowPlan

    def invocation_for_step(self, step_id: str) -> ToolInvocation:
        """Return the pinned invocation recipe for one plan step."""
        for step in self.plan.steps:
            if step.step_id == step_id:
                return ToolInvocation.from_dict(
                    _mapping(step.configuration.get(
                        _INVOCATION_CONFIGURATION_KEY
                    ))
                )
        raise ValueError(f"unknown compiled workflow step: {step_id}")


def compile_supplied_implementation_workflow(
    *,
    objective: ResearchObjective,
    protocol: ExperimentProtocol,
    artifact_store: ResearchArtifactStore,
) -> CompiledResearchWorkflow:
    """Compile one approved protocol into a fixed MCP capability DAG."""
    _validate_protocol_readiness(objective, protocol)
    pinned_strategy = _pin_ref(
        protocol.strategy.implementation_ref,
        artifact_store,
    )
    pinned_risks = tuple(
        _pin_ref(item.implementation_ref, artifact_store)
        for item in protocol.risk_managers
    )
    pinned_datasets = {
        item.requirement_id: (
            _pin_ref(item.dataset_manifest_ref, artifact_store),
            _pin_ref(item.data_quality_report_ref, artifact_store),
        )
        for item in protocol.datasets
    }
    pinned_objective = (
        _pin_optimization_objective(protocol, artifact_store)
        if protocol.optimization is not None
        else None
    )

    slots: list[ArtifactSlot] = []
    capabilities: list[CapabilityDefinition] = []
    steps: list[WorkflowStep] = []
    strategy_implementation_slot = "strategy_implementation"
    slots.append(_resolved_slot(strategy_implementation_slot, pinned_strategy))
    for index, reference in enumerate(pinned_risks):
        slots.append(_resolved_slot(f"risk_implementation_{index}", reference))
    for dataset in protocol.datasets:
        manifest, quality = pinned_datasets[dataset.requirement_id]
        slots.extend(
            (
                _resolved_slot(
                    f"dataset_manifest_{dataset.requirement_id}",
                    manifest,
                ),
                _resolved_slot(
                    f"data_quality_{dataset.requirement_id}",
                    quality,
                ),
            )
        )
    if pinned_objective is not None:
        slots.append(
            _resolved_slot(
                "optimization_objective_validation",
                pinned_objective,
            )
        )

    strategy_validation_slot = "strategy_implementation_validation"
    _append_step(
        capabilities,
        steps,
        slots,
        step_id="validate_strategy_implementation",
        capability_id="validate_strategy_implementation",
        tool_name=RESEARCH_VALIDATE_STRATEGY_IMPLEMENTATION_TOOL,
        input_bindings={"implementation": strategy_implementation_slot},
        output_bindings={
            "validation": strategy_validation_slot,
        },
        output_specs={
            "validation": (
                IMPLEMENTATION_VALIDATION_REPORT,
                ArtifactCardinality.EXACTLY_ONE,
                True,
            )
        },
        invocation=ToolInvocation(
            tool_name=RESEARCH_VALIDATE_STRATEGY_IMPLEMENTATION_TOOL,
            ref_arguments={
                "implementation_version_uri": strategy_implementation_slot
            },
            static_arguments={
                "fixture_parameters": dict(protocol.strategy.parameters)
            },
        ),
    )
    strategy_specification_slot = "strategy_specification"
    _append_step(
        capabilities,
        steps,
        slots,
        step_id="create_strategy_specification",
        capability_id="create_strategy_specification",
        tool_name=RESEARCH_CREATE_STRATEGY_SPECIFICATION_TOOL,
        depends_on=("validate_strategy_implementation",),
        input_bindings={"validation": strategy_validation_slot},
        output_bindings={"specification": strategy_specification_slot},
        output_specs={
            "specification": (
                STRATEGY_SPECIFICATION,
                ArtifactCardinality.EXACTLY_ONE,
                True,
            )
        },
        invocation=ToolInvocation(
            tool_name=RESEARCH_CREATE_STRATEGY_SPECIFICATION_TOOL,
            ref_arguments={
                "implementation_validation_ref": strategy_validation_slot
            },
            static_arguments={
                "parameters": dict(protocol.strategy.parameters),
                "sizing": dict(protocol.strategy.sizing),
                "portfolio_mode": protocol.strategy.portfolio_mode,
                "required_runtime_context": dict(
                    protocol.strategy.required_runtime_context
                ),
                "execution_assumptions": dict(
                    protocol.strategy.execution_assumptions
                ),
                "tunable_fields": list(protocol.strategy.tunable_fields),
                "provenance_refs": [
                    dict(item) for item in protocol.strategy.provenance_refs
                ],
                "prediction_bindings": [
                    dict(item) for item in protocol.strategy.prediction_bindings
                ],
            },
        ),
    )
    strategy_specification_validation_slot = (
        "strategy_specification_validation"
    )
    _append_step(
        capabilities,
        steps,
        slots,
        step_id="validate_strategy_specification",
        capability_id="validate_strategy_specification",
        tool_name=RESEARCH_VALIDATE_STRATEGY_SPECIFICATION_TOOL,
        depends_on=("create_strategy_specification",),
        input_bindings={"specification": strategy_specification_slot},
        output_bindings={
            "validation": strategy_specification_validation_slot
        },
        output_specs={
            "validation": (
                STRATEGY_SPECIFICATION_VALIDATION_REPORT,
                ArtifactCardinality.EXACTLY_ONE,
                True,
            )
        },
        invocation=ToolInvocation(
            tool_name=RESEARCH_VALIDATE_STRATEGY_SPECIFICATION_TOOL,
            ref_arguments={
                "strategy_specification_uri": strategy_specification_slot
            },
        ),
    )

    risk_validation_slots: list[str] = []
    risk_validation_steps: list[str] = []
    for index, risk in enumerate(protocol.risk_managers):
        step_id = f"validate_risk_implementation_{index}"
        output_slot = f"risk_implementation_validation_{index}"
        risk_validation_steps.append(step_id)
        risk_validation_slots.append(output_slot)
        _append_step(
            capabilities,
            steps,
            slots,
            step_id=step_id,
            capability_id=step_id,
            tool_name=RESEARCH_VALIDATE_RISK_MANAGER_IMPLEMENTATION_TOOL,
            input_bindings={
                "implementation": f"risk_implementation_{index}"
            },
            output_bindings={"validation": output_slot},
            output_specs={
                "validation": (
                    IMPLEMENTATION_VALIDATION_REPORT,
                    ArtifactCardinality.EXACTLY_ONE,
                    True,
                )
            },
            invocation=ToolInvocation(
                tool_name=RESEARCH_VALIDATE_RISK_MANAGER_IMPLEMENTATION_TOOL,
                ref_arguments={
                    "implementation_version_uri": (
                        f"risk_implementation_{index}"
                    )
                },
                static_arguments={
                    "fixture_parameters": dict(risk.parameters)
                },
            ),
        )
    risk_stack_slot = "risk_stack_specification"
    risk_input_bindings = {
        f"validation_{index}": slot
        for index, slot in enumerate(risk_validation_slots)
    }
    _append_step(
        capabilities,
        steps,
        slots,
        step_id="create_risk_stack_specification",
        capability_id="create_risk_stack_specification",
        tool_name=RESEARCH_CREATE_RISK_STACK_SPECIFICATION_TOOL,
        depends_on=tuple(risk_validation_steps),
        input_bindings=risk_input_bindings,
        output_bindings={"specification": risk_stack_slot},
        output_specs={
            "specification": (
                RISK_STACK_SPECIFICATION,
                ArtifactCardinality.EXACTLY_ONE,
                True,
            )
        },
        invocation=ToolInvocation(
            tool_name=RESEARCH_CREATE_RISK_STACK_SPECIFICATION_TOOL,
            mode=InvocationMode.RISK_STACK,
            static_arguments={
                "execution_assumptions": {
                    "live_trading_allowed": False,
                    "broker_mutation_allowed": False,
                    "raw_sql_allowed": False,
                },
            },
            risk_entries=tuple(
                {
                    "slot_id": risk_validation_slots[index],
                    "parameters": dict(risk.parameters),
                    "tunable_fields": list(risk.tunable_fields),
                }
                for index, risk in enumerate(protocol.risk_managers)
            ),
        ),
    )
    risk_stack_validation_slot = "risk_stack_specification_validation"
    _append_step(
        capabilities,
        steps,
        slots,
        step_id="validate_risk_stack_specification",
        capability_id="validate_risk_stack_specification",
        tool_name=RESEARCH_VALIDATE_RISK_STACK_SPECIFICATION_TOOL,
        depends_on=("create_risk_stack_specification",),
        input_bindings={"specification": risk_stack_slot},
        output_bindings={"validation": risk_stack_validation_slot},
        output_specs={
            "validation": (
                RISK_STACK_SPECIFICATION_VALIDATION_REPORT,
                ArtifactCardinality.EXACTLY_ONE,
                True,
            )
        },
        invocation=ToolInvocation(
            tool_name=RESEARCH_VALIDATE_RISK_STACK_SPECIFICATION_TOOL,
            ref_arguments={
                "risk_stack_specification_uri": risk_stack_slot
            },
        ),
    )

    experiment_dataset = _experiment_dataset(protocol)
    dataset_prefix = experiment_dataset.requirement_id
    base_backtest_specification_slot = "base_backtest_specification"
    base_create_dependencies = (
        "validate_strategy_specification",
        "validate_risk_stack_specification",
    )
    _append_step(
        capabilities,
        steps,
        slots,
        step_id="create_base_backtest_specification",
        capability_id="create_base_backtest_specification",
        tool_name=RESEARCH_CREATE_BACKTEST_SPECIFICATION_TOOL,
        depends_on=base_create_dependencies,
        input_bindings={
            "strategy_validation": strategy_specification_validation_slot,
            "risk_validation": risk_stack_validation_slot,
            "dataset_manifest": f"dataset_manifest_{dataset_prefix}",
            "data_quality": f"data_quality_{dataset_prefix}",
        },
        output_bindings={
            "specification": base_backtest_specification_slot
        },
        output_specs={
            "specification": (
                BACKTEST_SPECIFICATION,
                ArtifactCardinality.EXACTLY_ONE,
                True,
            )
        },
        invocation=ToolInvocation(
            tool_name=RESEARCH_CREATE_BACKTEST_SPECIFICATION_TOOL,
            ref_arguments={
                "strategy_specification_validation_ref": (
                    strategy_specification_validation_slot
                ),
                "risk_stack_specification_validation_ref": (
                    risk_stack_validation_slot
                ),
            },
            payload_arguments={
                "dataset_manifest": f"dataset_manifest_{dataset_prefix}",
                "data_quality_report": f"data_quality_{dataset_prefix}",
            },
            static_arguments=_base_backtest_arguments(protocol),
        ),
    )
    base_backtest_validation_slot = "base_backtest_specification_validation"
    _append_step(
        capabilities,
        steps,
        slots,
        step_id="validate_base_backtest_specification",
        capability_id="validate_base_backtest_specification",
        tool_name=RESEARCH_VALIDATE_BACKTEST_SPECIFICATION_TOOL,
        depends_on=("create_base_backtest_specification",),
        input_bindings={"specification": base_backtest_specification_slot},
        output_bindings={"validation": base_backtest_validation_slot},
        output_specs={
            "validation": (
                BACKTEST_SPECIFICATION_VALIDATION_REPORT,
                ArtifactCardinality.EXACTLY_ONE,
                True,
            )
        },
        invocation=ToolInvocation(
            tool_name=RESEARCH_VALIDATE_BACKTEST_SPECIFICATION_TOOL,
            ref_arguments={
                "backtest_specification_uri": base_backtest_specification_slot
            },
        ),
    )
    base_backtest_run_slot = "base_backtest_run"
    _append_step(
        capabilities,
        steps,
        slots,
        step_id="run_base_backtest",
        capability_id="run_base_backtest",
        tool_name=RESEARCH_RUN_BACKTEST_SPECIFICATION_TOOL,
        depends_on=("validate_base_backtest_specification",),
        input_bindings={"validation": base_backtest_validation_slot},
        output_bindings={"run": base_backtest_run_slot},
        output_specs={
            "run": (
                BACKTEST_RUN,
                ArtifactCardinality.EXACTLY_ONE,
                True,
            )
        },
        invocation=ToolInvocation(
            tool_name=RESEARCH_RUN_BACKTEST_SPECIFICATION_TOOL,
            ref_arguments={
                "backtest_specification_validation_ref": (
                    base_backtest_validation_slot
                )
            },
        ),
    )

    if protocol.optimization is not None:
        _append_optimization_steps(
            protocol=protocol,
            capabilities=capabilities,
            steps=steps,
            slots=slots,
            base_backtest_validation_slot=base_backtest_validation_slot,
        )

    plan_identity = {
        "objective_id": objective.objective_id,
        "protocol_id": protocol.protocol_id,
        "template_id": WORKFLOW_TEMPLATE_ID,
        "template_version": WORKFLOW_TEMPLATE_VERSION,
        "steps": [item.to_dict() for item in steps],
        "slots": [item.to_dict() for item in slots],
    }
    plan_id = stable_research_id("workflow_plan", plan_identity)
    plan = WorkflowPlan(
        plan_id=plan_id,
        objective_ref=artifact_report_ref(
            RESEARCH_OBJECTIVE,
            objective.objective_id,
        ),
        protocol_ref=artifact_report_ref(
            EXPERIMENT_PROTOCOL,
            protocol.protocol_id,
        ),
        template_id=WORKFLOW_TEMPLATE_ID,
        template_version=WORKFLOW_TEMPLATE_VERSION,
        capabilities=tuple(capabilities),
        artifact_slots=tuple(slots),
        prerequisites=(),
        approvals=protocol.approvals,
        steps=tuple(steps),
        requested_by=protocol.requested_by,
        actor="research_coordinator",
        status=WorkflowPlanStatus.READY,
    )
    return CompiledResearchWorkflow(
        objective=objective,
        protocol=protocol,
        plan=plan,
    )


def _append_optimization_steps(
    *,
    protocol: ExperimentProtocol,
    capabilities: list[CapabilityDefinition],
    steps: list[WorkflowStep],
    slots: list[ArtifactSlot],
    base_backtest_validation_slot: str,
) -> None:
    optimization = protocol.optimization
    if optimization is None:
        return
    holdout = _dataset_by_role(protocol, DatasetRole.HOLDOUT)
    holdout_manifest_slot = f"dataset_manifest_{holdout.requirement_id}"
    holdout_quality_slot = f"data_quality_{holdout.requirement_id}"
    plan_slot = "parameter_optimization_plan"
    _append_step(
        capabilities,
        steps,
        slots,
        step_id="create_parameter_optimization_plan",
        capability_id="create_parameter_optimization_plan",
        tool_name=RESEARCH_CREATE_PARAMETER_OPTIMIZATION_PLAN_TOOL,
        depends_on=("validate_base_backtest_specification",),
        input_bindings={
            "base_validation": base_backtest_validation_slot,
            "holdout_manifest": holdout_manifest_slot,
            "holdout_quality": holdout_quality_slot,
            "objective_validation": "optimization_objective_validation",
        },
        output_bindings={"plan": plan_slot},
        output_specs={
            "plan": (
                PARAMETER_OPTIMIZATION_PLAN,
                ArtifactCardinality.EXACTLY_ONE,
                True,
            )
        },
        invocation=ToolInvocation(
            tool_name=RESEARCH_CREATE_PARAMETER_OPTIMIZATION_PLAN_TOOL,
            ref_arguments={
                "base_backtest_specification_validation_ref": (
                    base_backtest_validation_slot
                ),
                "objective_validation_ref": (
                    "optimization_objective_validation"
                ),
            },
            payload_arguments={
                "holdout_dataset_manifest": holdout_manifest_slot,
                "holdout_data_quality_report": holdout_quality_slot,
            },
            static_arguments={
                "search_space": [
                    _search_dimension(item)
                    for item in optimization.dimensions
                ],
                "direction": optimization.direction.value,
                "constraints": [
                    _optimization_constraint(item)
                    for item in optimization.constraints
                ],
                "seed": optimization.seed,
                "max_trials": optimization.trial_budget,
                "resource_limits": {
                    "max_trial_attempts": 1,
                    "max_concurrent_trials": 1,
                },
            },
        ),
    )
    run_slot = "parameter_optimization_run"
    _append_step(
        capabilities,
        steps,
        slots,
        step_id="run_parameter_optimization",
        capability_id="run_parameter_optimization",
        tool_name=RESEARCH_RUN_PARAMETER_OPTIMIZATION_TOOL,
        depends_on=("run_base_backtest", "create_parameter_optimization_plan"),
        input_bindings={"plan": plan_slot},
        output_bindings={"run": run_slot},
        output_specs={
            "run": (
                PARAMETER_OPTIMIZATION_RUN,
                ArtifactCardinality.EXACTLY_ONE,
                True,
            )
        },
        invocation=ToolInvocation(
            tool_name=RESEARCH_RUN_PARAMETER_OPTIMIZATION_TOOL,
            ref_arguments={"optimization_plan_ref": plan_slot},
            static_arguments={
                "optimizer_profile": protocol.optimizer_profile
            },
        ),
    )
    holdout_specification_slot = "holdout_backtest_specification"
    _append_step(
        capabilities,
        steps,
        slots,
        step_id="create_holdout_backtest_specification",
        capability_id="create_holdout_backtest_specification",
        tool_name=RESEARCH_CREATE_BACKTEST_SPECIFICATION_TOOL,
        depends_on=("run_parameter_optimization",),
        input_bindings={
            "optimization_run": run_slot,
            "holdout_manifest": holdout_manifest_slot,
            "holdout_quality": holdout_quality_slot,
        },
        output_bindings={"specification": holdout_specification_slot},
        output_specs={
            "specification": (
                BACKTEST_SPECIFICATION,
                ArtifactCardinality.EXACTLY_ONE,
                True,
            )
        },
        invocation=ToolInvocation(
            tool_name=RESEARCH_CREATE_BACKTEST_SPECIFICATION_TOOL,
            mode=InvocationMode.SELECTED_HOLDOUT_BACKTEST,
            payload_arguments={
                "optimization_run": run_slot,
                "dataset_manifest": holdout_manifest_slot,
                "data_quality_report": holdout_quality_slot,
            },
            static_arguments=_base_backtest_arguments(protocol),
        ),
    )
    holdout_validation_slot = "holdout_backtest_specification_validation"
    _append_step(
        capabilities,
        steps,
        slots,
        step_id="validate_holdout_backtest_specification",
        capability_id="validate_holdout_backtest_specification",
        tool_name=RESEARCH_VALIDATE_BACKTEST_SPECIFICATION_TOOL,
        depends_on=("create_holdout_backtest_specification",),
        input_bindings={"specification": holdout_specification_slot},
        output_bindings={"validation": holdout_validation_slot},
        output_specs={
            "validation": (
                BACKTEST_SPECIFICATION_VALIDATION_REPORT,
                ArtifactCardinality.EXACTLY_ONE,
                True,
            )
        },
        invocation=ToolInvocation(
            tool_name=RESEARCH_VALIDATE_BACKTEST_SPECIFICATION_TOOL,
            ref_arguments={
                "backtest_specification_uri": holdout_specification_slot
            },
        ),
    )
    holdout_run_slot = "holdout_backtest_run"
    _append_step(
        capabilities,
        steps,
        slots,
        step_id="run_holdout_backtest",
        capability_id="run_holdout_backtest",
        tool_name=RESEARCH_RUN_BACKTEST_SPECIFICATION_TOOL,
        depends_on=("validate_holdout_backtest_specification",),
        input_bindings={"validation": holdout_validation_slot},
        output_bindings={"run": holdout_run_slot},
        output_specs={
            "run": (
                BACKTEST_RUN,
                ArtifactCardinality.EXACTLY_ONE,
                True,
            )
        },
        invocation=ToolInvocation(
            tool_name=RESEARCH_RUN_BACKTEST_SPECIFICATION_TOOL,
            ref_arguments={
                "backtest_specification_validation_ref": (
                    holdout_validation_slot
                )
            },
        ),
    )
    evaluation_slot = "parameter_optimization_evaluation"
    _append_step(
        capabilities,
        steps,
        slots,
        step_id="evaluate_parameter_optimization",
        capability_id="evaluate_parameter_optimization",
        tool_name=EVALUATION_GENERATE_PARAMETER_OPTIMIZATION_REPORT_TOOL,
        depends_on=("run_holdout_backtest",),
        input_bindings={
            "optimization_run": run_slot,
            "holdout_run": holdout_run_slot,
        },
        output_bindings={"evaluation": evaluation_slot},
        output_specs={
            "evaluation": (
                PARAMETER_OPTIMIZATION_EVALUATION_REPORT,
                ArtifactCardinality.EXACTLY_ONE,
                True,
            )
        },
        invocation=ToolInvocation(
            tool_name=EVALUATION_GENERATE_PARAMETER_OPTIMIZATION_REPORT_TOOL,
            ref_arguments={
                "optimization_run_ref": run_slot,
                "holdout_backtest_run_ref": holdout_run_slot,
            },
        ),
    )
    if not protocol.robustness_requirements:
        return
    audit_plan_slot = "parameter_optimization_audit_plan"
    _append_step(
        capabilities,
        steps,
        slots,
        step_id="create_parameter_optimization_audit_plan",
        capability_id="create_parameter_optimization_audit_plan",
        tool_name=ADVERSARIAL_CREATE_PARAMETER_OPTIMIZATION_AUDIT_PLAN_TOOL,
        depends_on=("run_parameter_optimization",),
        input_bindings={"optimization_run": run_slot},
        output_bindings={"audit_plan": audit_plan_slot},
        output_specs={
            "audit_plan": (
                PARAMETER_OPTIMIZATION_AUDIT_PLAN,
                ArtifactCardinality.EXACTLY_ONE,
                True,
            )
        },
        invocation=ToolInvocation(
            tool_name=ADVERSARIAL_CREATE_PARAMETER_OPTIMIZATION_AUDIT_PLAN_TOOL,
            ref_arguments={"optimization_run_ref": run_slot},
            static_arguments={
                "attacks": [
                    {
                        "attack_type": item.attack_type,
                        "configuration": dict(item.configuration),
                    }
                    for item in protocol.robustness_requirements
                ]
            },
        ),
    )
    variant_runs_slot = "parameter_optimization_variant_runs"
    _append_step(
        capabilities,
        steps,
        slots,
        step_id="run_parameter_optimization_variants",
        capability_id="run_parameter_optimization_variants",
        tool_name=RESEARCH_RUN_PARAMETER_OPTIMIZATION_VARIANTS_TOOL,
        depends_on=("create_parameter_optimization_audit_plan",),
        input_bindings={"audit_plan": audit_plan_slot},
        output_bindings={"variant_runs": variant_runs_slot},
        output_specs={
            "variant_runs": (
                PARAMETER_OPTIMIZATION_RUN,
                ArtifactCardinality.ONE_OR_MORE,
                False,
            )
        },
        invocation=ToolInvocation(
            tool_name=RESEARCH_RUN_PARAMETER_OPTIMIZATION_VARIANTS_TOOL,
            ref_arguments={"audit_plan_ref": audit_plan_slot},
        ),
    )
    robustness_slot = "parameter_optimization_robustness"
    _append_step(
        capabilities,
        steps,
        slots,
        step_id="generate_parameter_optimization_audit",
        capability_id="generate_parameter_optimization_audit",
        tool_name=ADVERSARIAL_GENERATE_PARAMETER_OPTIMIZATION_AUDIT_TOOL,
        depends_on=(
            "run_parameter_optimization_variants",
            "evaluate_parameter_optimization",
        ),
        input_bindings={
            "audit_plan": audit_plan_slot,
            "variant_runs": variant_runs_slot,
        },
        output_bindings={"robustness": robustness_slot},
        output_specs={
            "robustness": (
                PARAMETER_OPTIMIZATION_ROBUSTNESS_REPORT,
                ArtifactCardinality.EXACTLY_ONE,
                True,
            )
        },
        invocation=ToolInvocation(
            tool_name=ADVERSARIAL_GENERATE_PARAMETER_OPTIMIZATION_AUDIT_TOOL,
            ref_arguments={"audit_plan_ref": audit_plan_slot},
            ref_list_arguments={
                "variant_optimization_run_refs": variant_runs_slot
            },
            static_arguments={"stress_backtest_run_refs": []},
        ),
    )


def _append_step(
    capabilities: list[CapabilityDefinition],
    steps: list[WorkflowStep],
    slots: list[ArtifactSlot],
    *,
    step_id: str,
    capability_id: str,
    tool_name: str,
    input_bindings: Mapping[str, str],
    output_bindings: Mapping[str, str],
    output_specs: Mapping[
        str,
        tuple[str, ArtifactCardinality, bool],
    ],
    invocation: ToolInvocation,
    depends_on: tuple[str, ...] = (),
) -> None:
    input_declarations = tuple(
        _empty_slot(declaration_id, _slot_by_id(slots, plan_slot_id))
        for declaration_id, plan_slot_id in input_bindings.items()
    )
    output_declarations: list[ArtifactSlot] = []
    for declaration_id, plan_slot_id in output_bindings.items():
        artifact_type, cardinality, required = output_specs[declaration_id]
        plan_slot = _artifact_slot(
            plan_slot_id,
            artifact_type,
            cardinality=cardinality,
            required=required,
        )
        slots.append(plan_slot)
        output_declarations.append(
            _empty_slot(declaration_id, plan_slot)
        )
    capabilities.append(
        CapabilityDefinition(
            capability_id=capability_id,
            version="1",
            description=f"Deterministically invoke {tool_name}.",
            domain_owner=(
                output_declarations[0].domain_owner
                if output_declarations
                else DOMAIN_OWNER_BY_ARTIFACT_TYPE[
                    _slot_by_id(
                        slots,
                        next(iter(input_bindings.values())),
                    ).artifact_type
                ]
            ),
            producer_tool=tool_name,
            side_effect=CapabilitySideEffect.LOCAL_MUTATING,
            input_slots=input_declarations,
            output_slots=tuple(output_declarations),
            configuration_keys=(_INVOCATION_CONFIGURATION_KEY,),
        )
    )
    steps.append(
        WorkflowStep(
            step_id=step_id,
            capability_id=capability_id,
            depends_on=depends_on,
            input_bindings=dict(input_bindings),
            output_bindings=dict(output_bindings),
            configuration={
                _INVOCATION_CONFIGURATION_KEY: invocation.to_dict()
            },
        )
    )


def _artifact_slot(
    slot_id: str,
    artifact_type: str,
    *,
    cardinality: ArtifactCardinality = ArtifactCardinality.EXACTLY_ONE,
    required: bool = True,
    status: ArtifactSlotStatus = ArtifactSlotStatus.EMPTY,
    artifact_refs: tuple[ArtifactReportRef, ...] = (),
) -> ArtifactSlot:
    return ArtifactSlot(
        slot_id=slot_id,
        artifact_type=artifact_type,
        domain_owner=DOMAIN_OWNER_BY_ARTIFACT_TYPE[artifact_type],
        cardinality=cardinality,
        required=required,
        status=status,
        artifact_refs=artifact_refs,
    )


def _resolved_slot(
    slot_id: str,
    reference: ArtifactReportRef,
) -> ArtifactSlot:
    return _artifact_slot(
        slot_id,
        reference.artifact_type,
        status=ArtifactSlotStatus.RESOLVED,
        artifact_refs=(reference,),
    )


def _empty_slot(
    declaration_id: str,
    plan_slot: ArtifactSlot,
) -> ArtifactSlot:
    return _artifact_slot(
        declaration_id,
        plan_slot.artifact_type,
        cardinality=plan_slot.cardinality,
        required=plan_slot.required,
    )


def _slot_by_id(
    slots: Sequence[ArtifactSlot],
    slot_id: str,
) -> ArtifactSlot:
    for slot in slots:
        if slot.slot_id == slot_id:
            return slot
    raise ValueError(f"unknown workflow artifact slot: {slot_id}")


def _pin_ref(
    reference: ArtifactReportRef,
    artifact_store: ResearchArtifactStore,
) -> ArtifactReportRef:
    try:
        record = artifact_store.load_artifact_record(
            reference.artifact_type,
            reference.artifact_id,
        )
    except ResearchArtifactStoreError as exc:
        raise ValueError(
            f"workflow input artifact does not resolve: {reference.uri}"
        ) from exc
    if record.domain_owner != reference.domain_owner:
        raise ValueError(
            f"workflow input domain drift for {reference.uri}"
        )
    payload_type = str(record.payload.get("artifact_type") or "")
    if payload_type != reference.artifact_type:
        raise ValueError(
            f"workflow input payload type mismatch for {reference.uri}"
        )
    metadata = {
        **dict(reference.metadata),
        "payload_sha256": json_payload_hash(record.payload),
        "producer_tool": record.producer_tool,
        "status": record.status,
    }
    return ArtifactReportRef(
        artifact_id=reference.artifact_id,
        artifact_type=reference.artifact_type,
        domain_owner=reference.domain_owner,
        uri=reference.uri,
        metadata=metadata,
    )


def _pin_optimization_objective(
    protocol: ExperimentProtocol,
    artifact_store: ResearchArtifactStore,
) -> ArtifactReportRef:
    optimization = protocol.optimization
    if optimization is None:
        raise ValueError("optimization protocol is required")
    artifact_type, artifact_id = _parse_ref(
        optimization.objective_validation_ref
    )
    if artifact_type != IMPLEMENTATION_VALIDATION_REPORT:
        raise ValueError(
            "optimization objective ref must be an implementation validation"
        )
    reference = artifact_report_ref(artifact_type, artifact_id)
    pinned = _pin_ref(reference, artifact_store)
    payload = artifact_store.load_artifact(artifact_type, artifact_id)
    if payload.get("status") != "passed" or payload.get("valid") is not True:
        raise ValueError("optimization objective validation must be passed")
    if payload.get("blockers"):
        raise ValueError(
            "optimization objective validation cannot contain blockers"
        )
    return pinned


def _validate_protocol_readiness(
    objective: ResearchObjective,
    protocol: ExperimentProtocol,
) -> None:
    if objective.status is not ResearchObjectiveStatus.APPROVED:
        raise ValueError("research objective must be approved")
    if protocol.status is not ExperimentProtocolStatus.APPROVED:
        raise ValueError("experiment protocol must be approved")
    if protocol.objective_id != objective.objective_id:
        raise ValueError("protocol objective_id does not match objective")
    if any(
        item.status is not ApprovalStatus.APPROVED
        for item in protocol.approvals
    ):
        raise ValueError("experiment protocol contains unresolved approvals")
    if protocol.robustness_requirements and protocol.optimization is None:
        raise ValueError(
            "the implemented robustness workflow requires optimization"
        )


def _experiment_dataset(protocol: ExperimentProtocol) -> Any:
    role = (
        DatasetRole.SELECTION
        if protocol.optimization is not None
        else DatasetRole.BASELINE
    )
    candidates = [item for item in protocol.datasets if item.role is role]
    if protocol.optimization is None and not candidates:
        candidates = [
            item
            for item in protocol.datasets
            if item.role is DatasetRole.SELECTION
        ]
    if len(candidates) != 1:
        raise ValueError(
            f"workflow requires exactly one {role.value} dataset"
        )
    return candidates[0]


def _dataset_by_role(
    protocol: ExperimentProtocol,
    role: DatasetRole,
) -> Any:
    candidates = [item for item in protocol.datasets if item.role is role]
    if len(candidates) != 1:
        raise ValueError(
            f"workflow requires exactly one {role.value} dataset"
        )
    return candidates[0]


def _base_backtest_arguments(
    protocol: ExperimentProtocol,
) -> dict[str, Any]:
    return {
        "assumptions": _backtest_assumptions(protocol),
        "initial_cash": protocol.initial_portfolio.cash,
        "initial_positions": [
            {
                "symbol": item.symbol,
                "qty": item.quantity,
                "avg_price": item.avg_price,
            }
            for item in protocol.initial_portfolio.positions
        ],
        "deterministic_seed": protocol.deterministic_seed,
        "max_runs": protocol.max_runs,
        "log_cycle_details": protocol.log_cycle_details,
        "runtime_limits": dict(protocol.runtime_limits),
    }


def _backtest_assumptions(
    protocol: ExperimentProtocol,
) -> dict[str, Any]:
    assumptions: dict[str, Any] = {}
    supported = {
        "fees.fixed_per_order",
        "fees.bps",
        "fees.minimum_fee",
        "slippage.bps",
        "latency_ms",
    }
    for cost in protocol.costs:
        if cost.name not in supported:
            raise ValueError(
                f"unsupported executable cost assumption: {cost.name}"
            )
        if "." in cost.name:
            section, field = cost.name.split(".", 1)
            assumptions.setdefault(section, {})[field] = cost.value
        else:
            assumptions[cost.name] = cost.value
    return assumptions


def _search_dimension(value: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "path": value.target_path,
        "type": value.value_type.value,
    }
    if value.choices:
        payload["choices"] = list(value.choices)
    else:
        payload["low"] = value.lower
        payload["high"] = value.upper
        if value.step is not None:
            payload["step"] = value.step
    return payload


def _optimization_constraint(value: Any) -> dict[str, Any]:
    operator = {
        "<": "lt",
        "<=": "lte",
        "==": "eq",
        ">=": "gte",
        ">": "gt",
    }[value.operator]
    return {
        "metric": value.metric,
        "operator": operator,
        "value": value.threshold,
    }


def _parse_ref(uri: str) -> tuple[str, str]:
    parts = str(uri).split("/")
    if len(parts) < 2:
        raise ValueError("invalid canonical research URI")
    return parts[-2], parts[-1]


def _required_text(value: object, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{label} is required")
    return text


def _mapping(value: object) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return {}


def _text_mapping(value: object) -> dict[str, str]:
    return {
        str(key): str(item)
        for key, item in _mapping(value).items()
    }


def _sequence(value: object) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return value
    return ()
