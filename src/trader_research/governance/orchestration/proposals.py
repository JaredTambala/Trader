"""Define immutable experiment-design requests and protocol proposals.

The contracts in this module keep protocol authoring separate from approval and
execution. A design request contains every executable choice explicitly; a
proposal pins those choices and their canonical inputs; and approval application
can change only approval lifecycle fields, never the proposed design.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

from trader_research.foundation import (
    json_payload_hash,
    jsonable,
    parse_research_artifact_uri,
    stable_research_id,
)

from ..artifacts import (
    EXPERIMENT_PROTOCOL,
    EXPERIMENT_PROTOCOL_PROPOSAL,
    IMPLEMENTATION_VALIDATION_REPORT,
)
from ..handoffs import ArtifactReportRef, artifact_report_ref
from .enums import ApprovalStatus, ExperimentProtocolStatus
from .protocols import (
    Approval,
    CostAssumption,
    ExperimentProtocol,
    InitialPortfolio,
    MaterialAssumption,
    OptimizationProtocol,
    ProtocolDataset,
    ProtocolRiskManager,
    ProtocolStrategy,
    ResearchObjective,
    RobustnessRequirement,
)


@dataclass(frozen=True)
class ExperimentDesignRequest:
    """Complete structured input for one experiment-protocol proposal.

    The request deliberately has no protocol ID, approvals, lifecycle status, or
    proposer identity. Those values are derived at the trusted proposal boundary.
    Every field that affects execution is explicit, including deterministic
    limits and the operator who must decide material assumptions.

    Attributes:
        strategy: Pinned strategy implementation and executable configuration.
        risk_managers: Ordered pinned risk implementations and configuration.
        datasets: Role-labelled canonical Data evidence and bounded requirements.
        costs: Explicit cost model, including explicit zero-cost assumptions.
        initial_portfolio: Exact cash, currency, and starting positions.
        robustness_requirements: Pre-result claims and attacks to require.
        evaluation_questions: Questions the independent review must answer.
        falsification_criteria: Conditions that would reject the research claim.
        material_assumptions: Named choices requiring an operator decision.
        requested_approver: Person or role asked to decide every assumption.
        optimization: Optional bounded provider-neutral optimization design.
        deterministic_seed: Non-negative seed used by deterministic execution.
        max_runs: Positive hard bound on execution runs.
        log_cycle_details: Whether bounded cycle-level details may be recorded.
        runtime_limits: Explicit JSON-safe execution resource limits.
        optimizer_profile: Registered optimizer profile requested by the design.
    """

    strategy: ProtocolStrategy
    risk_managers: tuple[ProtocolRiskManager, ...]
    datasets: tuple[ProtocolDataset, ...]
    costs: tuple[CostAssumption, ...]
    initial_portfolio: InitialPortfolio
    robustness_requirements: tuple[RobustnessRequirement, ...]
    evaluation_questions: tuple[str, ...]
    falsification_criteria: tuple[str, ...]
    material_assumptions: tuple[MaterialAssumption, ...]
    requested_approver: str
    deterministic_seed: int
    max_runs: int
    log_cycle_details: bool
    runtime_limits: Mapping[str, Any]
    optimizer_profile: str
    optimization: OptimizationProtocol | None = None

    def __post_init__(self) -> None:
        """Validate the design by constructing its proposed protocol shape."""
        if not self.requested_approver.strip():
            raise ValueError("experiment design requested_approver is required")
        if not self.costs:
            raise ValueError("experiment design costs must be explicit")
        if not self.material_assumptions:
            raise ValueError(
                "experiment design material assumptions must be explicit"
            )
        if self.max_runs <= 0:
            raise ValueError("experiment design max_runs must be positive")
        if not isinstance(self.log_cycle_details, bool):
            raise ValueError("experiment design log_cycle_details must be a boolean")
        if not self.optimizer_profile.strip():
            raise ValueError("experiment design optimizer_profile is required")
        _validate_design_shape(self)

    def to_dict(self) -> dict[str, Any]:
        """Serialize every explicit protocol-design input into plain data."""
        return {
            "strategy": self.strategy.to_dict(),
            "risk_managers": [item.to_dict() for item in self.risk_managers],
            "datasets": [item.to_dict() for item in self.datasets],
            "costs": [item.to_dict() for item in self.costs],
            "initial_portfolio": self.initial_portfolio.to_dict(),
            "optimization": (
                self.optimization.to_dict() if self.optimization is not None else None
            ),
            "deterministic_seed": self.deterministic_seed,
            "max_runs": self.max_runs,
            "log_cycle_details": self.log_cycle_details,
            "runtime_limits": jsonable(self.runtime_limits),
            "optimizer_profile": self.optimizer_profile,
            "robustness_requirements": [
                item.to_dict() for item in self.robustness_requirements
            ],
            "evaluation_questions": list(self.evaluation_questions),
            "falsification_criteria": list(self.falsification_criteria),
            "material_assumptions": [
                item.to_dict() for item in self.material_assumptions
            ],
            "requested_approver": self.requested_approver,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ExperimentDesignRequest":
        """Parse a closed JSON-compatible experiment-design request.

        Args:
            payload: Mapping containing all execution-affecting design fields.

        Returns:
            Normalized immutable design request.

        Raises:
            ValueError: If fields are missing, unknown, unbounded, or internally
                inconsistent with the existing experiment protocol contract.
        """
        allowed = {
            "strategy",
            "risk_managers",
            "datasets",
            "costs",
            "initial_portfolio",
            "optimization",
            "deterministic_seed",
            "max_runs",
            "log_cycle_details",
            "runtime_limits",
            "optimizer_profile",
            "robustness_requirements",
            "evaluation_questions",
            "falsification_criteria",
            "material_assumptions",
            "requested_approver",
        }
        _reject_unknown_fields(payload, allowed, "experiment design request")
        missing = sorted(allowed.difference(payload))
        if missing:
            raise ValueError(
                "experiment design request is missing fields: " + ", ".join(missing)
            )
        optimization_payload = payload.get("optimization")
        if optimization_payload is not None and not isinstance(
            optimization_payload, Mapping
        ):
            raise ValueError("experiment design optimization must be a mapping")
        max_runs = payload.get("max_runs")
        if isinstance(max_runs, bool) or not isinstance(max_runs, int):
            raise ValueError("experiment design max_runs must be an integer")
        seed = payload.get("deterministic_seed")
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise ValueError(
                "experiment design deterministic_seed must be an integer"
            )
        log_cycle_details = payload.get("log_cycle_details")
        if not isinstance(log_cycle_details, bool):
            raise ValueError("experiment design log_cycle_details must be a boolean")
        return cls(
            strategy=ProtocolStrategy.from_dict(
                _mapping(payload.get("strategy"), "strategy")
            ),
            risk_managers=tuple(
                ProtocolRiskManager.from_dict(item)
                for item in _mapping_sequence(
                    payload.get("risk_managers"), "risk_managers"
                )
            ),
            datasets=tuple(
                ProtocolDataset.from_dict(item)
                for item in _mapping_sequence(payload.get("datasets"), "datasets")
            ),
            costs=tuple(
                CostAssumption.from_dict(item)
                for item in _mapping_sequence(payload.get("costs"), "costs")
            ),
            initial_portfolio=InitialPortfolio.from_dict(
                _mapping(payload.get("initial_portfolio"), "initial_portfolio")
            ),
            optimization=(
                OptimizationProtocol.from_dict(optimization_payload)
                if isinstance(optimization_payload, Mapping)
                else None
            ),
            deterministic_seed=seed,
            max_runs=max_runs,
            log_cycle_details=log_cycle_details,
            runtime_limits=_mapping(payload.get("runtime_limits"), "runtime_limits"),
            optimizer_profile=str(payload.get("optimizer_profile") or ""),
            robustness_requirements=tuple(
                RobustnessRequirement.from_dict(item)
                for item in _mapping_sequence(
                    payload.get("robustness_requirements"),
                    "robustness_requirements",
                )
            ),
            evaluation_questions=_text_sequence(
                payload.get("evaluation_questions"), "evaluation_questions"
            ),
            falsification_criteria=_text_sequence(
                payload.get("falsification_criteria"), "falsification_criteria"
            ),
            material_assumptions=tuple(
                MaterialAssumption.from_dict(item)
                for item in _mapping_sequence(
                    payload.get("material_assumptions"), "material_assumptions"
                )
            ),
            requested_approver=str(payload.get("requested_approver") or ""),
        )


@dataclass(frozen=True)
class ExperimentProtocolProposal:
    """Immutable canonical evidence for one proposed experiment design.

    Attributes:
        proposal_id: Content-derived proposal artifact identity.
        task_id: Exact specialist task that requested this proposal.
        objective_id: Approved research objective receiving the proposal.
        objective_digest: Digest of the exact approved objective payload.
        design_digest: Digest of protocol design excluding decision lifecycle.
        input_refs: Canonical digest-pinned implementation and Data inputs.
        protocol: Proposed protocol containing requested approvals only.
        requested_by: Composition or workflow that requested the proposal.
        proposed_by: Registered Experiment Design actor.
        status: Fixed proposal lifecycle value.
    """

    proposal_id: str
    task_id: str
    objective_id: str
    objective_digest: str
    design_digest: str
    input_refs: tuple[ArtifactReportRef, ...]
    protocol: ExperimentProtocol
    requested_by: str
    proposed_by: str
    status: str = "proposed"

    artifact_type = EXPERIMENT_PROTOCOL_PROPOSAL

    def __post_init__(self) -> None:
        """Reject proposal identity, lineage, input, or lifecycle drift."""
        for value, label in (
            (self.proposal_id, "proposal_id"),
            (self.task_id, "proposal task_id"),
            (self.objective_id, "proposal objective_id"),
            (self.objective_digest, "proposal objective_digest"),
            (self.design_digest, "proposal design_digest"),
            (self.requested_by, "proposal requested_by"),
            (self.proposed_by, "proposal proposed_by"),
        ):
            if not value.strip():
                raise ValueError(f"{label} is required")
        if self.status != "proposed":
            raise ValueError("experiment protocol proposal status must be proposed")
        if self.protocol.status is not ExperimentProtocolStatus.PROPOSED:
            raise ValueError("proposal protocol must have proposed status")
        if self.protocol.objective_id != self.objective_id:
            raise ValueError("proposal protocol objective identity drift")
        if self.protocol.requested_by != self.requested_by:
            raise ValueError("proposal protocol requester drift")
        if self.protocol.proposed_by != self.proposed_by:
            raise ValueError("proposal protocol proposer drift")
        if experiment_protocol_design_digest(self.protocol) != self.design_digest:
            raise ValueError("proposal protocol design digest drift")
        if not self.input_refs:
            raise ValueError("proposal canonical input refs are required")
        if len(self.input_refs) != len({item.uri for item in self.input_refs}):
            raise ValueError("proposal canonical input refs must be unique")
        if any(
            not str(item.metadata.get("payload_sha256") or "")
            for item in self.input_refs
        ):
            raise ValueError("proposal input refs must pin canonical payload hashes")
        requested = {item.assumption_id: item for item in self.protocol.approvals}
        assumptions = {
            item.assumption_id for item in self.protocol.material_assumptions
        }
        if set(requested) != assumptions:
            raise ValueError("proposal approvals must cover every material assumption")
        if any(item.status is not ApprovalStatus.REQUESTED for item in requested.values()):
            raise ValueError("proposal approvals must remain requested")

    def to_dict(self) -> dict[str, Any]:
        """Serialize canonical proposal evidence without artifact payload expansion."""
        return {
            "artifact_type": self.artifact_type,
            "proposal_id": self.proposal_id,
            "task_id": self.task_id,
            "objective_id": self.objective_id,
            "objective_digest": self.objective_digest,
            "design_digest": self.design_digest,
            "input_refs": [item.to_dict() for item in self.input_refs],
            "protocol": self.protocol.to_dict(),
            "requested_by": self.requested_by,
            "proposed_by": self.proposed_by,
            "status": self.status,
        }

    @classmethod
    def from_dict(
        cls, payload: Mapping[str, Any]
    ) -> "ExperimentProtocolProposal":
        """Parse and validate a complete canonical protocol proposal."""
        allowed = {
            "artifact_type",
            "proposal_id",
            "task_id",
            "objective_id",
            "objective_digest",
            "design_digest",
            "input_refs",
            "protocol",
            "requested_by",
            "proposed_by",
            "status",
        }
        _reject_unknown_fields(payload, allowed, "experiment protocol proposal")
        artifact_type = payload.get("artifact_type")
        if artifact_type != EXPERIMENT_PROTOCOL_PROPOSAL:
            raise ValueError(
                "experiment protocol proposal artifact_type must be "
                f"{EXPERIMENT_PROTOCOL_PROPOSAL}"
            )
        return cls(
            proposal_id=str(payload.get("proposal_id") or ""),
            task_id=str(payload.get("task_id") or ""),
            objective_id=str(payload.get("objective_id") or ""),
            objective_digest=str(payload.get("objective_digest") or ""),
            design_digest=str(payload.get("design_digest") or ""),
            input_refs=tuple(
                ArtifactReportRef.from_dict(item)
                for item in _mapping_sequence(payload.get("input_refs"), "input_refs")
            ),
            protocol=ExperimentProtocol.from_dict(
                _mapping(payload.get("protocol"), "protocol")
            ),
            requested_by=str(payload.get("requested_by") or ""),
            proposed_by=str(payload.get("proposed_by") or ""),
            status=str(payload.get("status") or ""),
        )


def build_experiment_protocol_proposal(
    *,
    objective: ResearchObjective,
    design: ExperimentDesignRequest,
    task_id: str,
    requested_by: str,
    proposed_by: str,
    input_refs: Sequence[ArtifactReportRef],
) -> ExperimentProtocolProposal:
    """Build a content-derived proposal from normalized, already-pinned inputs.

    Args:
        objective: Approved objective whose exact digest is retained.
        design: Complete deterministic protocol design.
        task_id: Specialist task requesting proposal persistence.
        requested_by: Composition or workflow request identity.
        proposed_by: Registered Experiment Design actor.
        input_refs: Canonical input refs with payload hashes resolved by a service.

    Returns:
        Immutable proposal with requested approvals for every assumption.

    Raises:
        ValueError: If identity is blank or input refs do not match the design.
    """
    for value, label in (
        (task_id, "proposal task_id"),
        (requested_by, "proposal requested_by"),
        (proposed_by, "proposal proposed_by"),
    ):
        if not value.strip():
            raise ValueError(f"{label} is required")
    expected_uris = {item.uri for item in experiment_design_input_refs(design)}
    normalized_inputs = tuple(input_refs)
    if {item.uri for item in normalized_inputs} != expected_uris:
        raise ValueError("proposal canonical inputs do not match the design")
    protocol_id = stable_research_id(
        "experiment_protocol",
        {
            "objective_id": objective.objective_id,
            "design": design.to_dict(),
            "requested_by": requested_by,
            "proposed_by": proposed_by,
        },
    )
    approvals = tuple(
        Approval(
            approval_id=stable_research_id(
                "experiment_protocol_approval",
                {
                    "protocol_id": protocol_id,
                    "assumption_id": assumption.assumption_id,
                    "requested_by": requested_by,
                    "requested_from": design.requested_approver,
                },
            ),
            subject_type=EXPERIMENT_PROTOCOL,
            subject_id=protocol_id,
            assumption_id=assumption.assumption_id,
            requested_by=requested_by,
            requested_from=design.requested_approver,
        )
        for assumption in design.material_assumptions
    )
    protocol = _protocol_from_design(
        objective_id=objective.objective_id,
        protocol_id=protocol_id,
        design=design,
        requested_by=requested_by,
        proposed_by=proposed_by,
        approvals=approvals,
        status=ExperimentProtocolStatus.PROPOSED,
    )
    design_digest = experiment_protocol_design_digest(protocol)
    objective_digest = json_payload_hash(objective.to_dict())
    proposal_id = stable_research_id(
        "experiment_protocol_proposal",
        {
            "task_id": task_id,
            "objective_digest": objective_digest,
            "design_digest": design_digest,
            "input_refs": [item.to_dict() for item in normalized_inputs],
        },
    )
    return ExperimentProtocolProposal(
        proposal_id=proposal_id,
        task_id=task_id,
        objective_id=objective.objective_id,
        objective_digest=objective_digest,
        design_digest=design_digest,
        input_refs=normalized_inputs,
        protocol=protocol,
        requested_by=requested_by,
        proposed_by=proposed_by,
    )


def apply_experiment_protocol_approvals(
    proposal: ExperimentProtocolProposal,
    decisions: Sequence[Approval],
) -> ExperimentProtocol:
    """Apply explicit operator decisions without changing proposed design.

    Args:
        proposal: Immutable canonical proposal being decided.
        decisions: One explicit terminal decision per requested approval.

    Returns:
        Approved protocol when all decisions approve, otherwise a blocked protocol
        when at least one explicit decision rejects an assumption.

    Raises:
        ValueError: If decisions are missing, requested, duplicated, or alter any
            approval identity, subject, requester, or requested approver.
    """
    by_id = {item.approval_id: item for item in decisions}
    if len(by_id) != len(tuple(decisions)):
        raise ValueError("approval decisions must have unique approval IDs")
    expected = {item.approval_id: item for item in proposal.protocol.approvals}
    if set(by_id) != set(expected):
        raise ValueError("approval decisions must match every proposal approval")
    ordered: list[Approval] = []
    for requested in proposal.protocol.approvals:
        decided = by_id[requested.approval_id]
        if decided.status is ApprovalStatus.REQUESTED:
            raise ValueError("approval decisions cannot remain requested")
        for attribute in (
            "subject_type",
            "subject_id",
            "assumption_id",
            "requested_by",
            "requested_from",
        ):
            if getattr(decided, attribute) != getattr(requested, attribute):
                raise ValueError(
                    f"approval decision changed proposal {attribute}"
                )
        ordered.append(decided)
    status = (
        ExperimentProtocolStatus.BLOCKED
        if any(item.status is ApprovalStatus.REJECTED for item in ordered)
        else ExperimentProtocolStatus.APPROVED
    )
    protocol = replace(
        proposal.protocol,
        approvals=tuple(ordered),
        status=status,
    )
    if experiment_protocol_design_digest(protocol) != proposal.design_digest:
        raise ValueError("approval decisions changed the proposed design")
    return protocol


def experiment_protocol_design_digest(protocol: ExperimentProtocol) -> str:
    """Hash protocol design while excluding approval decision lifecycle fields."""
    payload = protocol.to_dict()
    payload.pop("status", None)
    approvals = []
    for raw_approval in payload.get("approvals", []):
        approval = dict(raw_approval)
        approval.pop("status", None)
        approval.pop("decided_by", None)
        approval.pop("rationale", None)
        approvals.append(approval)
    payload["approvals"] = approvals
    return json_payload_hash(payload)


def experiment_design_input_refs(
    design: ExperimentDesignRequest,
) -> tuple[ArtifactReportRef, ...]:
    """Return unique canonical refs consumed by one design in stable order."""
    refs = [design.strategy.implementation_ref]
    refs.extend(item.implementation_ref for item in design.risk_managers)
    for dataset in design.datasets:
        refs.extend(
            (dataset.dataset_manifest_ref, dataset.data_quality_report_ref)
        )
    if design.optimization is not None:
        artifact_type, artifact_id = parse_research_artifact_uri(
            design.optimization.objective_validation_ref
        )
        if artifact_type != IMPLEMENTATION_VALIDATION_REPORT:
            raise ValueError(
                "optimization objective ref must be an implementation validation"
            )
        refs.append(artifact_report_ref(artifact_type, artifact_id))
    unique: dict[str, ArtifactReportRef] = {}
    for reference in refs:
        unique.setdefault(reference.uri, reference)
    return tuple(unique.values())


def replace_experiment_design_refs(
    design: ExperimentDesignRequest,
    pinned_refs: Mapping[str, ArtifactReportRef],
) -> ExperimentDesignRequest:
    """Return a design whose typed refs carry current canonical payload hashes."""
    strategy = replace(
        design.strategy,
        implementation_ref=pinned_refs[design.strategy.implementation_ref.uri],
    )
    risks = tuple(
        replace(
            item,
            implementation_ref=pinned_refs[item.implementation_ref.uri],
        )
        for item in design.risk_managers
    )
    datasets = tuple(
        replace(
            item,
            dataset_manifest_ref=pinned_refs[item.dataset_manifest_ref.uri],
            data_quality_report_ref=pinned_refs[item.data_quality_report_ref.uri],
        )
        for item in design.datasets
    )
    return replace(design, strategy=strategy, risk_managers=risks, datasets=datasets)


def _protocol_from_design(
    *,
    objective_id: str,
    protocol_id: str,
    design: ExperimentDesignRequest,
    requested_by: str,
    proposed_by: str,
    approvals: tuple[Approval, ...],
    status: ExperimentProtocolStatus,
) -> ExperimentProtocol:
    return ExperimentProtocol(
        protocol_id=protocol_id,
        objective_id=objective_id,
        strategy=design.strategy,
        risk_managers=design.risk_managers,
        datasets=design.datasets,
        costs=design.costs,
        initial_portfolio=design.initial_portfolio,
        optimization=design.optimization,
        deterministic_seed=design.deterministic_seed,
        max_runs=design.max_runs,
        log_cycle_details=design.log_cycle_details,
        runtime_limits=design.runtime_limits,
        optimizer_profile=design.optimizer_profile,
        robustness_requirements=design.robustness_requirements,
        evaluation_questions=design.evaluation_questions,
        falsification_criteria=design.falsification_criteria,
        material_assumptions=design.material_assumptions,
        approvals=approvals,
        requested_by=requested_by,
        proposed_by=proposed_by,
        status=status,
    )


def _validate_design_shape(design: ExperimentDesignRequest) -> None:
    _protocol_from_design(
        objective_id="design_validation_objective",
        protocol_id="design_validation_protocol",
        design=design,
        requested_by="design_validation_request",
        proposed_by="Experiment Design Agent",
        approvals=(),
        status=ExperimentProtocolStatus.PROPOSED,
    )


def _reject_unknown_fields(
    payload: Mapping[str, Any], allowed: set[str], label: str
) -> None:
    unknown = sorted(set(payload).difference(allowed))
    if unknown:
        raise ValueError(f"{label} has unknown fields: {', '.join(unknown)}")


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be a mapping")
    return value


def _mapping_sequence(
    value: object, label: str
) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{label} must be a sequence")
    if any(not isinstance(item, Mapping) for item in value):
        raise ValueError(f"{label} must contain mappings")
    return tuple(item for item in value if isinstance(item, Mapping))


def _text_sequence(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{label} must be a sequence")
    return tuple(str(item) for item in value)
