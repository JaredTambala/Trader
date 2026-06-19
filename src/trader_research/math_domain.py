"""Quantitative Methods domain schemas for method contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class ParameterSpec:
    """Single method parameter contract."""

    name: str
    kind: str
    required: bool = True
    min_value: float | None = None
    max_value: float | None = None
    allowed_values: tuple[Any, ...] = tuple()
    default: Any = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "required": self.required,
            "min_value": self.min_value,
            "max_value": self.max_value,
            "allowed_values": list(self.allowed_values),
            "default": self.default,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ParameterSpec":
        return cls(
            name=str(payload.get("name") or ""),
            kind=str(payload.get("kind") or ""),
            required=bool(payload.get("required", True)),
            min_value=float(payload["min_value"]) if payload.get("min_value") is not None else None,
            max_value=float(payload["max_value"]) if payload.get("max_value") is not None else None,
            allowed_values=tuple(_sequence(payload.get("allowed_values"))),
            default=payload.get("default"),
        )


@dataclass(frozen=True)
class MethodRegistryEntry:
    """Maintained Quantitative Methods registry entry."""

    method_id: str
    family: str
    status: str
    purpose: str
    parameters: tuple[ParameterSpec, ...]
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    assumptions: tuple[str, ...]
    failure_modes: tuple[str, ...]
    artifact_outputs: tuple[str, ...]
    warmup: str
    nan_policy: str
    no_lookahead: bool
    requires_evidence: bool = False
    approved_method_card_ids: tuple[str, ...] = tuple()
    runtime_contract: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_type": "method_contract",
            "method_id": self.method_id,
            "family": self.family,
            "status": self.status,
            "purpose": self.purpose,
            "parameters": [parameter.to_dict() for parameter in self.parameters],
            "inputs": list(self.inputs),
            "outputs": list(self.outputs),
            "assumptions": list(self.assumptions),
            "failure_modes": list(self.failure_modes),
            "artifact_outputs": list(self.artifact_outputs),
            "warmup": self.warmup,
            "nan_policy": self.nan_policy,
            "no_lookahead": self.no_lookahead,
            "requires_evidence": self.requires_evidence,
            "approved_method_card_ids": list(self.approved_method_card_ids),
            "runtime_contract": self.runtime_contract,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "MethodRegistryEntry":
        return cls(
            method_id=str(payload.get("method_id") or ""),
            family=str(payload.get("family") or ""),
            status=str(payload.get("status") or "planned"),
            purpose=str(payload.get("purpose") or ""),
            parameters=tuple(ParameterSpec.from_dict(_mapping(item)) for item in _sequence(payload.get("parameters"))),
            inputs=_string_tuple(payload.get("inputs")),
            outputs=_string_tuple(payload.get("outputs")),
            assumptions=_string_tuple(payload.get("assumptions")),
            failure_modes=_string_tuple(payload.get("failure_modes")),
            artifact_outputs=_string_tuple(payload.get("artifact_outputs")),
            warmup=str(payload.get("warmup") or ""),
            nan_policy=str(payload.get("nan_policy") or ""),
            no_lookahead=bool(payload.get("no_lookahead", False)),
            requires_evidence=bool(payload.get("requires_evidence", False)),
            approved_method_card_ids=_string_tuple(payload.get("approved_method_card_ids")),
            runtime_contract=str(payload["runtime_contract"]) if payload.get("runtime_contract") is not None else None,
        )


@dataclass(frozen=True)
class MethodContract:
    """User-supplied method contract payload to validate."""

    method_id: str
    parameters: Mapping[str, Any] = field(default_factory=dict)
    input_schema: Mapping[str, Any] = field(default_factory=dict)
    warmup_behavior: str | None = None
    nan_policy: str | None = None
    no_lookahead: bool | None = None
    knowledge_evidence_refs: tuple[Mapping[str, Any], ...] = tuple()

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "MethodContract":
        raw_refs = payload.get("knowledge_evidence_refs") or ()
        if isinstance(raw_refs, Mapping):
            raw_refs = (raw_refs,)
        if isinstance(raw_refs, (str, bytes)) or not isinstance(raw_refs, Sequence):
            raw_refs = tuple()
        return cls(
            method_id=str(payload.get("method_id") or payload.get("name") or ""),
            parameters=_mapping(payload.get("parameters")),
            input_schema=_mapping(payload.get("input_schema")),
            warmup_behavior=str(payload["warmup_behavior"]) if payload.get("warmup_behavior") is not None else None,
            nan_policy=str(payload["nan_policy"]) if payload.get("nan_policy") is not None else None,
            no_lookahead=bool(payload["no_lookahead"]) if payload.get("no_lookahead") is not None else None,
            knowledge_evidence_refs=tuple(_mapping(ref) for ref in raw_refs if isinstance(ref, Mapping)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "method_id": self.method_id,
            "parameters": dict(self.parameters),
            "input_schema": dict(self.input_schema),
            "warmup_behavior": self.warmup_behavior,
            "nan_policy": self.nan_policy,
            "no_lookahead": self.no_lookahead,
            "knowledge_evidence_refs": [dict(ref) for ref in self.knowledge_evidence_refs],
        }


@dataclass(frozen=True)
class MethodValidationReport:
    """Validation result for one method contract."""

    method_id: str
    valid: bool
    checked_parameters: Mapping[str, Any]
    assumptions: tuple[str, ...]
    failure_modes: tuple[str, ...]
    warmup: str
    nan_policy: str
    no_lookahead: bool
    fixture_status: str
    warnings: tuple[str, ...] = tuple()
    blockers: tuple[str, ...] = tuple()

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_type": "method_validation_report",
            "method_id": self.method_id,
            "valid": self.valid,
            "checked_parameters": dict(self.checked_parameters),
            "assumptions": list(self.assumptions),
            "failure_modes": list(self.failure_modes),
            "warmup": self.warmup,
            "nan_policy": self.nan_policy,
            "no_lookahead": self.no_lookahead,
            "fixture_status": self.fixture_status,
            "warnings": list(self.warnings),
            "blockers": list(self.blockers),
        }


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> Sequence[Any]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes)):
        return (value,)
    if isinstance(value, Sequence):
        return value
    return (value,)


def _string_tuple(value: Any) -> tuple[str, ...]:
    return tuple(str(item) for item in _sequence(value) if str(item))
