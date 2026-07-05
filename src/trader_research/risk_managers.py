"""Risk-manager candidate schemas and maintained template catalog services.

The risk-manager catalog is a source-generation surface for portfolio research.
Generated candidates implement the platform `trader.risk.RiskManager` interface,
but remain backtest-only and validation-deferred until later strategy/risk stack
tools approve them for portfolio backtests.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import math
from pathlib import Path
import textwrap
from typing import Any, Mapping, Sequence

from .contracts import ArtifactReference, SideEffect, ToolEnvelope, error_envelope, success_envelope, write_json_artifact
from .domain import (
    METHOD_PACKAGE_MANIFEST,
    RISK_MANAGER_CANDIDATE,
    RISK_MANAGER_IMPLEMENTATION,
    ResearchIssue,
    RiskManagerCandidateManifest,
    RiskManagerCandidateSourceRef,
    StrategyCandidateArtifactLink,
    stable_research_id,
)
from .method_implementations.io import file_sha256
from .method_implementations.manifest import INDICATOR_RUNTIME_CONTRACT, SIGNAL_RUNTIME_CONTRACT
from .method_packages import MethodPackageManifest, method_package_path


RESEARCH_LIST_RISK_MANAGER_TEMPLATES = "research_list_risk_manager_templates"
RESEARCH_CREATE_RISK_MANAGER_CANDIDATE = "research_create_risk_manager_candidate"
RISK_MANAGER_RUNTIME_CONTRACT = "trader.risk.RiskManager"
SUPPORTED_RISK_MANAGER_FAMILIES = (
    "gross_exposure_cap",
    "per_symbol_exposure_cap",
    "concentration_cap",
    "drawdown_guard",
    "var_cvar_limit",
)
FORBIDDEN_EXECUTION_TRUE_FLAGS = frozenset(
    {"broker_mutation_allowed", "live_trading_allowed", "raw_sql_allowed"}
)
_SUPPORTED_METHOD_PACKAGE_CONTRACTS = frozenset({INDICATOR_RUNTIME_CONTRACT, SIGNAL_RUNTIME_CONTRACT})


@dataclass(frozen=True)
class RiskManagerTemplateParameter:
    """JSON-safe parameter contract for a maintained risk-manager template.

    Attributes:
        name: Stable parameter name expected by the candidate builder.
        value_type: Human-readable JSON value type.
        description: Caller-facing explanation of how the parameter is used.
        required: Whether a candidate must provide the value explicitly.
        default: Optional default used when the caller omits the parameter.
        constraints: JSON-compatible validation hints for candidate construction.
    """

    name: str
    value_type: str
    description: str
    required: bool = False
    default: Any | None = None
    constraints: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate parameter identity and type labels before catalog publication."""
        if not self.name.strip():
            raise ValueError("risk-manager template parameter name is required")
        if not self.value_type.strip():
            raise ValueError("risk-manager template parameter value_type is required")
        if not self.description.strip():
            raise ValueError("risk-manager template parameter description is required")

    def to_dict(self) -> dict[str, Any]:
        """Serialize the parameter contract into the catalog payload."""
        payload: dict[str, Any] = {
            "name": self.name,
            "value_type": self.value_type,
            "description": self.description,
            "required": self.required,
            "constraints": _jsonable(self.constraints),
        }
        if not self.required or self.default is not None:
            payload["default"] = _jsonable(self.default)
        return payload


@dataclass(frozen=True)
class RiskManagerTemplate:
    """Maintained risk-manager generation target exposed to supervisors.

    Attributes:
        template_family: Stable risk-manager template identifier.
        display_name: Human-readable risk-manager template name.
        description: Brief explanation of the intended risk policy.
        parameters: Parameter contracts in deterministic output order.
        method_package_roles: Optional method-package roles for sourced risk measures.
        policy_intent: Declarative policy behavior for later validation/backtests.
        execution_assumptions: Execution boundary defaults.
        validation_requirements: Deferred checks required before portfolio backtests.
        source_generator: Service path that generates candidate source.
        runtime_contract: Runtime interface generated candidates must implement.
        constraints: Additional template-level validation hints.
    """

    template_family: str
    display_name: str
    description: str
    parameters: tuple[RiskManagerTemplateParameter, ...]
    method_package_roles: tuple[Mapping[str, Any], ...]
    policy_intent: Mapping[str, Any]
    execution_assumptions: Mapping[str, Any]
    validation_requirements: Mapping[str, Any]
    source_generator: str = "trader_research.risk_managers:create_risk_manager_candidate"
    runtime_contract: str = RISK_MANAGER_RUNTIME_CONTRACT
    constraints: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate stable template identifiers and catalog parameter uniqueness."""
        if self.template_family not in SUPPORTED_RISK_MANAGER_FAMILIES:
            raise ValueError(f"unsupported risk-manager template family: {self.template_family}")
        if not self.display_name.strip():
            raise ValueError("risk-manager template display_name is required")
        parameter_names = [parameter.name for parameter in self.parameters]
        if len(parameter_names) != len(set(parameter_names)):
            raise ValueError(f"duplicate parameter names for risk-manager template: {self.template_family}")

    def to_dict(self) -> dict[str, Any]:
        """Serialize maintained template metadata for tool envelopes and docs."""
        return {
            "template_family": self.template_family,
            "display_name": self.display_name,
            "description": self.description,
            "runtime_contract": self.runtime_contract,
            "source_generator": self.source_generator,
            "parameters": [parameter.to_dict() for parameter in self.parameters],
            "method_package_roles": _jsonable(self.method_package_roles),
            "policy_intent": _jsonable(self.policy_intent),
            "execution_assumptions": _jsonable(self.execution_assumptions),
            "validation_requirements": _jsonable(self.validation_requirements),
            "constraints": _jsonable(self.constraints),
        }


@dataclass(frozen=True)
class _ResolvedMethodPackage:
    """Validated package reference attached to one risk-measure role."""

    role: str
    manifest: MethodPackageManifest
    path: Path | None = None


def list_risk_manager_templates(*, families: Sequence[str] | None = None) -> ToolEnvelope:
    """Return maintained risk-manager generation templates.

    Args:
        families: Optional risk-manager family filter. Family names are normalized
            by trimming whitespace, lowercasing, and converting hyphens to
            underscores.

    Returns:
        Read-only `ToolEnvelope` containing deterministic template metadata.
        Unknown or empty requested families return a failed envelope.
    """
    try:
        requested_families = _normalize_requested_families(families)
        templates = [get_risk_manager_template(family) for family in requested_families]
    except ValueError as exc:
        return error_envelope(
            command=RESEARCH_LIST_RISK_MANAGER_TEMPLATES,
            side_effect=SideEffect.READ_ONLY,
            code="unsupported_risk_manager_template",
            message=str(exc),
            data={"supported_risk_manager_families": list(SUPPORTED_RISK_MANAGER_FAMILIES)},
        )

    return success_envelope(
        command=RESEARCH_LIST_RISK_MANAGER_TEMPLATES,
        side_effect=SideEffect.READ_ONLY,
        data={
            "templates": [template.to_dict() for template in templates],
            "template_count": len(templates),
            "supported_risk_manager_families": list(SUPPORTED_RISK_MANAGER_FAMILIES),
        },
    )


def create_risk_manager_candidate(
    *,
    artifact_root: str | Path,
    template_family: str,
    parameters: Mapping[str, Any] | None = None,
    method_package_refs: Sequence[Mapping[str, Any]] | None = None,
    execution_assumptions: Mapping[str, Any] | None = None,
) -> ToolEnvelope:
    """Build and persist one bounded source-backed risk-manager candidate.

    Args:
        artifact_root: Root directory for local research artifacts.
        template_family: Maintained template family from the risk-manager catalog.
        parameters: Optional scalar template parameter values.
        method_package_refs: Optional role-bound refs to validated
            `method_package_manifest` artifacts for risk-measure inputs. Each ref
            must include `role` plus exactly one of `package_id`, `path`, or
            `package_manifest`.
        execution_assumptions: Optional execution-boundary assumptions.

    Returns:
        Standard local-mutating envelope. Invalid inputs fail closed without
        writing a candidate artifact.
    """
    try:
        template = get_risk_manager_template(template_family)
    except ValueError as exc:
        return error_envelope(
            command=RESEARCH_CREATE_RISK_MANAGER_CANDIDATE,
            side_effect=SideEffect.LOCAL_MUTATING,
            code="unsupported_risk_manager_template",
            message=str(exc),
            data={"supported_risk_manager_families": list(SUPPORTED_RISK_MANAGER_FAMILIES)},
        )

    blockers: list[str] = []
    warnings = [
        "Risk-manager candidate source implements trader.risk.RiskManager, but policy validation and portfolio "
        "backtest use are deferred to later strategy/risk stack tasks."
    ]
    normalized_parameters = _normalize_candidate_parameters(template=template, parameters=parameters, blockers=blockers)
    resolved_packages = _resolve_method_package_refs(
        artifact_root=artifact_root,
        refs=method_package_refs or (),
        blockers=blockers,
    )
    ordered_packages = _validate_method_package_roles(template, resolved_packages, blockers)
    normalized_execution_assumptions = _normalize_execution_assumptions(
        template=template,
        execution_assumptions=execution_assumptions,
        blockers=blockers,
    )

    if blockers:
        return _risk_manager_candidate_error(blockers=blockers, warnings=warnings, template=template)

    method_package_links = tuple(_method_package_link(item) for item in ordered_packages)
    candidate_id = _candidate_id(
        template=template,
        parameters=normalized_parameters,
        method_packages=ordered_packages,
        execution_assumptions=normalized_execution_assumptions,
    )
    risk_manager_source = _write_risk_manager_source(
        artifact_root=artifact_root,
        candidate_id=candidate_id,
        template=template,
        parameters=normalized_parameters,
        method_package_refs=method_package_links,
    )
    manifest = RiskManagerCandidateManifest(
        candidate_id=candidate_id,
        template_family=template.template_family,
        method_package_refs=method_package_links,
        risk_manager_source=risk_manager_source,
        parameters=normalized_parameters,
        policy_intent=template.policy_intent,
        execution_assumptions=normalized_execution_assumptions,
        validation_requirements=template.validation_requirements,
        warnings=tuple(ResearchIssue(code="risk_manager_candidate_warning", message=message) for message in warnings),
    )
    manifest_path = write_json_artifact(manifest.to_dict(), risk_manager_candidate_path(artifact_root, candidate_id))
    return success_envelope(
        command=RESEARCH_CREATE_RISK_MANAGER_CANDIDATE,
        side_effect=SideEffect.LOCAL_MUTATING,
        data={"risk_manager_candidate_manifest": manifest.to_dict()},
        artifacts={
            "risk_manager_candidate": ArtifactReference(
                artifact_type=RISK_MANAGER_CANDIDATE,
                path=manifest_path,
                metadata={"id": manifest.candidate_id},
            ).to_dict(),
            "risk_manager_source": ArtifactReference(
                artifact_type=RISK_MANAGER_IMPLEMENTATION,
                path=risk_manager_source.path,
                metadata={
                    "class_name": risk_manager_source.class_name,
                    "factory_name": risk_manager_source.factory_name,
                    "id": risk_manager_source.artifact_id,
                    "runtime_contract": risk_manager_source.runtime_contract,
                    "sha256": risk_manager_source.source_hash,
                },
            ).to_dict(),
        },
        warnings=tuple(warnings),
    )


def risk_manager_candidate_path(artifact_root: str | Path, candidate_id: str) -> Path:
    """Return the deterministic local path for one risk-manager candidate manifest.

    Args:
        artifact_root: Root directory for local research artifacts.
        candidate_id: Stable risk-manager candidate identifier.

    Returns:
        Path where the candidate manifest is persisted.
    """
    return Path(artifact_root) / "risk_managers" / "manifests" / f"{candidate_id}.json"


def risk_manager_candidate_source_path(artifact_root: str | Path, candidate_id: str) -> Path:
    """Return the deterministic local source path for one generated risk-manager module.

    Args:
        artifact_root: Root directory for local research artifacts.
        candidate_id: Stable risk-manager candidate identifier.

    Returns:
        Path where the generated source file is persisted.
    """
    return Path(artifact_root) / "risk_managers" / "source" / f"{candidate_id}.py"


def get_risk_manager_template(family: str) -> RiskManagerTemplate:
    """Return one maintained risk-manager template by normalized family name.

    Args:
        family: Risk-manager family value supplied by a caller or suite config.

    Returns:
        Matching `RiskManagerTemplate`.

    Raises:
        ValueError: If the family is empty or unsupported.
    """
    normalized = normalize_risk_manager_family(family)
    return _TEMPLATE_BY_FAMILY[normalized]


def normalize_risk_manager_family(value: str) -> str:
    """Normalize and validate a maintained risk-manager family identifier.

    Args:
        value: Raw family text from a request or config file.

    Returns:
        Canonical family name.

    Raises:
        ValueError: If the normalized family is not cataloged.
    """
    family = str(value).strip().lower().replace("-", "_")
    if family not in SUPPORTED_RISK_MANAGER_FAMILIES:
        raise ValueError(f"Unsupported risk-manager family: {value}")
    return family


def _normalize_requested_families(families: Sequence[str] | None) -> tuple[str, ...]:
    if families is None:
        return SUPPORTED_RISK_MANAGER_FAMILIES
    normalized: list[str] = []
    for family in families:
        normalized_family = normalize_risk_manager_family(family)
        if normalized_family not in normalized:
            normalized.append(normalized_family)
    if not normalized:
        raise ValueError("At least one risk-manager family is required")
    return tuple(normalized)


def _normalize_candidate_parameters(
    *,
    template: RiskManagerTemplate,
    parameters: Mapping[str, Any] | None,
    blockers: list[str],
) -> dict[str, Any]:
    raw_parameters = _optional_mapping(parameters, "parameters", blockers)
    parameter_by_name = {parameter.name: parameter for parameter in template.parameters}
    normalized: dict[str, Any] = {}

    for name in sorted(set(raw_parameters).difference(parameter_by_name)):
        blockers.append(f"unknown risk-manager template parameter: {name}")
    for name, value in raw_parameters.items():
        if isinstance(value, Mapping) or (
            isinstance(value, Sequence) and not isinstance(value, (str, bytes))
        ):
            blockers.append(f"{name} must be a single scalar value, not a parameter grid")

    for parameter in template.parameters:
        value = _candidate_parameter_value(parameter=parameter, raw_parameters=raw_parameters, blockers=blockers)
        if value is not None or parameter.required:
            normalized[parameter.name] = value

    _validate_parameter_constraints(template, normalized, blockers)
    return normalized


def _candidate_parameter_value(
    *,
    parameter: RiskManagerTemplateParameter,
    raw_parameters: Mapping[str, Any],
    blockers: list[str],
) -> Any:
    if parameter.name in raw_parameters:
        return _coerce_parameter_value(parameter, raw_parameters[parameter.name], blockers)
    if parameter.default is not None:
        return parameter.default
    if parameter.required:
        blockers.append(f"required risk-manager template parameter is missing: {parameter.name}")
    return None


def _coerce_parameter_value(
    parameter: RiskManagerTemplateParameter,
    value: Any,
    blockers: list[str],
) -> Any:
    if parameter.value_type == "integer":
        return _coerce_integer_or_block(value, field_name=f"parameters.{parameter.name}", blockers=blockers)
    if parameter.value_type == "number":
        return _coerce_number_or_block(value, field_name=f"parameters.{parameter.name}", blockers=blockers)
    if parameter.value_type == "boolean":
        if isinstance(value, bool):
            return value
        blockers.append(f"parameters.{parameter.name} must be a boolean")
        return None
    if parameter.value_type == "string":
        if isinstance(value, str) and value.strip():
            return value.strip()
        blockers.append(f"parameters.{parameter.name} must be a non-empty string")
        return None
    return _jsonable(value)


def _validate_parameter_constraints(
    template: RiskManagerTemplate,
    parameters: Mapping[str, Any],
    blockers: list[str],
) -> None:
    for parameter in template.parameters:
        value = parameters.get(parameter.name)
        constraints = parameter.constraints
        numeric_value = _numeric_value(value)
        if "minimum" in constraints and numeric_value is not None:
            if numeric_value < float(constraints["minimum"]):
                blockers.append(f"{parameter.name} must be >= {constraints['minimum']}")
        if "exclusive_minimum" in constraints and numeric_value is not None:
            if numeric_value <= float(constraints["exclusive_minimum"]):
                blockers.append(f"{parameter.name} must be > {constraints['exclusive_minimum']}")
        if "maximum" in constraints and numeric_value is not None:
            if numeric_value > float(constraints["maximum"]):
                blockers.append(f"{parameter.name} must be <= {constraints['maximum']}")
        if "must_be_at_least" in constraints:
            other_name = str(constraints["must_be_at_least"])
            other_value = _numeric_value(parameters.get(other_name))
            if numeric_value is not None and other_value is not None and numeric_value < other_value:
                blockers.append(f"{parameter.name} must be at least {other_name}")


def _resolve_method_package_refs(
    *,
    artifact_root: str | Path,
    refs: Sequence[Mapping[str, Any]],
    blockers: list[str],
) -> tuple[_ResolvedMethodPackage, ...]:
    if isinstance(refs, Mapping) or isinstance(refs, (str, bytes)):
        blockers.append("method_package_refs must be a sequence of role-bound refs")
        return ()

    resolved: list[_ResolvedMethodPackage] = []
    for index, ref in enumerate(refs):
        if not isinstance(ref, Mapping):
            blockers.append(f"method_package_refs[{index}] must be a mapping")
            continue
        role = str(ref.get("role") or "").strip()
        if not role:
            blockers.append(f"method_package_refs[{index}].role is required")
            continue
        source_keys = [key for key in ("package_id", "path", "package_manifest") if ref.get(key) is not None]
        if len(source_keys) != 1:
            blockers.append(
                f"method_package_refs[{index}] must provide exactly one of package_id, path, or package_manifest"
            )
            continue
        try:
            package, package_path = _load_method_package_ref(artifact_root=artifact_root, ref=ref)
        except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
            blockers.append(f"method_package_refs[{index}] could not be resolved: {exc}")
            continue
        resolved.append(_ResolvedMethodPackage(role=role, manifest=package, path=package_path))
    return tuple(resolved)


def _load_method_package_ref(
    *,
    artifact_root: str | Path,
    ref: Mapping[str, Any],
) -> tuple[MethodPackageManifest, Path | None]:
    if ref.get("package_manifest") is not None:
        payload = ref["package_manifest"]
        if not isinstance(payload, Mapping):
            raise ValueError("package_manifest must be a mapping")
        return _method_package_from_payload(payload), None

    if ref.get("package_id") is not None:
        package_id = str(ref.get("package_id") or "").strip()
        if not package_id:
            raise ValueError("package_id is required")
        path = method_package_path(artifact_root, package_id)
        return _method_package_from_path(path), path

    path_value = str(ref.get("path") or "").strip()
    if not path_value:
        raise ValueError("path is required")
    path = Path(path_value)
    return _method_package_from_path(path), path


def _method_package_from_path(path: Path) -> MethodPackageManifest:
    if not path.exists():
        raise FileNotFoundError(f"method package manifest not found: {path}")
    return _method_package_from_payload(json.loads(path.read_text(encoding="utf-8")))


def _method_package_from_payload(payload: Mapping[str, Any]) -> MethodPackageManifest:
    artifact_type = str(payload.get("artifact_type") or "")
    if artifact_type == "method_implementation_manifest":
        raise ValueError("raw method_implementation_manifest inputs are not accepted; provide method_package_manifest")
    return MethodPackageManifest.from_dict(payload)


def _validate_method_package_roles(
    template: RiskManagerTemplate,
    resolved_packages: Sequence[_ResolvedMethodPackage],
    blockers: list[str],
) -> tuple[_ResolvedMethodPackage, ...]:
    role_by_name = {str(item.get("role") or ""): item for item in template.method_package_roles}
    packages_by_role: dict[str, _ResolvedMethodPackage] = {}
    for item in resolved_packages:
        if item.role not in role_by_name:
            blockers.append(f"unknown method package role for {template.template_family}: {item.role}")
            continue
        if item.role in packages_by_role:
            blockers.append(f"duplicate method package role: {item.role}")
            continue
        packages_by_role[item.role] = item
        blockers.extend(_method_package_blockers(item, role_by_name[item.role]))

    for role, spec in role_by_name.items():
        if bool(spec.get("required")) and role not in packages_by_role:
            blockers.append(f"missing required method package role: {role}")
    return tuple(packages_by_role[role] for role in role_by_name if role in packages_by_role)


def _method_package_blockers(
    resolved_package: _ResolvedMethodPackage,
    role_spec: Mapping[str, Any],
) -> list[str]:
    package = resolved_package.manifest
    role = resolved_package.role
    blockers: list[str] = []
    if package.artifact_type != METHOD_PACKAGE_MANIFEST:
        blockers.append(f"{role} must reference artifact_type={METHOD_PACKAGE_MANIFEST}")
    if package.status != "validated":
        blockers.append(f"{role} package must have status=validated")
    if package.blockers:
        blockers.append(f"{role} package blockers must be empty")
    if not package.method_card_ids:
        blockers.append(f"{role} package must include approved method-card refs")
    accepted_contracts = tuple(
        str(item) for item in _sequence(role_spec.get("accepted_runtime_contracts"))
    ) or tuple(sorted(_SUPPORTED_METHOD_PACKAGE_CONTRACTS))
    if package.runtime_contract not in accepted_contracts:
        blockers.append(f"{role} package runtime_contract must be one of {list(accepted_contracts)}")
    if package.runtime_contract not in _SUPPORTED_METHOD_PACKAGE_CONTRACTS:
        blockers.append(f"{role} package runtime_contract is not supported for risk-manager candidates")
    if not package.package_id:
        blockers.append(f"{role} package_id is required")
    if not package.method_id:
        blockers.append(f"{role} method_id is required")
    if not package.source_hash:
        blockers.append(f"{role} source_hash is required")
    return blockers


def _normalize_execution_assumptions(
    *,
    template: RiskManagerTemplate,
    execution_assumptions: Mapping[str, Any] | None,
    blockers: list[str],
) -> dict[str, Any]:
    raw_assumptions = _optional_mapping(execution_assumptions, "execution_assumptions", blockers)
    normalized = dict(template.execution_assumptions)
    normalized.update(
        {
            "backtest_only": True,
            "broker_mutation_allowed": False,
            "live_trading_allowed": False,
            "raw_sql_allowed": False,
            "runtime_instantiation": "deferred_to_risk_manager_candidate_validation",
        }
    )
    normalized.update(raw_assumptions)
    if normalized.get("backtest_only") is not True:
        blockers.append("execution_assumptions.backtest_only must remain true")
    for flag in sorted(FORBIDDEN_EXECUTION_TRUE_FLAGS):
        if _truthy(normalized.get(flag)):
            blockers.append(f"execution_assumptions.{flag} must remain false")
    return dict(_jsonable(normalized))


def _candidate_id(
    *,
    template: RiskManagerTemplate,
    parameters: Mapping[str, Any],
    method_packages: Sequence[_ResolvedMethodPackage],
    execution_assumptions: Mapping[str, Any],
) -> str:
    return stable_research_id(
        "risk_manager_candidate",
        {
            "execution_assumptions": execution_assumptions,
            "method_packages": [
                {
                    "package_id": item.manifest.package_id,
                    "role": item.role,
                    "source_hash": item.manifest.source_hash,
                }
                for item in method_packages
            ],
            "parameters": parameters,
            "template_family": template.template_family,
        },
    )


def _method_package_link(resolved_package: _ResolvedMethodPackage) -> StrategyCandidateArtifactLink:
    package = resolved_package.manifest
    return StrategyCandidateArtifactLink(
        artifact_id=package.package_id,
        artifact_type=METHOD_PACKAGE_MANIFEST,
        role=resolved_package.role,
        path=str(resolved_package.path) if resolved_package.path is not None else None,
        agent_owner="Quantitative Methods Agent",
        status=package.status,
        metadata={
            "entrypoint": package.entrypoint,
            "implementation_id": package.implementation_id,
            "method_id": package.method_id,
            "package_id": package.package_id,
            "runtime_contract": package.runtime_contract,
            "source_hash": package.source_hash,
            "validation_report_ref": package.validation_report_ref,
        },
    )


def _write_risk_manager_source(
    *,
    artifact_root: str | Path,
    candidate_id: str,
    template: RiskManagerTemplate,
    parameters: Mapping[str, Any],
    method_package_refs: Sequence[StrategyCandidateArtifactLink],
) -> RiskManagerCandidateSourceRef:
    source_path = risk_manager_candidate_source_path(artifact_root, candidate_id)
    source_path.parent.mkdir(parents=True, exist_ok=True)
    class_name = _risk_manager_class_name(template.template_family)
    source_path.write_text(
        _render_risk_manager_source(
            candidate_id=candidate_id,
            class_name=class_name,
            template=template,
            parameters=parameters,
        ),
        encoding="utf-8",
    )
    source_hash = file_sha256(source_path)
    return RiskManagerCandidateSourceRef(
        artifact_id=candidate_id,
        path=str(source_path),
        source_hash=source_hash,
        class_name=class_name,
        metadata={
            "candidate_id": candidate_id,
            "method_package_refs": [item.to_dict() for item in method_package_refs],
            "template_family": template.template_family,
        },
    )


def _render_risk_manager_source(
    *,
    candidate_id: str,
    class_name: str,
    template: RiskManagerTemplate,
    parameters: Mapping[str, Any],
) -> str:
    parameters_json = json.dumps(_jsonable(parameters), sort_keys=True)
    policy_intent_json = json.dumps(_jsonable(template.policy_intent), sort_keys=True)
    parameters_literal = repr(parameters_json)
    policy_intent_literal = repr(policy_intent_json)
    return textwrap.dedent(
        f'''\
        """Generated risk-manager implementation for research candidate {candidate_id}.

        Source reference:
            Generated by trader_research.risk_managers.research_create_risk_manager_candidate.

        Implements:
            trader.risk.RiskManager as a deterministic backtest-only research candidate.

        This module records risk-manager policy intent and bounded parameters. It
        does not mutate brokers, raw SQL, or live risk state. Portfolio backtest
        tooling must validate this candidate before using it in a strategy/risk
        stack.
        """

        from __future__ import annotations

        import json
        from typing import Iterable, Mapping, Sequence

        from trader.risk import RiskContext, RiskManager


        CANDIDATE_ID = "{candidate_id}"
        TEMPLATE_FAMILY = "{template.template_family}"
        RUNTIME_CONTRACT = "{RISK_MANAGER_RUNTIME_CONTRACT}"
        BACKTEST_ONLY = True
        LIVE_TRADING_ALLOWED = False
        _PARAMETERS = json.loads({parameters_literal})
        _POLICY_INTENT = json.loads({policy_intent_literal})


        class {class_name}(RiskManager):
            """Source-backed risk-manager candidate implementing the Trader RiskManager interface."""

            def __init__(self, *, parameters: Mapping[str, object] | None = None) -> None:
                self.parameters = dict(_PARAMETERS)
                if parameters is not None:
                    self.parameters.update(dict(parameters))
                self.policy_intent = dict(_POLICY_INTENT)

            @property
            def candidate_id(self) -> str:
                """Return the stable risk-manager candidate identifier."""
                return CANDIDATE_ID

            @property
            def template_family(self) -> str:
                """Return the maintained risk-manager template family."""
                return TEMPLATE_FAMILY

            def validate(
                self,
                orders: Iterable[Mapping[str, object]],
                context: RiskContext,
            ) -> Sequence[Mapping[str, object]]:
                """Return candidate orders unchanged until later policy validation adds enforcement."""
                del context
                return list(orders)

            def evaluate(
                self,
                orders: Iterable[Mapping[str, object]],
                context: RiskContext,
            ) -> tuple[Sequence[Mapping[str, object]], Sequence[Mapping[str, object]]]:
                """Approve all orders while preserving the platform risk-manager split contract."""
                del context
                return list(orders), []


        def build_risk_manager(
            *,
            parameters: Mapping[str, object] | None = None,
        ) -> RiskManager:
            """Instantiate the generated risk-manager candidate for backtest validation."""
            return {class_name}(parameters=parameters)
        '''
    )


def _risk_manager_class_name(template_family: str) -> str:
    return f"{_pascal_case(template_family)}ResearchRiskManager"


def _risk_manager_candidate_error(
    *,
    blockers: Sequence[str],
    warnings: Sequence[str],
    template: RiskManagerTemplate,
) -> ToolEnvelope:
    return error_envelope(
        command=RESEARCH_CREATE_RISK_MANAGER_CANDIDATE,
        side_effect=SideEffect.LOCAL_MUTATING,
        code="invalid_risk_manager_candidate",
        message="Risk-manager candidate construction failed",
        data={
            "blockers": list(blockers),
            "method_package_roles": _jsonable(template.method_package_roles),
            "supported_risk_manager_families": list(SUPPORTED_RISK_MANAGER_FAMILIES),
            "template_family": template.template_family,
            "warnings": list(warnings),
        },
    )


def _optional_mapping(value: Mapping[str, Any] | Any, field_name: str, blockers: list[str]) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return dict(value)
    blockers.append(f"{field_name} must be a mapping")
    return {}


def _coerce_integer_or_block(value: Any, *, field_name: str, blockers: list[str]) -> int | None:
    number = _coerce_number_or_block(value, field_name=field_name, blockers=blockers)
    if number is None:
        return None
    if not float(number).is_integer():
        blockers.append(f"{field_name} must be an integer")
        return None
    return int(number)


def _coerce_number_or_block(value: Any, *, field_name: str, blockers: list[str]) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        blockers.append(f"{field_name} must be numeric")
        return None
    if not math.isfinite(number):
        blockers.append(f"{field_name} must be finite")
        return None
    return number


def _numeric_value(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _truthy(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _sequence(value: object) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return value
    return ()


def _jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _jsonable(val) for key, val in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return value.to_dict()
    return value


def _pascal_case(value: str) -> str:
    parts = [part for part in value.replace("-", "_").split("_") if part]
    return "".join(part[:1].upper() + part[1:] for part in parts) or "Generated"


_OPTIONAL_RISK_MEASURE_ROLE = (
    {
        "role": "risk_measure",
        "required": False,
        "accepted_runtime_contracts": sorted(_SUPPORTED_METHOD_PACKAGE_CONTRACTS),
        "description": "Optional validated method package used to compute supporting risk telemetry.",
    },
)


_TEMPLATES = (
    RiskManagerTemplate(
        template_family="gross_exposure_cap",
        display_name="Gross Exposure Cap",
        description="Generation target for limiting aggregate gross portfolio exposure.",
        parameters=(
            RiskManagerTemplateParameter(
                name="max_gross_exposure",
                value_type="number",
                description="Maximum allowed gross notional exposure in account currency.",
                required=True,
                constraints={"exclusive_minimum": 0.0},
            ),
        ),
        method_package_roles=(),
        policy_intent={
            "risk_dimension": "gross_exposure",
            "order_filter": "reject_orders_that_raise_gross_exposure_above_cap",
        },
        execution_assumptions={
            "telemetry_required": ("gross_exposure",),
            "policy_enforcement": "deferred_to_validation",
        },
        validation_requirements={
            "requires_risk_manager_candidate_validation": True,
            "requires_strategy_risk_stack_validation": True,
            "required_runtime_contract": RISK_MANAGER_RUNTIME_CONTRACT,
        },
    ),
    RiskManagerTemplate(
        template_family="per_symbol_exposure_cap",
        display_name="Per-Symbol Exposure Cap",
        description="Generation target for limiting notional exposure in each traded symbol.",
        parameters=(
            RiskManagerTemplateParameter(
                name="max_symbol_exposure",
                value_type="number",
                description="Maximum absolute notional exposure allowed per symbol.",
                required=True,
                constraints={"exclusive_minimum": 0.0},
            ),
        ),
        method_package_roles=(),
        policy_intent={
            "risk_dimension": "symbol_exposure",
            "order_filter": "reject_orders_that_raise_symbol_exposure_above_cap",
        },
        execution_assumptions={
            "telemetry_required": ("per_symbol_exposure",),
            "policy_enforcement": "deferred_to_validation",
        },
        validation_requirements={
            "requires_risk_manager_candidate_validation": True,
            "requires_strategy_risk_stack_validation": True,
            "required_runtime_contract": RISK_MANAGER_RUNTIME_CONTRACT,
        },
    ),
    RiskManagerTemplate(
        template_family="concentration_cap",
        display_name="Concentration Cap",
        description="Generation target for limiting portfolio concentration in any single symbol.",
        parameters=(
            RiskManagerTemplateParameter(
                name="max_symbol_weight",
                value_type="number",
                description="Maximum fraction of portfolio value allowed in one symbol.",
                required=True,
                constraints={"exclusive_minimum": 0.0, "maximum": 1.0},
            ),
        ),
        method_package_roles=(),
        policy_intent={
            "risk_dimension": "concentration",
            "order_filter": "reject_orders_that_raise_symbol_weight_above_cap",
        },
        execution_assumptions={
            "telemetry_required": ("portfolio_value", "per_symbol_exposure"),
            "policy_enforcement": "deferred_to_validation",
        },
        validation_requirements={
            "requires_risk_manager_candidate_validation": True,
            "requires_strategy_risk_stack_validation": True,
            "required_runtime_contract": RISK_MANAGER_RUNTIME_CONTRACT,
        },
    ),
    RiskManagerTemplate(
        template_family="drawdown_guard",
        display_name="Drawdown Guard",
        description="Generation target for filtering orders when drawdown exceeds a bounded threshold.",
        parameters=(
            RiskManagerTemplateParameter(
                name="max_drawdown_fraction",
                value_type="number",
                description="Maximum tolerated drawdown fraction before new exposure is blocked.",
                required=True,
                constraints={"exclusive_minimum": 0.0, "maximum": 1.0},
            ),
            RiskManagerTemplateParameter(
                name="lookback_period",
                value_type="integer",
                description="Number of portfolio observations used by the drawdown guard.",
                default=252,
                constraints={"minimum": 1},
            ),
        ),
        method_package_roles=_OPTIONAL_RISK_MEASURE_ROLE,
        policy_intent={
            "risk_dimension": "drawdown",
            "order_filter": "reject_new_risk_when_drawdown_exceeds_threshold",
        },
        execution_assumptions={
            "telemetry_required": ("equity_curve", "drawdown"),
            "policy_enforcement": "deferred_to_validation",
        },
        validation_requirements={
            "requires_risk_manager_candidate_validation": True,
            "requires_strategy_risk_stack_validation": True,
            "required_runtime_contract": RISK_MANAGER_RUNTIME_CONTRACT,
        },
    ),
    RiskManagerTemplate(
        template_family="var_cvar_limit",
        display_name="VaR/CVaR Limit",
        description="Generation target for filtering exposure using sourced VaR and CVaR telemetry.",
        parameters=(
            RiskManagerTemplateParameter(
                name="confidence_level",
                value_type="number",
                description="Tail confidence level used by the supplied risk-measure method.",
                default=0.95,
                constraints={"exclusive_minimum": 0.5, "maximum": 0.999},
            ),
            RiskManagerTemplateParameter(
                name="lookback_period",
                value_type="integer",
                description="Number of return observations used by the supplied risk-measure method.",
                default=252,
                constraints={"minimum": 1},
            ),
            RiskManagerTemplateParameter(
                name="max_var_fraction",
                value_type="number",
                description="Maximum tolerated VaR as a fraction of portfolio value.",
                required=True,
                constraints={"exclusive_minimum": 0.0, "maximum": 1.0},
            ),
            RiskManagerTemplateParameter(
                name="max_cvar_fraction",
                value_type="number",
                description="Maximum tolerated CVaR as a fraction of portfolio value.",
                required=True,
                constraints={"exclusive_minimum": 0.0, "maximum": 1.0, "must_be_at_least": "max_var_fraction"},
            ),
        ),
        method_package_roles=_OPTIONAL_RISK_MEASURE_ROLE,
        policy_intent={
            "risk_dimension": "var_cvar",
            "order_filter": "reject_orders_when_var_or_cvar_would_exceed_limits",
        },
        execution_assumptions={
            "telemetry_required": ("portfolio_returns", "var", "cvar"),
            "policy_enforcement": "deferred_to_validation",
        },
        validation_requirements={
            "requires_risk_manager_candidate_validation": True,
            "requires_strategy_risk_stack_validation": True,
            "required_runtime_contract": RISK_MANAGER_RUNTIME_CONTRACT,
        },
    ),
)
_TEMPLATE_BY_FAMILY = {template.template_family: template for template in _TEMPLATES}
