"""Quantitative Methods service functions exposed through MCP."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from trader_research.contracts import SideEffect, ToolEnvelope, error_envelope, success_envelope
from trader_research.knowledge.citation_validation import validate_citations
from trader_research.knowledge.method_cards import has_approved_method_card

from .math_domain import MethodContract, MethodRegistryEntry, MethodValidationReport, ParameterSpec
from .math_registry import get_method, list_methods


MATH_LIST_METHOD_CONTRACTS = "math_list_method_contracts"
MATH_VALIDATE_METHOD_CONTRACT = "math_validate_method_contract"


def math_list_method_contracts(
    *,
    family: str | None = None,
    status: str | None = None,
    include_planned: bool = True,
    limit: int = 50,
) -> ToolEnvelope:
    """List maintained Quantitative Methods method contracts."""
    if limit < 1 or limit > 200:
        return error_envelope(
            command=MATH_LIST_METHOD_CONTRACTS,
            side_effect=SideEffect.READ_ONLY,
            code="validation_error",
            message="limit must be between 1 and 200",
        )
    methods = list_methods(family=family, status=status, include_planned=include_planned)
    return success_envelope(
        command=MATH_LIST_METHOD_CONTRACTS,
        side_effect=SideEffect.READ_ONLY,
        data={"methods": [method.to_dict() for method in methods[:limit]], "method_count": len(methods[:limit])},
    )


def math_validate_method_contract(
    *,
    artifact_root: str | Path,
    method_contract: Mapping[str, Any],
    require_evidence: bool = True,
) -> ToolEnvelope:
    """Validate a method contract against the maintained registry."""
    contract = MethodContract.from_mapping(method_contract)
    if not contract.method_id:
        return error_envelope(
            command=MATH_VALIDATE_METHOD_CONTRACT,
            side_effect=SideEffect.READ_ONLY,
            code="validation_error",
            message="method_id is required",
        )
    entry = get_method(contract.method_id)
    if entry is None:
        return error_envelope(
            command=MATH_VALIDATE_METHOD_CONTRACT,
            side_effect=SideEffect.READ_ONLY,
            code="unsupported_method",
            message=f"unsupported method_id: {contract.method_id}",
        )
    blockers, warnings, checked_parameters = _validate_parameters(entry, contract.parameters)
    if contract.warmup_behavior is not None and contract.warmup_behavior != entry.warmup:
        warnings.append("warmup_behavior differs from maintained registry metadata")
    if contract.nan_policy is not None and contract.nan_policy != entry.nan_policy:
        warnings.append("nan_policy differs from maintained registry metadata")
    if contract.no_lookahead is not None and contract.no_lookahead is not entry.no_lookahead:
        blockers.append("no_lookahead metadata conflicts with maintained registry")
    if require_evidence and entry.requires_evidence:
        method_card_ids = tuple(
            str(ref.get("method_card_id"))
            for ref in contract.knowledge_evidence_refs
            if ref.get("method_card_id") is not None
        )
        if not method_card_ids:
            blockers.append("approved method-card evidence is required")
        elif not set(method_card_ids).intersection(entry.approved_method_card_ids):
            blockers.append("method-card evidence does not match the requested method")
        elif not has_approved_method_card(artifact_root, method_card_ids):
            blockers.append("no approved method-card evidence matched this method contract")
        else:
            citation_result = validate_citations(
                artifact_root=artifact_root,
                artifact=contract.to_dict(),
                require_approved_method_card=True,
            )
            if not citation_result.ok:
                blockers.append("knowledge citation validation failed")
    report = MethodValidationReport(
        method_id=entry.method_id,
        valid=not blockers,
        checked_parameters=checked_parameters,
        assumptions=entry.assumptions,
        failure_modes=entry.failure_modes,
        warmup=entry.warmup,
        nan_policy=entry.nan_policy,
        no_lookahead=entry.no_lookahead,
        fixture_status="not_run_in_slice_5_core",
        warnings=tuple(warnings),
        blockers=tuple(blockers),
    )
    data = {
        "method": entry.to_dict(),
        "method_validation_report": report.to_dict(),
    }
    if blockers:
        return error_envelope(
            command=MATH_VALIDATE_METHOD_CONTRACT,
            side_effect=SideEffect.READ_ONLY,
            code="method_contract_validation_failed",
            message="method contract validation failed",
            data=data,
        )
    return success_envelope(
        command=MATH_VALIDATE_METHOD_CONTRACT,
        side_effect=SideEffect.READ_ONLY,
        data=data,
        warnings=tuple(warnings),
    )


def _validate_parameters(
    entry: MethodRegistryEntry,
    parameters: Mapping[str, Any],
) -> tuple[list[str], list[str], Mapping[str, Any]]:
    blockers: list[str] = []
    warnings: list[str] = []
    checked: dict[str, Any] = {}
    specs = {spec.name: spec for spec in entry.parameters}
    for name, spec in specs.items():
        if name not in parameters:
            if spec.required:
                blockers.append(f"missing required parameter: {name}")
            else:
                checked[name] = spec.default
            continue
        value = parameters[name]
        converted = _convert_parameter(value, spec)
        if converted is None:
            blockers.append(f"invalid {spec.kind} parameter: {name}")
            continue
        if spec.min_value is not None and float(converted) < spec.min_value:
            blockers.append(f"parameter {name} is below minimum {spec.min_value}")
        if spec.max_value is not None and float(converted) > spec.max_value:
            blockers.append(f"parameter {name} is above maximum {spec.max_value}")
        if spec.allowed_values and converted not in spec.allowed_values:
            blockers.append(f"parameter {name} is not in allowed values")
        checked[name] = converted
    unknown = sorted(set(parameters) - set(specs))
    if unknown:
        warnings.append(f"unknown parameters ignored: {', '.join(unknown)}")
    return blockers, warnings, checked


def _convert_parameter(value: Any, spec: ParameterSpec) -> Any:
    try:
        if spec.kind == "int":
            if isinstance(value, bool):
                return None
            return int(value)
        if spec.kind == "float":
            if isinstance(value, bool):
                return None
            return float(value)
        if spec.kind == "str":
            return str(value)
    except (TypeError, ValueError):
        return None
    return value
