"""Quantitative Methods service functions exposed through MCP."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from trader_research.foundation import ApplicationResult, error_result, success_result
from trader_research.foundation.artifacts import ResearchArtifactStore
from trader_research.knowledge.approved_cards import ApprovedMethodCardReadError, ApprovedMethodCardReader
from trader_research.methodology.kernels import compile_cpp_kernel, generate_cpp_kernel
from trader_research.methodology.implementation import (
    generate_python_method_from_payload,
    register_method_implementation,
    run_indicator_fixtures,
    run_signal_fixtures,
)
from trader_research.methodology.packaging import package_method_artifact
from trader_research.methodology.multiple_testing import run_multiple_testing_report
from trader_research.methodology.diagnostics import run_signal_diagnostics

from .contracts import MethodContract, MethodRegistryEntry, MethodValidationReport, ParameterSpec
from .registry import get_method, list_methods


MATH_LIST_METHOD_CONTRACTS = "math_list_method_contracts"
MATH_VALIDATE_METHOD_CONTRACT = "math_validate_method_contract"
MATH_REGISTER_METHOD_IMPLEMENTATION = "math_register_method_implementation"
MATH_RUN_INDICATOR_FIXTURES = "math_run_indicator_fixtures"
MATH_RUN_SIGNAL_FIXTURES = "math_run_signal_fixtures"
MATH_GENERATE_PYTHON_METHOD = "math_generate_python_method"
MATH_RUN_SIGNAL_DIAGNOSTICS = "math_run_signal_diagnostics"
MATH_RUN_MULTIPLE_TESTING_REPORT = "math_run_multiple_testing_report"
MATH_GENERATE_CPP_KERNEL = "math_generate_cpp_kernel"
MATH_COMPILE_KERNEL = "math_compile_kernel"
MATH_PACKAGE_METHOD_ARTIFACT = "math_package_method_artifact"


def math_list_method_contracts(
    *,
    family: str | None = None,
    status: str | None = None,
    include_planned: bool = True,
    limit: int = 50,
) -> ApplicationResult:
    """Return bounded registry method contracts through a read-only tool result.

    The command validates the caller's limit, applies family/status/planned filters
    through the registry layer, and translates knowledge-store failures into
    stable error results. Results are serialized with each method's maintained
    assumptions, parameters, and runtime contract metadata.
    """
    if limit < 1 or limit > 200:
        return error_result(
            command=MATH_LIST_METHOD_CONTRACTS,
            code="validation_error",
            message="limit must be between 1 and 200",
        )
    methods = list_methods(family=family, status=status, include_planned=include_planned)
    return success_result(
        command=MATH_LIST_METHOD_CONTRACTS,
        data={"methods": [method.to_dict() for method in methods[:limit]], "method_count": len(methods[:limit])},
    )


def math_validate_method_contract(
    *,
    artifact_root: str | Path,
    method_contract: Mapping[str, Any],
    require_evidence: bool = True,
    approved_card_reader: ApprovedMethodCardReader | None = None,
) -> ApplicationResult:
    """Validate caller-supplied method metadata against maintained contracts.

    The tool normalizes the incoming contract, verifies the method exists, checks
    required parameters and parameter bounds, compares warmup/NaN/no-lookahead
    metadata, and optionally requires approved method-card evidence. All warnings,
    blockers, checked values, and inherited registry constraints are returned in a
    `MethodValidationReport`.
    """
    contract = MethodContract.from_mapping(method_contract)
    if not contract.method_id:
        return error_result(
            command=MATH_VALIDATE_METHOD_CONTRACT,
            code="validation_error",
            message="method_id is required",
        )
    entry = get_method(contract.method_id)
    if entry is None:
        return error_result(
            command=MATH_VALIDATE_METHOD_CONTRACT,
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
        else:
            if approved_card_reader is None:
                blockers.append("approved method-card reader is required")
                approved_card_matches = False
                any_card_matches = False
            else:
                try:
                    approved_card_matches = approved_card_reader.has_approved_method_card(
                        method_card_ids,
                        method_id=entry.method_id,
                    )
                    any_card_matches = _method_card_ids_match_requested_method(
                        method_card_ids,
                        method_id=entry.method_id,
                        approved_card_reader=approved_card_reader,
                    )
                except ApprovedMethodCardReadError as exc:
                    return error_result(
                        command=MATH_VALIDATE_METHOD_CONTRACT,
                        code="approved_method_card_read_error",
                        message=str(exc),
                    )
            if not approved_card_matches and not any_card_matches:
                blockers.append("method-card evidence does not match the requested method")
            elif not approved_card_matches:
                blockers.append("no approved method-card evidence matched this method contract")
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
        return error_result(
            command=MATH_VALIDATE_METHOD_CONTRACT,
            code="method_contract_validation_failed",
            message="method contract validation failed",
            data=data,
        )
    return success_result(
        command=MATH_VALIDATE_METHOD_CONTRACT,
        data=data,
        warnings=tuple(warnings),
    )


def math_register_method_implementation(
    *,
    artifact_root: str | Path,
    method_id: str,
    method_card_ids: list[str],
    method_contract: Mapping[str, Any] | None = None,
    entrypoint: str | None = None,
    source_path: str | None = None,
    class_name: str | None = None,
    constructor_kwargs: Mapping[str, Any] | None = None,
    implementation_kind: str = "maintained",
    dependency_allowlist: list[str] | None = None,
    expected_source_hash: str | None = None,
    approved_card_reader: ApprovedMethodCardReader | None = None,
    artifact_store: ResearchArtifactStore | None = None,
) -> ApplicationResult:
    """Delegate registration of a concrete Python method implementation manifest.

    The wrapper preserves the MCP-facing command signature while the registration
    service validates method evidence, entrypoint/source metadata, dependency
    allowlists, source hashes, runtime contract, and importability before writing
    the manifest artifact.
    """
    return register_method_implementation(
        artifact_root=artifact_root,
        method_id=method_id,
        method_card_ids=method_card_ids,
        method_contract=method_contract,
        entrypoint=entrypoint,
        source_path=source_path,
        class_name=class_name,
        constructor_kwargs=constructor_kwargs,
        implementation_kind=implementation_kind,
        dependency_allowlist=dependency_allowlist,
        expected_source_hash=expected_source_hash,
        approved_card_reader=approved_card_reader,
        artifact_store=artifact_store,
    )


def math_run_indicator_fixtures(
    *,
    artifact_root: str | Path,
    implementation_id: str | None = None,
    implementation_manifest: Mapping[str, Any] | None = None,
    fixtures: list[dict[str, Any]] | None = None,
    approved_card_reader: ApprovedMethodCardReader | None = None,
    artifact_store: ResearchArtifactStore | None = None,
) -> ApplicationResult:
    """Run indicator fixture validation through the method-implementation service.

    The wrapper accepts either an implementation ID or manifest payload, passes
    optional fixture overrides through unchanged, and returns the local-mutating
    validation result produced by the fixture runner.
    """
    return run_indicator_fixtures(
        artifact_root=artifact_root,
        implementation_id=implementation_id,
        implementation_manifest=implementation_manifest,
        fixtures=fixtures,
        approved_card_reader=approved_card_reader,
        artifact_store=artifact_store,
    )


def math_run_signal_fixtures(
    *,
    artifact_root: str | Path,
    implementation_id: str | None = None,
    implementation_manifest: Mapping[str, Any] | None = None,
    fixtures: list[dict[str, Any]] | None = None,
    approved_card_reader: ApprovedMethodCardReader | None = None,
    artifact_store: ResearchArtifactStore | None = None,
) -> ApplicationResult:
    """Run signal fixture validation through the method-implementation service.

    The wrapper mirrors indicator validation for signal runtime contracts, keeping
    MCP inputs stable while the fixture service resolves manifests, reloads the
    implementation, runs prefix/no-lookahead checks, and writes a validation report.
    """
    return run_signal_fixtures(
        artifact_root=artifact_root,
        implementation_id=implementation_id,
        implementation_manifest=implementation_manifest,
        fixtures=fixtures,
        approved_card_reader=approved_card_reader,
        artifact_store=artifact_store,
    )


def math_generate_python_method(
    *,
    artifact_root: str | Path,
    method_id: str,
    method_card_ids: list[str],
    method_contract: Mapping[str, Any],
    llm_payload: Mapping[str, Any],
    fixtures: list[dict[str, Any]] | None = None,
    approved_card_reader: ApprovedMethodCardReader | None = None,
) -> ApplicationResult:
    """Persist and validate a quarantined Python method from an LLM JSON payload."""
    return generate_python_method_from_payload(
        artifact_root=artifact_root,
        method_id=method_id,
        method_card_ids=method_card_ids,
        method_contract=method_contract,
        llm_payload=llm_payload,
        fixtures=fixtures,
        approved_card_reader=approved_card_reader,
    )


def math_run_signal_diagnostics(
    *,
    artifact_root: str | Path,
    signal_observations: list[dict[str, Any]],
    forward_return_labels: list[dict[str, Any]],
    candidate_family_manifest: Mapping[str, Any],
    method_contracts: list[dict[str, Any]],
    quantile_count: int = 5,
    data_quality_report: Mapping[str, Any] | None = None,
    approved_card_reader: ApprovedMethodCardReader | None = None,
) -> ApplicationResult:
    """Run signal-composition diagnostics over declared trade-intent candidates."""
    return run_signal_diagnostics(
        artifact_root=artifact_root,
        signal_observations=signal_observations,
        forward_return_labels=forward_return_labels,
        candidate_family_manifest=candidate_family_manifest,
        method_contracts=method_contracts,
        quantile_count=quantile_count,
        data_quality_report=data_quality_report,
        approved_card_reader=approved_card_reader,
    )


def math_run_multiple_testing_report(
    *,
    artifact_root: str | Path,
    candidate_family_manifest: Mapping[str, Any],
    metric_matrix: list[dict[str, Any]],
    method_contract: Mapping[str, Any],
    alpha: float | None = None,
    approved_card_reader: ApprovedMethodCardReader | None = None,
) -> ApplicationResult:
    """Run multiple-testing controls across a declared signal candidate family."""
    return run_multiple_testing_report(
        artifact_root=artifact_root,
        candidate_family_manifest=candidate_family_manifest,
        metric_matrix=metric_matrix,
        method_contract=method_contract,
        alpha=alpha,
        approved_card_reader=approved_card_reader,
    )


def math_generate_cpp_kernel(
    *,
    artifact_root: str | Path,
    implementation_id: str | None = None,
    implementation_manifest: Mapping[str, Any] | None = None,
    template_id: str | None = None,
) -> ApplicationResult:
    """Generate a template-restricted C++ kernel from a validated Python reference."""
    return generate_cpp_kernel(
        artifact_root=artifact_root,
        implementation_id=implementation_id,
        implementation_manifest=implementation_manifest,
        template_id=template_id,
    )


def math_compile_kernel(
    *,
    artifact_root: str | Path,
    kernel_id: str | None = None,
    kernel_manifest: Mapping[str, Any] | None = None,
    compiler: str | None = None,
    timeout_seconds: float = 30.0,
) -> ApplicationResult:
    """Compile a generated C++ kernel in an isolated artifact build directory."""
    return compile_cpp_kernel(
        artifact_root=artifact_root,
        kernel_id=kernel_id,
        kernel_manifest=kernel_manifest,
        compiler=compiler,
        timeout_seconds=timeout_seconds,
    )


def math_package_method_artifact(
    *,
    artifact_root: str | Path,
    implementation_id: str | None = None,
    implementation_manifest: Mapping[str, Any] | None = None,
    validation_report_id: str | None = None,
    validation_report: Mapping[str, Any] | None = None,
    cxx_kernel_id: str | None = None,
    cxx_kernel_manifest: Mapping[str, Any] | None = None,
    artifact_store: ResearchArtifactStore | None = None,
) -> ApplicationResult:
    """Package a validated Python method implementation for strategy handoff."""
    return package_method_artifact(
        artifact_root=artifact_root,
        implementation_id=implementation_id,
        implementation_manifest=implementation_manifest,
        validation_report_id=validation_report_id,
        validation_report=validation_report,
        cxx_kernel_id=cxx_kernel_id,
        cxx_kernel_manifest=cxx_kernel_manifest,
        artifact_store=artifact_store,
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


def _method_card_ids_match_requested_method(
    method_card_ids: tuple[str, ...],
    *,
    method_id: str,
    approved_card_reader: ApprovedMethodCardReader,
) -> bool:
    for card_id in method_card_ids:
        card = approved_card_reader.get_method_card(card_id)
        if card is not None and card.method_id == method_id:
            return True
    return False
