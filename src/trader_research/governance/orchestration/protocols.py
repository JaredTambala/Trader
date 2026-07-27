"""Research-objective, experiment-protocol, and approval contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from trader_research.foundation import ORCHESTRATION_DOMAIN_OWNER, jsonable

from ..artifacts import (
    APPROVAL_REQUEST,
    EXPERIMENT_PROTOCOL,
    IMPLEMENTATION_VERSION,
    RESEARCH_OBJECTIVE,
    SUPPORTED_ARTIFACT_TYPES,
)
from ..handoffs import ArtifactReportRef, DataRequirement
from ._validation import (
    _enum_value,
    _mapping,
    _mapping_sequence,
    _number,
    _optional_text,
    _parse_timestamp,
    _required_text,
    _required_text_sequence,
    _sequence,
    _text_tuple,
    _unique,
    _validate_payload_artifact_type,
    _validate_ref_type,
)
from .enums import (
    ApprovalStatus,
    DatasetRole,
    ExperimentProtocolStatus,
    OptimizationDirection,
    ResearchObjectiveStatus,
    TunableValueType,
)

@dataclass(frozen=True)
class ObjectiveConstraint:
    """One operator-declared boundary on a research objective."""

    key: str
    value: Any
    description: str = ""

    def __post_init__(self) -> None:
        """Validate the stable constraint key."""
        _required_text(self.key, "objective constraint key")

    def to_dict(self) -> dict[str, Any]:
        """Serialize this declared constraint."""
        return {
            "key": self.key,
            "value": jsonable(self.value),
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ObjectiveConstraint":
        """Parse an objective constraint from JSON-compatible data."""
        return cls(
            key=str(payload.get("key") or ""),
            value=payload.get("value"),
            description=str(payload.get("description") or ""),
        )

@dataclass(frozen=True)
class ResearchObjective:
    """Operator-owned desired outcome and explicit research boundaries."""

    objective_id: str
    statement: str
    success_criteria: tuple[str, ...]
    requested_by: str
    actor: str
    constraints: tuple[ObjectiveConstraint, ...] = ()
    supplied_artifact_refs: tuple[ArtifactReportRef, ...] = ()
    status: ResearchObjectiveStatus = ResearchObjectiveStatus.DRAFT

    artifact_type = RESEARCH_OBJECTIVE
    domain_owner = ORCHESTRATION_DOMAIN_OWNER

    def __post_init__(self) -> None:
        """Validate objective identity, intent, provenance, and constraints."""
        _required_text(self.objective_id, "objective_id")
        _required_text(self.statement, "objective statement")
        _required_text(self.requested_by, "objective requested_by")
        _required_text(self.actor, "objective actor")
        _required_text_sequence(self.success_criteria, "objective success criteria")
        _unique((item.key for item in self.constraints), "objective constraint keys")
        _unique(
            (item.uri for item in self.supplied_artifact_refs),
            "supplied artifact refs",
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize the objective as a canonical artifact payload."""
        return {
            "artifact_type": self.artifact_type,
            "objective_id": self.objective_id,
            "statement": self.statement,
            "success_criteria": list(self.success_criteria),
            "constraints": [item.to_dict() for item in self.constraints],
            "supplied_artifact_refs": [
                item.to_dict() for item in self.supplied_artifact_refs
            ],
            "requested_by": self.requested_by,
            "actor": self.actor,
            "status": self.status.value,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ResearchObjective":
        """Parse a research objective from JSON-compatible data."""
        _validate_payload_artifact_type(payload, RESEARCH_OBJECTIVE)
        return cls(
            objective_id=str(payload.get("objective_id") or ""),
            statement=str(payload.get("statement") or ""),
            success_criteria=_text_tuple(payload.get("success_criteria")),
            constraints=tuple(
                ObjectiveConstraint.from_dict(item)
                for item in _mapping_sequence(payload.get("constraints"))
            ),
            supplied_artifact_refs=tuple(
                ArtifactReportRef.from_dict(item)
                for item in _mapping_sequence(payload.get("supplied_artifact_refs"))
            ),
            requested_by=str(payload.get("requested_by") or ""),
            actor=str(payload.get("actor") or ""),
            status=_enum_value(
                ResearchObjectiveStatus,
                payload.get("status"),
                "objective status",
            ),
        )


@dataclass(frozen=True)
class ProtocolDataset:
    """A bounded Data Agent requirement with an explicit experiment role."""

    requirement_id: str
    role: DatasetRole
    requirement: DataRequirement
    sealed: bool = False

    def __post_init__(self) -> None:
        """Validate dataset identity and holdout sealing."""
        _required_text(self.requirement_id, "dataset requirement_id")
        if self.role is DatasetRole.HOLDOUT and not self.sealed:
            raise ValueError("holdout dataset requirements must be sealed")
        if self.role is not DatasetRole.HOLDOUT and self.sealed:
            raise ValueError("only holdout dataset requirements may be sealed")

    def to_dict(self) -> dict[str, Any]:
        """Serialize this protocol dataset requirement."""
        return {
            "requirement_id": self.requirement_id,
            "role": self.role.value,
            "requirement": self.requirement.to_dict(),
            "sealed": self.sealed,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ProtocolDataset":
        """Parse a protocol dataset requirement."""
        return cls(
            requirement_id=str(payload.get("requirement_id") or ""),
            role=_enum_value(DatasetRole, payload.get("role"), "dataset role"),
            requirement=DataRequirement.from_dict(
                _mapping(payload.get("requirement"))
            ),
            sealed=bool(payload.get("sealed", False)),
        )


@dataclass(frozen=True)
class CostAssumption:
    """One explicit cost included in the proposed experiment."""

    name: str
    value: float
    unit: str

    def __post_init__(self) -> None:
        """Validate cost identity, non-negative value, and unit."""
        _required_text(self.name, "cost name")
        _required_text(self.unit, "cost unit")
        if self.value < 0:
            raise ValueError("cost assumption value cannot be negative")

    def to_dict(self) -> dict[str, Any]:
        """Serialize this cost assumption."""
        return {"name": self.name, "value": self.value, "unit": self.unit}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CostAssumption":
        """Parse a cost assumption."""
        return cls(
            name=str(payload.get("name") or ""),
            value=float(payload.get("value", 0.0)),
            unit=str(payload.get("unit") or ""),
        )


@dataclass(frozen=True)
class InitialPosition:
    """One explicitly declared initial portfolio position."""

    symbol: str
    quantity: float

    def __post_init__(self) -> None:
        """Validate position symbol."""
        _required_text(self.symbol, "initial position symbol")

    def to_dict(self) -> dict[str, Any]:
        """Serialize this initial position."""
        return {"symbol": self.symbol, "quantity": self.quantity}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "InitialPosition":
        """Parse an initial position."""
        return cls(
            symbol=str(payload.get("symbol") or ""),
            quantity=float(payload.get("quantity", 0.0)),
        )


@dataclass(frozen=True)
class InitialPortfolio:
    """Explicit initial state used by baseline and variant runs."""

    cash: float
    currency: str
    positions: tuple[InitialPosition, ...] = ()

    def __post_init__(self) -> None:
        """Validate cash, currency, and unique positions."""
        if self.cash < 0:
            raise ValueError("initial portfolio cash cannot be negative")
        _required_text(self.currency, "initial portfolio currency")
        _unique((item.symbol for item in self.positions), "initial position symbols")

    def to_dict(self) -> dict[str, Any]:
        """Serialize initial portfolio state."""
        return {
            "cash": self.cash,
            "currency": self.currency,
            "positions": [item.to_dict() for item in self.positions],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "InitialPortfolio":
        """Parse initial portfolio state."""
        return cls(
            cash=float(payload.get("cash", 0.0)),
            currency=str(payload.get("currency") or ""),
            positions=tuple(
                InitialPosition.from_dict(item)
                for item in _mapping_sequence(payload.get("positions"))
            ),
        )


@dataclass(frozen=True)
class TunableDimension:
    """One provider-neutral parameter search dimension."""

    dimension_id: str
    target_path: str
    value_type: TunableValueType
    lower: int | float | None = None
    upper: int | float | None = None
    step: int | float | None = None
    choices: tuple[Any, ...] = ()

    def __post_init__(self) -> None:
        """Validate numeric bounds or categorical choices."""
        _required_text(self.dimension_id, "tunable dimension_id")
        _required_text(self.target_path, "tunable target_path")
        if not self.target_path.startswith("/"):
            raise ValueError("tunable target_path must be a JSON pointer")
        if self.value_type is TunableValueType.CATEGORICAL:
            if not self.choices:
                raise ValueError("categorical tunable dimension choices are required")
            if self.lower is not None or self.upper is not None or self.step is not None:
                raise ValueError("categorical tunable dimensions cannot define bounds")
            return
        if self.choices:
            raise ValueError("numeric tunable dimensions cannot define choices")
        if self.lower is None or self.upper is None:
            raise ValueError("numeric tunable dimension bounds are required")
        if self.lower >= self.upper:
            raise ValueError("tunable dimension lower must be less than upper")
        if self.step is not None and self.step <= 0:
            raise ValueError("tunable dimension step must be positive")
        if self.value_type is TunableValueType.INTEGER and any(
            value is not None and not isinstance(value, int)
            for value in (self.lower, self.upper, self.step)
        ):
            raise ValueError("integer tunable dimension bounds must be integers")

    def to_dict(self) -> dict[str, Any]:
        """Serialize this search dimension."""
        return {
            "dimension_id": self.dimension_id,
            "target_path": self.target_path,
            "value_type": self.value_type.value,
            "lower": self.lower,
            "upper": self.upper,
            "step": self.step,
            "choices": jsonable(self.choices),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "TunableDimension":
        """Parse a provider-neutral search dimension."""
        value_type = _enum_value(
            TunableValueType,
            payload.get("value_type"),
            "tunable value_type",
        )
        lower = payload.get("lower")
        upper = payload.get("upper")
        step = payload.get("step")
        return cls(
            dimension_id=str(payload.get("dimension_id") or ""),
            target_path=str(payload.get("target_path") or ""),
            value_type=value_type,
            lower=_number(lower),
            upper=_number(upper),
            step=_number(step),
            choices=tuple(_sequence(payload.get("choices"))),
        )


@dataclass(frozen=True)
class ProtocolConstraint:
    """A declared experiment constraint evaluated outside the objective."""

    constraint_id: str
    metric: str
    operator: str
    threshold: float

    def __post_init__(self) -> None:
        """Validate constraint identity and comparison operator."""
        _required_text(self.constraint_id, "protocol constraint_id")
        _required_text(self.metric, "protocol constraint metric")
        if self.operator not in {"<", "<=", "==", ">=", ">"}:
            raise ValueError(f"unsupported protocol constraint operator: {self.operator}")

    def to_dict(self) -> dict[str, Any]:
        """Serialize this protocol constraint."""
        return {
            "constraint_id": self.constraint_id,
            "metric": self.metric,
            "operator": self.operator,
            "threshold": self.threshold,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ProtocolConstraint":
        """Parse a protocol constraint."""
        return cls(
            constraint_id=str(payload.get("constraint_id") or ""),
            metric=str(payload.get("metric") or ""),
            operator=str(payload.get("operator") or ""),
            threshold=float(payload.get("threshold", 0.0)),
        )


@dataclass(frozen=True)
class OptimizationProtocol:
    """Provider-neutral optimisation intent embedded in an experiment protocol."""

    objective_validation_ref: str
    direction: OptimizationDirection
    trial_budget: int
    seed: int
    dimensions: tuple[TunableDimension, ...]
    constraints: tuple[ProtocolConstraint, ...] = ()

    def __post_init__(self) -> None:
        """Validate the objective, budget, dimensions, and constraints."""
        _required_text(
            self.objective_validation_ref,
            "optimization objective_validation_ref",
        )
        if not self.objective_validation_ref.startswith("research://postgres/"):
            raise ValueError(
                "optimization objective_validation_ref must be a canonical research URI"
            )
        if self.trial_budget <= 0:
            raise ValueError("optimization trial_budget must be positive")
        if self.seed < 0:
            raise ValueError("optimization seed cannot be negative")
        if not self.dimensions:
            raise ValueError("optimization dimensions are required")
        _unique(
            (item.dimension_id for item in self.dimensions),
            "optimization dimension IDs",
        )
        _unique(
            (item.target_path for item in self.dimensions),
            "optimization target paths",
        )
        _unique(
            (item.constraint_id for item in self.constraints),
            "optimization constraint IDs",
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize this optimisation design."""
        return {
            "objective_validation_ref": self.objective_validation_ref,
            "direction": self.direction.value,
            "trial_budget": self.trial_budget,
            "seed": self.seed,
            "dimensions": [item.to_dict() for item in self.dimensions],
            "constraints": [item.to_dict() for item in self.constraints],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "OptimizationProtocol":
        """Parse an optimisation design."""
        return cls(
            objective_validation_ref=str(
                payload.get("objective_validation_ref") or ""
            ),
            direction=_enum_value(
                OptimizationDirection,
                payload.get("direction"),
                "optimization direction",
            ),
            trial_budget=int(payload.get("trial_budget", 0)),
            seed=int(payload.get("seed", 0)),
            dimensions=tuple(
                TunableDimension.from_dict(item)
                for item in _mapping_sequence(payload.get("dimensions"))
            ),
            constraints=tuple(
                ProtocolConstraint.from_dict(item)
                for item in _mapping_sequence(payload.get("constraints"))
            ),
        )


@dataclass(frozen=True)
class RobustnessRequirement:
    """One immutable challenge the approved protocol requires."""

    requirement_id: str
    attack_type: str
    claim: str
    configuration: Mapping[str, Any] = field(default_factory=dict)
    required: bool = True

    def __post_init__(self) -> None:
        """Validate robustness requirement identity and claim."""
        _required_text(self.requirement_id, "robustness requirement_id")
        _required_text(self.attack_type, "robustness attack_type")
        _required_text(self.claim, "robustness claim")

    def to_dict(self) -> dict[str, Any]:
        """Serialize this robustness requirement."""
        return {
            "requirement_id": self.requirement_id,
            "attack_type": self.attack_type,
            "claim": self.claim,
            "configuration": jsonable(self.configuration),
            "required": self.required,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RobustnessRequirement":
        """Parse a robustness requirement."""
        return cls(
            requirement_id=str(payload.get("requirement_id") or ""),
            attack_type=str(payload.get("attack_type") or ""),
            claim=str(payload.get("claim") or ""),
            configuration=_mapping(payload.get("configuration")),
            required=bool(payload.get("required", True)),
        )


@dataclass(frozen=True)
class MaterialAssumption:
    """One experiment-design choice requiring explicit approval."""

    assumption_id: str
    category: str
    statement: str
    value: Any

    def __post_init__(self) -> None:
        """Validate assumption identity, category, and statement."""
        _required_text(self.assumption_id, "material assumption_id")
        _required_text(self.category, "material assumption category")
        _required_text(self.statement, "material assumption statement")

    def to_dict(self) -> dict[str, Any]:
        """Serialize this material assumption."""
        return {
            "assumption_id": self.assumption_id,
            "category": self.category,
            "statement": self.statement,
            "value": jsonable(self.value),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "MaterialAssumption":
        """Parse a material assumption."""
        return cls(
            assumption_id=str(payload.get("assumption_id") or ""),
            category=str(payload.get("category") or ""),
            statement=str(payload.get("statement") or ""),
            value=payload.get("value"),
        )


@dataclass(frozen=True)
class Approval:
    """Explicit operator decision over one material assumption."""

    approval_id: str
    subject_type: str
    subject_id: str
    assumption_id: str
    requested_by: str
    requested_from: str
    status: ApprovalStatus = ApprovalStatus.REQUESTED
    decided_by: str | None = None
    rationale: str | None = None

    artifact_type = APPROVAL_REQUEST
    domain_owner = ORCHESTRATION_DOMAIN_OWNER

    def __post_init__(self) -> None:
        """Validate approval subject, request provenance, and decision fields."""
        _required_text(self.approval_id, "approval_id")
        if self.subject_type not in SUPPORTED_ARTIFACT_TYPES:
            raise ValueError(f"unsupported approval subject_type: {self.subject_type}")
        _required_text(self.subject_id, "approval subject_id")
        _required_text(self.assumption_id, "approval assumption_id")
        _required_text(self.requested_by, "approval requested_by")
        _required_text(self.requested_from, "approval requested_from")
        if self.status is ApprovalStatus.REQUESTED:
            if self.decided_by is not None or self.rationale is not None:
                raise ValueError(
                    "requested approvals cannot contain decision fields"
                )
            return
        _required_text(self.decided_by or "", "approval decided_by")
        _required_text(self.rationale or "", "approval rationale")

    def to_dict(self) -> dict[str, Any]:
        """Serialize this approval request or decision."""
        return {
            "artifact_type": self.artifact_type,
            "approval_id": self.approval_id,
            "subject_type": self.subject_type,
            "subject_id": self.subject_id,
            "assumption_id": self.assumption_id,
            "requested_by": self.requested_by,
            "requested_from": self.requested_from,
            "status": self.status.value,
            "decided_by": self.decided_by,
            "rationale": self.rationale,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "Approval":
        """Parse an approval request or decision."""
        _validate_payload_artifact_type(payload, APPROVAL_REQUEST)
        return cls(
            approval_id=str(payload.get("approval_id") or ""),
            subject_type=str(payload.get("subject_type") or ""),
            subject_id=str(payload.get("subject_id") or ""),
            assumption_id=str(payload.get("assumption_id") or ""),
            requested_by=str(payload.get("requested_by") or ""),
            requested_from=str(payload.get("requested_from") or ""),
            status=_enum_value(
                ApprovalStatus,
                payload.get("status"),
                "approval status",
            ),
            decided_by=_optional_text(payload.get("decided_by")),
            rationale=_optional_text(payload.get("rationale")),
        )


@dataclass(frozen=True)
class ExperimentProtocol:
    """Immutable proposed or approved procedure for supplied implementations."""

    protocol_id: str
    objective_id: str
    strategy_implementation_ref: ArtifactReportRef
    risk_implementation_refs: tuple[ArtifactReportRef, ...]
    datasets: tuple[ProtocolDataset, ...]
    costs: tuple[CostAssumption, ...]
    initial_portfolio: InitialPortfolio
    robustness_requirements: tuple[RobustnessRequirement, ...]
    evaluation_questions: tuple[str, ...]
    falsification_criteria: tuple[str, ...]
    material_assumptions: tuple[MaterialAssumption, ...]
    requested_by: str
    proposed_by: str
    optimization: OptimizationProtocol | None = None
    approvals: tuple[Approval, ...] = ()
    status: ExperimentProtocolStatus = ExperimentProtocolStatus.PROPOSED

    artifact_type = EXPERIMENT_PROTOCOL

    def __post_init__(self) -> None:
        """Validate complete protocol structure and approval integrity."""
        _required_text(self.protocol_id, "protocol_id")
        _required_text(self.objective_id, "protocol objective_id")
        _required_text(self.requested_by, "protocol requested_by")
        _required_text(self.proposed_by, "protocol proposed_by")
        _validate_ref_type(
            self.strategy_implementation_ref,
            IMPLEMENTATION_VERSION,
            "strategy implementation",
        )
        for reference in self.risk_implementation_refs:
            _validate_ref_type(
                reference,
                IMPLEMENTATION_VERSION,
                "risk implementation",
            )
        if not self.datasets:
            raise ValueError("experiment protocol datasets are required")
        _unique(
            (item.requirement_id for item in self.datasets),
            "protocol dataset requirement IDs",
        )
        roles = {item.role for item in self.datasets}
        if DatasetRole.BASELINE not in roles and DatasetRole.SELECTION not in roles:
            raise ValueError(
                "experiment protocol requires a baseline or selection dataset"
            )
        if self.optimization is not None:
            if DatasetRole.SELECTION not in roles or DatasetRole.HOLDOUT not in roles:
                raise ValueError(
                    "optimization requires selection and sealed holdout datasets"
                )
            self._validate_optimization_datasets()
        _unique((item.name for item in self.costs), "protocol cost names")
        _unique(
            (item.requirement_id for item in self.robustness_requirements),
            "robustness requirement IDs",
        )
        _required_text_sequence(
            self.evaluation_questions,
            "protocol evaluation questions",
        )
        _required_text_sequence(
            self.falsification_criteria,
            "protocol falsification criteria",
        )
        _unique(
            (item.assumption_id for item in self.material_assumptions),
            "material assumption IDs",
        )
        _unique((item.approval_id for item in self.approvals), "approval IDs")
        self._validate_approvals()

    def _validate_optimization_datasets(self) -> None:
        selection = [
            item for item in self.datasets if item.role is DatasetRole.SELECTION
        ]
        holdout = [
            item for item in self.datasets if item.role is DatasetRole.HOLDOUT
        ]
        if len(selection) != 1 or len(holdout) != 1:
            raise ValueError(
                "optimization requires exactly one selection and one holdout dataset"
            )
        selection_requirement = selection[0].requirement
        holdout_requirement = holdout[0].requirement
        for attribute in ("symbols", "asset_class", "timeframe", "source"):
            if getattr(selection_requirement, attribute) != getattr(
                holdout_requirement,
                attribute,
            ):
                raise ValueError(
                    f"optimization holdout {attribute} must match selection data"
                )
        selection_end = _parse_timestamp(
            selection_requirement.end,
            "selection dataset end",
        )
        holdout_start = _parse_timestamp(
            holdout_requirement.start,
            "holdout dataset start",
        )
        if holdout_start <= selection_end:
            raise ValueError(
                "optimization holdout must begin after the selection dataset ends"
            )

    def _validate_approvals(self) -> None:
        assumptions = {item.assumption_id for item in self.material_assumptions}
        approvals_by_assumption: dict[str, Approval] = {}
        for approval in self.approvals:
            if approval.subject_type != EXPERIMENT_PROTOCOL:
                raise ValueError(
                    "protocol approvals must target experiment_protocol"
                )
            if approval.subject_id != self.protocol_id:
                raise ValueError("protocol approval subject_id does not match protocol")
            if approval.assumption_id not in assumptions:
                raise ValueError(
                    "protocol approval references an unknown material assumption"
                )
            if approval.assumption_id in approvals_by_assumption:
                raise ValueError(
                    "protocol has multiple approvals for one material assumption"
                )
            approvals_by_assumption[approval.assumption_id] = approval
        if self.status is ExperimentProtocolStatus.APPROVED:
            missing = assumptions.difference(approvals_by_assumption)
            if missing:
                raise ValueError(
                    "approved protocol is missing material approvals: "
                    + ", ".join(sorted(missing))
                )
            unapproved = [
                item.assumption_id
                for item in approvals_by_assumption.values()
                if item.status is not ApprovalStatus.APPROVED
            ]
            if unapproved:
                raise ValueError(
                    "approved protocol contains unresolved approvals: "
                    + ", ".join(sorted(unapproved))
                )
        if any(
            item.status is ApprovalStatus.REJECTED for item in self.approvals
        ) and self.status not in {
            ExperimentProtocolStatus.BLOCKED,
            ExperimentProtocolStatus.SUPERSEDED,
        }:
            raise ValueError("rejected approvals require a blocked protocol")

    def to_dict(self) -> dict[str, Any]:
        """Serialize the complete experiment protocol."""
        return {
            "artifact_type": self.artifact_type,
            "protocol_id": self.protocol_id,
            "objective_id": self.objective_id,
            "strategy_implementation_ref": (
                self.strategy_implementation_ref.to_dict()
            ),
            "risk_implementation_refs": [
                item.to_dict() for item in self.risk_implementation_refs
            ],
            "datasets": [item.to_dict() for item in self.datasets],
            "costs": [item.to_dict() for item in self.costs],
            "initial_portfolio": self.initial_portfolio.to_dict(),
            "optimization": (
                self.optimization.to_dict() if self.optimization is not None else None
            ),
            "robustness_requirements": [
                item.to_dict() for item in self.robustness_requirements
            ],
            "evaluation_questions": list(self.evaluation_questions),
            "falsification_criteria": list(self.falsification_criteria),
            "material_assumptions": [
                item.to_dict() for item in self.material_assumptions
            ],
            "approvals": [item.to_dict() for item in self.approvals],
            "requested_by": self.requested_by,
            "proposed_by": self.proposed_by,
            "status": self.status.value,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ExperimentProtocol":
        """Parse a complete experiment protocol."""
        _validate_payload_artifact_type(payload, EXPERIMENT_PROTOCOL)
        optimization_payload = payload.get("optimization")
        return cls(
            protocol_id=str(payload.get("protocol_id") or ""),
            objective_id=str(payload.get("objective_id") or ""),
            strategy_implementation_ref=ArtifactReportRef.from_dict(
                _mapping(payload.get("strategy_implementation_ref"))
            ),
            risk_implementation_refs=tuple(
                ArtifactReportRef.from_dict(item)
                for item in _mapping_sequence(
                    payload.get("risk_implementation_refs")
                )
            ),
            datasets=tuple(
                ProtocolDataset.from_dict(item)
                for item in _mapping_sequence(payload.get("datasets"))
            ),
            costs=tuple(
                CostAssumption.from_dict(item)
                for item in _mapping_sequence(payload.get("costs"))
            ),
            initial_portfolio=InitialPortfolio.from_dict(
                _mapping(payload.get("initial_portfolio"))
            ),
            optimization=(
                OptimizationProtocol.from_dict(optimization_payload)
                if isinstance(optimization_payload, Mapping)
                else None
            ),
            robustness_requirements=tuple(
                RobustnessRequirement.from_dict(item)
                for item in _mapping_sequence(
                    payload.get("robustness_requirements")
                )
            ),
            evaluation_questions=_text_tuple(payload.get("evaluation_questions")),
            falsification_criteria=_text_tuple(
                payload.get("falsification_criteria")
            ),
            material_assumptions=tuple(
                MaterialAssumption.from_dict(item)
                for item in _mapping_sequence(payload.get("material_assumptions"))
            ),
            approvals=tuple(
                Approval.from_dict(item)
                for item in _mapping_sequence(payload.get("approvals"))
            ),
            requested_by=str(payload.get("requested_by") or ""),
            proposed_by=str(payload.get("proposed_by") or ""),
            status=_enum_value(
                ExperimentProtocolStatus,
                payload.get("status"),
                "experiment protocol status",
            ),
        )
