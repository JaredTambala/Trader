"""Strategy candidate schemas and maintained template catalog services.

The strategy catalog is deliberately declarative. It exposes the maintained
strategy families that later candidate-building tools may use, while avoiding
dynamic imports or arbitrary executable strategy code at discovery time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import math
from pathlib import Path
import textwrap
from typing import Any, Mapping, Sequence

from trader_research.contracts import (
    ArtifactReference,
    SideEffect,
    ToolEnvelope,
    error_envelope,
    success_envelope,
    write_json_artifact,
)
from trader_research.artifact_store import ResearchArtifactStore, source_hash
from trader_research.domain import (
    METHOD_CARD,
    METHOD_PACKAGE_MANIFEST,
    QUANTITATIVE_METHODS_OWNER,
    STRATEGY_CANDIDATE,
    STRATEGY_IMPLEMENTATION,
    ResearchIssue,
    StrategyCandidateArtifactLink,
    StrategyCandidateManifest,
    StrategyCandidateRiskAssumption,
    StrategyCandidateSizing,
    StrategyCandidateSourceRef,
    stable_research_id,
)
from trader_research.knowledge.domain import RICH_METHOD_CARD_FORMAT, RichMethodCard
from trader_research.knowledge.method_cards import get_rich_method_card
from trader_research.knowledge.store import KnowledgeStore, KnowledgeStoreError
from trader_research.method_implementations.manifest import SIGNAL_RUNTIME_CONTRACT
from trader_research.methods.packages import MethodPackageManifest, method_package_path


RESEARCH_LIST_STRATEGY_TEMPLATES = "research_list_strategy_templates"
RESEARCH_CREATE_STRATEGY_CANDIDATE = "research_create_strategy_candidate"
SUPPORTED_STRATEGY_FAMILIES = (
    "trend_following",
    "mean_reversion",
    "bollinger_band",
    "cross_sectional_momentum",
    "pairs_mean_reversion",
)
SUPPORTED_PORTFOLIO_MODES = ("single_symbol", "per_symbol_independent", "cross_sectional", "pairs")
STRATEGY_RUNTIME_CONTRACT = "trader.strategies.Strategy"
FORBIDDEN_EXECUTION_TRUE_FLAGS = frozenset(
    {"arbitrary_strategy_code_allowed", "broker_mutation_allowed", "live_trading_allowed"}
)


@dataclass(frozen=True)
class StrategyTemplateParameter:
    """JSON-safe parameter contract for a maintained strategy template.

    Attributes:
        name: Stable parameter name expected by the candidate builder.
        value_type: Human-readable JSON value type.
        description: Caller-facing explanation of how the parameter is used.
        required: Whether a candidate must provide the value explicitly.
        default: Optional default used by the maintained runtime builder.
        constraints: JSON-compatible validation hints for later candidate validation.
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
            raise ValueError("strategy template parameter name is required")
        if not self.value_type.strip():
            raise ValueError("strategy template parameter value_type is required")
        if not self.description.strip():
            raise ValueError("strategy template parameter description is required")

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
class StrategyTemplate:
    """Maintained strategy family metadata exposed to research supervisors.

    Attributes:
        template_family: Stable template identifier used by strategy candidates.
        display_name: Human-readable strategy family name.
        description: Brief explanation of the maintained strategy composition.
        runtime_builder_path: Import path string for the maintained runtime builder.
        runtime_strategy_id: Strategy identifier emitted by the runtime builder.
        parameters: Parameter contracts in deterministic output order.
        required_artifact_types: Artifact types expected before candidate creation.
        required_artifact_roles: Named signal/method package roles required by the family.
        entry_semantics: Declarative entry behavior for candidate manifests.
        exit_semantics: Declarative exit behavior for candidate manifests.
        sizing: Sizing assumptions exposed by the template.
        risk_assumptions: Risk and execution assumptions for v1 candidates.
        backtest_context_requirements: Declarative context that later backtest
            tooling must supply when binding the strategy to market data.
        portfolio_mode: Whether the template is single-symbol, independent per
            symbol, or cross-sectional across a supplied universe.
        rebalance_cadence: Declarative rebalance cadence metadata.
        allocation_bounds: Declarative allocation and position bounds.
        portfolio_state_requirements: Portfolio facts needed by the strategy.
        constraints: Additional validation hints for later candidate tools.
    """

    template_family: str
    display_name: str
    description: str
    runtime_builder_path: str
    runtime_strategy_id: str
    parameters: tuple[StrategyTemplateParameter, ...]
    required_artifact_types: tuple[str, ...]
    required_artifact_roles: tuple[Mapping[str, Any], ...]
    entry_semantics: Mapping[str, Any]
    exit_semantics: Mapping[str, Any]
    sizing: Mapping[str, Any]
    risk_assumptions: Mapping[str, Any]
    backtest_context_requirements: Mapping[str, Any]
    portfolio_mode: str = "per_symbol_independent"
    rebalance_cadence: Mapping[str, Any] = field(default_factory=dict)
    allocation_bounds: Mapping[str, Any] = field(default_factory=dict)
    portfolio_state_requirements: Mapping[str, Any] = field(default_factory=dict)
    constraints: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate stable template identifiers and catalog parameter uniqueness."""
        if self.template_family not in SUPPORTED_STRATEGY_FAMILIES:
            raise ValueError(f"unsupported strategy template family: {self.template_family}")
        if self.portfolio_mode not in SUPPORTED_PORTFOLIO_MODES:
            raise ValueError(f"unsupported strategy portfolio mode: {self.portfolio_mode}")
        if not self.display_name.strip():
            raise ValueError("strategy template display_name is required")
        if not self.runtime_builder_path.strip():
            raise ValueError("strategy template runtime_builder_path is required")
        parameter_names = [parameter.name for parameter in self.parameters]
        if len(parameter_names) != len(set(parameter_names)):
            raise ValueError(f"duplicate parameter names for strategy template: {self.template_family}")

    def to_dict(self) -> dict[str, Any]:
        """Serialize maintained template metadata for tool envelopes and docs."""
        return {
            "template_family": self.template_family,
            "display_name": self.display_name,
            "description": self.description,
            "runtime_builder_path": self.runtime_builder_path,
            "runtime_strategy_id": self.runtime_strategy_id,
            "parameters": [parameter.to_dict() for parameter in self.parameters],
            "required_artifact_types": list(self.required_artifact_types),
            "required_artifact_roles": _jsonable(self.required_artifact_roles),
            "entry_semantics": _jsonable(self.entry_semantics),
            "exit_semantics": _jsonable(self.exit_semantics),
            "sizing": _jsonable(self.sizing),
            "risk_assumptions": _jsonable(self.risk_assumptions),
            "backtest_context_requirements": _jsonable(self.backtest_context_requirements),
            "portfolio_mode": self.portfolio_mode,
            "rebalance_cadence": _jsonable(self.rebalance_cadence),
            "allocation_bounds": _jsonable(self.allocation_bounds),
            "portfolio_state_requirements": _jsonable(self.portfolio_state_requirements),
            "constraints": _jsonable(self.constraints),
        }


@dataclass(frozen=True)
class _ResolvedMethodPackage:
    """Validated package reference attached to one template role."""

    role: str
    manifest: MethodPackageManifest
    path: Path | None = None


def list_strategy_templates(*, families: Sequence[str] | None = None) -> ToolEnvelope:
    """Return maintained strategy templates in a standard research-tool envelope.

    Args:
        families: Optional strategy family filter. Family names are normalized by
            trimming whitespace, lowercasing, and converting hyphens to underscores.

    Returns:
        Read-only `ToolEnvelope` containing deterministic strategy template metadata.
        Unknown or empty requested families return a failed envelope.
    """
    try:
        requested_families = _normalize_requested_families(families)
        templates = [get_strategy_template(family) for family in requested_families]
    except ValueError as exc:
        return error_envelope(
            command=RESEARCH_LIST_STRATEGY_TEMPLATES,
            side_effect=SideEffect.READ_ONLY,
            code="unsupported_strategy_template",
            message=str(exc),
            data={"supported_strategy_families": list(SUPPORTED_STRATEGY_FAMILIES)},
        )

    return success_envelope(
        command=RESEARCH_LIST_STRATEGY_TEMPLATES,
        side_effect=SideEffect.READ_ONLY,
        data={
            "templates": [template.to_dict() for template in templates],
            "template_count": len(templates),
            "supported_strategy_families": list(SUPPORTED_STRATEGY_FAMILIES),
        },
    )


def create_strategy_candidate(
    *,
    artifact_root: str | Path,
    template_family: str,
    method_package_refs: Sequence[Mapping[str, Any]] | None = None,
    rich_method_card_id: str | None = None,
    rich_method_card_uri: str | None = None,
    rich_method_card: Mapping[str, Any] | None = None,
    parameters: Mapping[str, Any] | None = None,
    sizing: Mapping[str, Any] | None = None,
    risk_assumptions: Mapping[str, Any] | None = None,
    execution_assumptions: Mapping[str, Any] | None = None,
    knowledge_store: KnowledgeStore | None = None,
    artifact_store: ResearchArtifactStore | None = None,
) -> ToolEnvelope:
    """Build and persist one bounded source-backed strategy candidate.

    Args:
        artifact_root: Root directory for local research artifacts.
        template_family: Maintained template family from the catalog.
        method_package_refs: Role-bound refs to validated `method_package_manifest`
            artifacts. Each ref must include `role` plus exactly one of
            `package_id`, `path`, or `package_manifest`.
        rich_method_card_id: Optional approved rich method-card ID for
            methodology-backed templates.
        rich_method_card_uri: Optional approved rich method-card URI.
        rich_method_card: Optional inline approved rich method-card payload.
        parameters: Optional scalar template parameter overrides.
        sizing: Optional fixed-quantity sizing assumptions.
        risk_assumptions: Optional JSON-safe risk assumption overrides.
        execution_assumptions: Optional execution-boundary assumptions.

    Returns:
        Standard local-mutating envelope. Invalid inputs fail closed without
        writing a candidate artifact.
    """
    try:
        template = get_strategy_template(template_family)
    except ValueError as exc:
        return error_envelope(
            command=RESEARCH_CREATE_STRATEGY_CANDIDATE,
            side_effect=SideEffect.LOCAL_MUTATING,
            code="unsupported_strategy_template",
            message=str(exc),
            data={"supported_strategy_families": list(SUPPORTED_STRATEGY_FAMILIES)},
        )

    blockers: list[str] = []
    warnings: list[str] = []
    rich_card = _resolve_rich_method_card(
        artifact_root=artifact_root,
        rich_method_card_id=rich_method_card_id,
        rich_method_card_uri=rich_method_card_uri,
        rich_method_card=rich_method_card,
        knowledge_store=knowledge_store,
        blockers=blockers,
    )
    blockers.extend(_rich_methodology_blockers(template, rich_card))
    resolved_packages = _resolve_method_package_refs(
        artifact_root=artifact_root,
        refs=method_package_refs or (),
        allow_empty=not template.required_artifact_roles,
        blockers=blockers,
    )
    ordered_packages = _validate_method_package_roles(template, resolved_packages, blockers)

    sizing_target_override = _sizing_target_override(parameters, sizing, blockers)
    normalized_parameters = _normalize_candidate_parameters(
        template=template,
        parameters=parameters,
        target_qty_override=sizing_target_override,
        blockers=blockers,
    )
    normalized_sizing = _normalize_sizing(
        sizing=sizing,
        target_qty_when_long=normalized_parameters.get("target_qty_when_long"),
        blockers=blockers,
    )
    normalized_risk_assumptions = _normalize_risk_assumptions(
        template=template,
        risk_assumptions=risk_assumptions,
        blockers=blockers,
    )
    normalized_execution_assumptions = _normalize_execution_assumptions(
        template=template,
        execution_assumptions=execution_assumptions,
        blockers=blockers,
    )

    if blockers:
        return _strategy_candidate_error(blockers=blockers, warnings=warnings, template=template)

    method_package_links = tuple(_method_package_link(item) for item in ordered_packages)
    methodology_refs = (
        (_rich_methodology_link(rich_card, knowledge_store=knowledge_store),)
        if rich_card is not None
        else tuple()
    )
    signal_refs = tuple(
        _signal_ref(item) for item in ordered_packages if item.manifest.runtime_contract == SIGNAL_RUNTIME_CONTRACT
    )
    candidate_id = _candidate_id(
        template=template,
        method_packages=ordered_packages,
        methodology_refs=methodology_refs,
        parameters=normalized_parameters,
        sizing=normalized_sizing,
        risk_assumptions=normalized_risk_assumptions,
        execution_assumptions=normalized_execution_assumptions,
    )
    strategy_source = _write_strategy_source(
        artifact_root=artifact_root,
        candidate_id=candidate_id,
        template=template,
        parameters=normalized_parameters,
        sizing=normalized_sizing,
        method_package_refs=method_package_links,
        methodology_refs=methodology_refs,
        artifact_store=artifact_store,
    )
    manifest = StrategyCandidateManifest(
        candidate_id=candidate_id,
        template_family=template.template_family,
        method_package_refs=method_package_links,
        methodology_refs=methodology_refs,
        signal_refs=signal_refs,
        strategy_source=strategy_source,
        parameters=normalized_parameters,
        entry_semantics=template.entry_semantics,
        exit_semantics=template.exit_semantics,
        sizing=normalized_sizing,
        risk_assumptions=normalized_risk_assumptions,
        execution_assumptions=normalized_execution_assumptions,
        warnings=tuple(ResearchIssue(code="strategy_candidate_warning", message=message) for message in warnings),
    )
    manifest_payload = manifest.to_dict()
    if artifact_store is not None:
        manifest_record = artifact_store.save_artifact(
            artifact_type=STRATEGY_CANDIDATE,
            artifact_id=manifest.candidate_id,
            payload=manifest_payload,
            status="candidate",
            source_hash=strategy_source.source_hash,
            metadata={"template_family": manifest.template_family},
        )
        manifest_ref = ArtifactReference(
            artifact_type=STRATEGY_CANDIDATE,
            uri=manifest_record.uri,
            metadata={"id": manifest.candidate_id},
        ).to_dict()
        source_ref = ArtifactReference(
            artifact_type=STRATEGY_IMPLEMENTATION,
            uri=strategy_source.uri,
            metadata={
                "class_name": strategy_source.class_name,
                "factory_name": strategy_source.factory_name,
                "id": strategy_source.artifact_id,
                "runtime_contract": strategy_source.runtime_contract,
                "sha256": strategy_source.source_hash,
            },
        ).to_dict()
    else:
        manifest_path = write_json_artifact(manifest_payload, strategy_candidate_path(artifact_root, manifest.candidate_id))
        manifest_ref = ArtifactReference(
            artifact_type=STRATEGY_CANDIDATE,
            path=manifest_path,
            metadata={"id": manifest.candidate_id},
        ).to_dict()
        source_ref = ArtifactReference(
            artifact_type=STRATEGY_IMPLEMENTATION,
            path=strategy_source.path,
            metadata={
                "class_name": strategy_source.class_name,
                "factory_name": strategy_source.factory_name,
                "id": strategy_source.artifact_id,
                "runtime_contract": strategy_source.runtime_contract,
                "sha256": strategy_source.source_hash,
            },
        ).to_dict()
    return success_envelope(
        command=RESEARCH_CREATE_STRATEGY_CANDIDATE,
        side_effect=SideEffect.LOCAL_MUTATING,
        data={"strategy_candidate_manifest": manifest_payload},
        artifacts={
            "strategy_candidate": manifest_ref,
            "strategy_source": source_ref,
        },
        warnings=tuple(warnings),
    )


def strategy_candidate_path(artifact_root: str | Path, candidate_id: str) -> Path:
    """Return the deterministic local path for one strategy candidate manifest."""
    return Path(artifact_root) / "strategy_candidates" / "manifests" / f"{candidate_id}.json"


def strategy_candidate_source_path(artifact_root: str | Path, candidate_id: str) -> Path:
    """Return the deterministic local source path for one generated strategy module."""
    return Path(artifact_root) / "strategy_candidates" / "source" / f"{candidate_id}.py"


def get_strategy_template(family: str) -> StrategyTemplate:
    """Return one maintained strategy template by normalized family name.

    Args:
        family: Strategy family value supplied by a caller or suite config.

    Returns:
        Matching `StrategyTemplate`.

    Raises:
        ValueError: If the family is empty or unsupported.
    """
    normalized = normalize_strategy_family(family)
    return _TEMPLATE_BY_FAMILY[normalized]


def normalize_strategy_family(value: str) -> str:
    """Normalize and validate a maintained strategy family identifier.

    Args:
        value: Raw family text from a request or config file.

    Returns:
        Canonical family name.

    Raises:
        ValueError: If the normalized family is not cataloged.
    """
    family = str(value).strip().lower().replace("-", "_")
    if family not in SUPPORTED_STRATEGY_FAMILIES:
        raise ValueError(f"Unsupported strategy family: {value}")
    return family


def _normalize_requested_families(families: Sequence[str] | None) -> tuple[str, ...]:
    if families is None:
        return SUPPORTED_STRATEGY_FAMILIES
    normalized: list[str] = []
    for family in families:
        normalized_family = normalize_strategy_family(family)
        if normalized_family not in normalized:
            normalized.append(normalized_family)
    if not normalized:
        raise ValueError("At least one strategy family is required")
    return tuple(normalized)


def _resolve_method_package_refs(
    *,
    artifact_root: str | Path,
    refs: Sequence[Mapping[str, Any]],
    allow_empty: bool = False,
    blockers: list[str],
) -> tuple[_ResolvedMethodPackage, ...]:
    if isinstance(refs, Mapping) or isinstance(refs, (str, bytes)):
        blockers.append("method_package_refs must be a sequence of role-bound refs")
        return ()
    if not refs:
        if allow_empty:
            return ()
        blockers.append("method_package_refs are required")
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
    template: StrategyTemplate,
    resolved_packages: Sequence[_ResolvedMethodPackage],
    blockers: list[str],
) -> tuple[_ResolvedMethodPackage, ...]:
    required_by_role = {str(item.get("role") or ""): item for item in template.required_artifact_roles}
    required_roles = tuple(role for role in required_by_role if role)
    packages_by_role: dict[str, _ResolvedMethodPackage] = {}
    for item in resolved_packages:
        if item.role not in required_by_role:
            blockers.append(f"unknown method package role for {template.template_family}: {item.role}")
            continue
        if item.role in packages_by_role:
            blockers.append(f"duplicate method package role: {item.role}")
            continue
        packages_by_role[item.role] = item
        blockers.extend(_method_package_blockers(item, required_by_role[item.role]))

    for role in required_roles:
        if role not in packages_by_role:
            blockers.append(f"missing required method package role: {role}")
    return tuple(packages_by_role[role] for role in required_roles if role in packages_by_role)


def _resolve_rich_method_card(
    *,
    artifact_root: str | Path,
    rich_method_card_id: str | None,
    rich_method_card_uri: str | None,
    rich_method_card: Mapping[str, Any] | None,
    knowledge_store: KnowledgeStore | None,
    blockers: list[str],
) -> RichMethodCard | None:
    supplied = [bool(rich_method_card_id), bool(rich_method_card_uri), rich_method_card is not None]
    if sum(supplied) > 1:
        blockers.append("provide at most one rich method-card input")
        return None
    if not any(supplied):
        return None
    if rich_method_card is not None:
        payload = rich_method_card
        if payload.get("card_format") != RICH_METHOD_CARD_FORMAT:
            blockers.append("rich_method_card must have card_format=rich_method_card")
            return None
        try:
            card = RichMethodCard.from_dict(payload)
        except ValueError as exc:
            blockers.append(str(exc))
            return None
    else:
        if knowledge_store is None:
            blockers.append("knowledge_store is required to resolve rich method-card refs")
            return None
        card_id = str(rich_method_card_id or "").strip()
        if rich_method_card_uri:
            card_id = _method_card_id_from_uri(rich_method_card_uri)
        try:
            card = get_rich_method_card(
                artifact_root,
                card_id,
                include_drafts=True,
                knowledge_store=knowledge_store,
            )
        except KnowledgeStoreError as exc:
            blockers.append(str(exc))
            return None
        if card is None:
            blockers.append(f"unknown rich method_card_id: {card_id}")
            return None
    if card.status != "approved":
        blockers.append(f"rich method card must be approved: {card.method_card_id}")
    return card


def _method_card_id_from_uri(uri: str) -> str:
    parts = [part for part in str(uri).strip().split("/") if part]
    return parts[-1] if parts else ""


def _rich_methodology_blockers(template: StrategyTemplate, card: RichMethodCard | None) -> list[str]:
    blockers: list[str] = []
    if template.template_family == "pairs_mean_reversion" and card is None:
        return ["pairs_mean_reversion requires an approved rich statistical-arbitrage method card"]
    if card is None:
        return blockers
    if card.family != "statistical_arbitrage" and template.template_family == "pairs_mean_reversion":
        blockers.append("pairs_mean_reversion rich method card family must be statistical_arbitrage")
    if template.template_family != "pairs_mean_reversion":
        return blockers
    blockers.extend(_rich_card_readiness_blockers(card, "strategy_template"))
    required_groups = {
        "spread_or_legs": _has_rich_field(
            card,
            ("extension_fields", "statistical_arbitrage", "spread_definition"),
            ("extension_fields", "statistical_arbitrage", "leg_universe"),
        ),
        "relationship": _has_rich_field(
            card,
            ("extension_fields", "statistical_arbitrage", "cointegration_test"),
            ("extension_fields", "statistical_arbitrage", "stationarity_test"),
            ("extension_fields", "statistical_arbitrage", "hedge_ratio_method"),
        ),
        "entry_logic": _has_rich_field(
            card,
            ("core_fields", "signal_decision_logic", "entry_rules"),
            ("extension_fields", "statistical_arbitrage", "entry_zscore"),
        ),
        "exit_logic": _has_rich_field(
            card,
            ("core_fields", "signal_decision_logic", "exit_rules"),
            ("extension_fields", "statistical_arbitrage", "exit_zscore"),
        ),
        "price_inputs": _has_rich_field(
            card,
            ("core_fields", "data_requirements", "required_inputs"),
            ("core_fields", "data_requirements", "price_fields"),
        ),
    }
    for name, present in required_groups.items():
        if not present:
            blockers.append(f"pairs_mean_reversion rich method card missing required {name} evidence")
    return blockers


def _rich_card_readiness_blockers(card: RichMethodCard, required_level: str) -> list[str]:
    readiness = card.lineage.get("readiness_summary") if isinstance(card.lineage, Mapping) else None
    if not isinstance(readiness, Mapping):
        return [f"rich method card missing {required_level} readiness_summary"]
    level = readiness.get(required_level)
    if not isinstance(level, Mapping):
        return [f"rich method card missing {required_level} readiness"]
    if str(level.get("status") or "") == "passed":
        return []
    missing = ", ".join(str(role) for role in level.get("missing_roles", ()))
    suffix = f"; missing roles: {missing}" if missing else ""
    return [f"rich method card {required_level} readiness must be passed{suffix}"]


def _has_rich_field(card: RichMethodCard, *paths: tuple[str, str, str]) -> bool:
    for scope, group, field_name in paths:
        groups = card.core_fields if scope == "core_fields" else card.extension_fields
        field = groups.get(group, {}).get(field_name)
        if field is not None and field.value is not None and field.evidence_refs:
            return True
    return False


def _method_package_blockers(
    resolved_package: _ResolvedMethodPackage,
    required_role: Mapping[str, Any],
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
    expected_contract = str(required_role.get("runtime_contract") or "")
    if package.runtime_contract != expected_contract:
        blockers.append(f"{role} package runtime_contract must be {expected_contract}")
    if expected_contract != SIGNAL_RUNTIME_CONTRACT:
        blockers.append(f"{role} requires unsupported v1 runtime_contract: {expected_contract}")
    if not package.package_id:
        blockers.append(f"{role} package_id is required")
    if not package.method_id:
        blockers.append(f"{role} method_id is required")
    if not package.source_hash:
        blockers.append(f"{role} source_hash is required")
    return blockers


def _sizing_target_override(
    parameters: Mapping[str, Any] | None,
    sizing: Mapping[str, Any] | None,
    blockers: list[str],
) -> float | None:
    parameter_target = None
    sizing_target = None
    if isinstance(parameters, Mapping) and "target_qty_when_long" in parameters:
        parameter_target = _coerce_number_or_block(
            parameters["target_qty_when_long"],
            field_name="parameters.target_qty_when_long",
            blockers=blockers,
        )
    if isinstance(sizing, Mapping) and "target_qty_when_long" in sizing:
        sizing_target = _coerce_number_or_block(
            sizing["target_qty_when_long"],
            field_name="sizing.target_qty_when_long",
            blockers=blockers,
        )
    if parameter_target is not None and sizing_target is not None and parameter_target != sizing_target:
        blockers.append("target_qty_when_long cannot conflict between parameters and sizing")
    return sizing_target


def _normalize_candidate_parameters(
    *,
    template: StrategyTemplate,
    parameters: Mapping[str, Any] | None,
    target_qty_override: float | None,
    blockers: list[str],
) -> dict[str, Any]:
    raw_parameters = _optional_mapping(parameters, "parameters", blockers)
    parameter_by_name = {parameter.name: parameter for parameter in template.parameters}
    normalized: dict[str, Any] = {}

    for name in sorted(set(raw_parameters).difference(parameter_by_name)):
        blockers.append(f"unknown strategy template parameter: {name}")
    for name, value in raw_parameters.items():
        if isinstance(value, Mapping) or (
            isinstance(value, Sequence) and not isinstance(value, (str, bytes))
        ):
            blockers.append(f"{name} must be a single scalar value, not a parameter grid")

    for parameter in template.parameters:
        value = _candidate_parameter_value(
            parameter=parameter,
            raw_parameters=raw_parameters,
            target_qty_override=target_qty_override,
            blockers=blockers,
        )
        if value is not None or parameter.required:
            normalized[parameter.name] = value

    _validate_parameter_constraints(template, normalized, blockers)
    return normalized


def _candidate_parameter_value(
    *,
    parameter: StrategyTemplateParameter,
    raw_parameters: Mapping[str, Any],
    target_qty_override: float | None,
    blockers: list[str],
) -> Any:
    if parameter.name == "target_qty_when_long" and target_qty_override is not None:
        return target_qty_override
    if parameter.name in raw_parameters:
        return _coerce_parameter_value(parameter, raw_parameters[parameter.name], blockers)
    if parameter.default is not None:
        return parameter.default
    if parameter.required:
        blockers.append(f"required strategy template parameter is missing: {parameter.name}")
    return None


def _coerce_parameter_value(
    parameter: StrategyTemplateParameter,
    value: Any,
    blockers: list[str],
) -> Any:
    if parameter.value_type == "integer":
        return _coerce_integer_or_block(value, field_name=f"parameters.{parameter.name}", blockers=blockers)
    if parameter.value_type == "number":
        return _coerce_number_or_block(value, field_name=f"parameters.{parameter.name}", blockers=blockers)
    if parameter.value_type == "string":
        if isinstance(value, str) and value.strip():
            return value.strip()
        blockers.append(f"parameters.{parameter.name} must be a non-empty string")
        return None
    if parameter.value_type == "array[string]":
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            values = [str(item).strip() for item in value if str(item).strip()]
            if values:
                return values
        blockers.append(f"parameters.{parameter.name} must be a non-empty string array")
        return None
    return _jsonable(value)


def _validate_parameter_constraints(
    template: StrategyTemplate,
    parameters: Mapping[str, Any],
    blockers: list[str],
) -> None:
    for parameter in template.parameters:
        value = parameters.get(parameter.name)
        constraints = parameter.constraints
        if "allowed_values" in constraints and value not in constraints["allowed_values"]:
            blockers.append(f"{parameter.name} must be one of {constraints['allowed_values']}")
        if "min_items" in constraints and isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            if len(value) < int(constraints["min_items"]):
                blockers.append(f"{parameter.name} must contain at least {constraints['min_items']} items")
        if "max_items" in constraints and isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            if len(value) > int(constraints["max_items"]):
                blockers.append(f"{parameter.name} must contain at most {constraints['max_items']} items")
        numeric_value = _numeric_value(value)
        if "minimum" in constraints and numeric_value is not None:
            if numeric_value < float(constraints["minimum"]):
                blockers.append(f"{parameter.name} must be >= {constraints['minimum']}")
        if "maximum" in constraints and numeric_value is not None:
            if numeric_value > float(constraints["maximum"]):
                blockers.append(f"{parameter.name} must be <= {constraints['maximum']}")
        if "must_exceed" in constraints:
            other_name = str(constraints["must_exceed"])
            other_value = _numeric_value(parameters.get(other_name))
            if numeric_value is not None and other_value is not None:
                if numeric_value <= other_value:
                    blockers.append(f"{parameter.name} must exceed {other_name}")


def _normalize_sizing(
    *,
    sizing: Mapping[str, Any] | None,
    target_qty_when_long: Any,
    blockers: list[str],
) -> StrategyCandidateSizing:
    raw_sizing = _optional_mapping(sizing, "sizing", blockers)
    model = str(raw_sizing.get("model") or "fixed_quantity")
    if model != "fixed_quantity":
        blockers.append("v1 strategy candidates require sizing.model=fixed_quantity")
    target_qty = _coerce_number_or_block(
        raw_sizing.get("target_qty_when_long", target_qty_when_long),
        field_name="sizing.target_qty_when_long",
        blockers=blockers,
    )
    max_position_qty = None
    if raw_sizing.get("max_position_qty") is not None:
        max_position_qty = _coerce_number_or_block(
            raw_sizing["max_position_qty"],
            field_name="sizing.max_position_qty",
            blockers=blockers,
        )
    metadata = _optional_mapping(raw_sizing.get("metadata"), "sizing.metadata", blockers)
    try:
        return StrategyCandidateSizing(
            model=model,
            target_qty_when_long=target_qty if target_qty is not None else 1.0,
            max_position_qty=max_position_qty,
            metadata=metadata,
        )
    except ValueError as exc:
        blockers.append(str(exc))
        return StrategyCandidateSizing()


def _normalize_risk_assumptions(
    *,
    template: StrategyTemplate,
    risk_assumptions: Mapping[str, Any] | None,
    blockers: list[str],
) -> tuple[StrategyCandidateRiskAssumption, ...]:
    raw_assumptions = _optional_mapping(risk_assumptions, "risk_assumptions", blockers)
    merged = dict(template.risk_assumptions)
    merged.update(raw_assumptions)
    return tuple(
        StrategyCandidateRiskAssumption(name=name, value=_jsonable(merged[name]))
        for name in sorted(merged)
    )


def _normalize_execution_assumptions(
    *,
    template: StrategyTemplate,
    execution_assumptions: Mapping[str, Any] | None,
    blockers: list[str],
) -> dict[str, Any]:
    raw_assumptions = _optional_mapping(execution_assumptions, "execution_assumptions", blockers)
    normalized = {
        "arbitrary_strategy_code_allowed": False,
        "backtest_execution": "deferred",
        "broker_mutation_allowed": False,
        "dynamic_stop_policy_configuration": False,
        "live_trading_allowed": False,
        "order_type": template.entry_semantics.get("order_type", "market"),
        "position_model": template.entry_semantics.get("position_model", "long_flat"),
        "runtime_instantiation": "deferred_to_strategy_candidate_validation",
    }
    normalized.update(raw_assumptions)
    if normalized.get("order_type") != "market":
        blockers.append("v1 strategy candidates require execution_assumptions.order_type=market")
    for flag in sorted(FORBIDDEN_EXECUTION_TRUE_FLAGS):
        if _truthy(normalized.get(flag)):
            blockers.append(f"execution_assumptions.{flag} must remain false")
    if _truthy(normalized.get("dynamic_stop_policy_configuration")):
        blockers.append("execution_assumptions.dynamic_stop_policy_configuration must remain false")
    return dict(_jsonable(normalized))


def _candidate_id(
    *,
    template: StrategyTemplate,
    method_packages: Sequence[_ResolvedMethodPackage],
    methodology_refs: Sequence[StrategyCandidateArtifactLink],
    parameters: Mapping[str, Any],
    sizing: StrategyCandidateSizing,
    risk_assumptions: Sequence[StrategyCandidateRiskAssumption],
    execution_assumptions: Mapping[str, Any],
) -> str:
    return stable_research_id(
        "strategy_candidate",
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
            "methodology_refs": [item.to_dict() for item in methodology_refs],
            "parameters": parameters,
            "risk_assumptions": [item.to_dict() for item in risk_assumptions],
            "sizing": sizing.to_dict(),
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


def _signal_ref(resolved_package: _ResolvedMethodPackage) -> StrategyCandidateArtifactLink:
    package = resolved_package.manifest
    validation_ref = package.validation_report_ref
    return StrategyCandidateArtifactLink(
        artifact_id=str(validation_ref.get("validation_id") or package.implementation_id),
        artifact_type=str(validation_ref.get("artifact_type") or "signal_implementation_validation_report"),
        role=resolved_package.role,
        path=str(validation_ref.get("path")) if validation_ref.get("path") is not None else None,
        agent_owner="Quantitative Methods Agent",
        status=str(validation_ref.get("status") or "passed"),
        metadata={
            "implementation_id": package.implementation_id,
            "method_id": package.method_id,
            "package_id": package.package_id,
            "runtime_contract": package.runtime_contract,
            "source_hash": package.source_hash,
        },
    )


def _rich_methodology_link(
    card: RichMethodCard,
    *,
    knowledge_store: KnowledgeStore | None,
) -> StrategyCandidateArtifactLink:
    ref = knowledge_store.artifact_reference(METHOD_CARD, card.method_card_id) if knowledge_store is not None else None
    return StrategyCandidateArtifactLink(
        artifact_id=card.method_card_id,
        artifact_type=METHOD_CARD,
        role="methodology",
        uri=ref.uri if ref is not None else None,
        path=str(ref.path) if ref is not None and ref.path is not None else None,
        agent_owner=QUANTITATIVE_METHODS_OWNER,
        status=card.status,
        metadata={
            "card_format": RICH_METHOD_CARD_FORMAT,
            "family": card.family,
            "method_id": card.method_id,
            "method_card_set_id": card.method_card_set_id,
            "revision_number": card.revision_number,
            "supersedes_method_card_id": card.supersedes_method_card_id,
            "source_methodology_candidate_id": card.source_methodology_candidate_id,
            "validation_refs": list(card.validation_refs),
            "readiness_summary": card.lineage.get("readiness_summary") if isinstance(card.lineage, Mapping) else None,
        },
    )


def _write_strategy_source(
    *,
    artifact_root: str | Path,
    candidate_id: str,
    template: StrategyTemplate,
    parameters: Mapping[str, Any],
    sizing: StrategyCandidateSizing,
    method_package_refs: Sequence[StrategyCandidateArtifactLink],
    methodology_refs: Sequence[StrategyCandidateArtifactLink],
    artifact_store: ResearchArtifactStore | None,
) -> StrategyCandidateSourceRef:
    class_name = _strategy_class_name(template.template_family)
    source_code = _render_strategy_source(
        candidate_id=candidate_id,
        class_name=class_name,
        template=template,
        parameters=parameters,
        sizing=sizing,
    )
    generated_hash = source_hash(source_code)
    if artifact_store is not None:
        record = artifact_store.save_artifact(
            artifact_type=STRATEGY_IMPLEMENTATION,
            artifact_id=candidate_id,
            payload={
                "artifact_type": STRATEGY_IMPLEMENTATION,
                "artifact_id": candidate_id,
                "class_name": class_name,
                "factory_name": "build_strategy",
                "runtime_contract": STRATEGY_RUNTIME_CONTRACT,
                "source_code": source_code,
                "source_hash": generated_hash,
                "metadata": {
                    "candidate_id": candidate_id,
                    "allocation_bounds": template.allocation_bounds,
                    "method_package_refs": [item.to_dict() for item in method_package_refs],
                    "methodology_refs": [item.to_dict() for item in methodology_refs],
                    "portfolio_mode": template.portfolio_mode,
                    "portfolio_state_requirements": template.portfolio_state_requirements,
                    "rebalance_cadence": template.rebalance_cadence,
                    "runtime_builder_path": template.runtime_builder_path,
                    "template_family": template.template_family,
                },
            },
            status="generated",
            source_hash=generated_hash,
            metadata={"candidate_id": candidate_id, "template_family": template.template_family},
        )
        return StrategyCandidateSourceRef(
            artifact_id=candidate_id,
            path=None,
            uri=record.uri,
            source_hash=generated_hash,
            class_name=class_name,
            metadata={
                "candidate_id": candidate_id,
                "allocation_bounds": template.allocation_bounds,
                "method_package_refs": [item.to_dict() for item in method_package_refs],
                "methodology_refs": [item.to_dict() for item in methodology_refs],
                "portfolio_mode": template.portfolio_mode,
                "portfolio_state_requirements": template.portfolio_state_requirements,
                "rebalance_cadence": template.rebalance_cadence,
                "runtime_builder_path": template.runtime_builder_path,
                "template_family": template.template_family,
            },
        )
    source_path = strategy_candidate_source_path(artifact_root, candidate_id)
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text(source_code, encoding="utf-8")
    return StrategyCandidateSourceRef(
        artifact_id=candidate_id,
        path=str(source_path),
        source_hash=generated_hash,
        class_name=class_name,
        metadata={
            "candidate_id": candidate_id,
            "allocation_bounds": template.allocation_bounds,
            "method_package_refs": [item.to_dict() for item in method_package_refs],
            "methodology_refs": [item.to_dict() for item in methodology_refs],
            "portfolio_mode": template.portfolio_mode,
            "portfolio_state_requirements": template.portfolio_state_requirements,
            "rebalance_cadence": template.rebalance_cadence,
            "runtime_builder_path": template.runtime_builder_path,
            "template_family": template.template_family,
        },
    )


def _render_strategy_source(
    *,
    candidate_id: str,
    class_name: str,
    template: StrategyTemplate,
    parameters: Mapping[str, Any],
    sizing: StrategyCandidateSizing,
) -> str:
    module_name, function_name = _builder_import_parts(template.runtime_builder_path)
    parameters_json = json.dumps(_jsonable(parameters), sort_keys=True)
    strategy_parameters_literal = repr(parameters_json)
    default_qty = float(sizing.target_qty_when_long)
    return textwrap.dedent(
        f'''\
        """Generated strategy implementation for research candidate {candidate_id}.

        Source reference:
            Generated by trader_research.strategy_candidates.research_create_strategy_candidate.

        Implements:
            trader.strategies.Strategy via a deterministic wrapper around
            {template.runtime_builder_path}.

        This module is a local research artifact. It binds strategy logic and
        strategy parameters only; symbols, asset class, timeframe, and date
        ranges are supplied by validation or backtest tooling.
        """

        from __future__ import annotations

        from datetime import datetime
        import json
        from typing import Mapping, Sequence

        from trader.event_store import EventStore
        from trader.portfolio import Portfolio
        from trader.strategies import Strategy
        from trader.strategy_metadata import StrategyInfo, resolve_strategy_info
        from {module_name} import {function_name} as _build_inner_strategy


        CANDIDATE_ID = "{candidate_id}"
        TEMPLATE_FAMILY = "{template.template_family}"
        RUNTIME_BUILDER_PATH = "{template.runtime_builder_path}"
        _STRATEGY_PARAMETERS = json.loads({strategy_parameters_literal})
        _DEFAULT_TARGET_QTY_WHEN_LONG = {default_qty!r}


        class {class_name}(Strategy):
            """Source-backed strategy candidate implementing the Trader Strategy interface."""

            def __init__(
                self,
                *,
                symbols: Sequence[str],
                asset_class: str,
                timeframe: str,
                target_qty_when_long: float | None = None,
            ) -> None:
                runtime_parameters = dict(_STRATEGY_PARAMETERS)
                runtime_parameters["target_qty_when_long"] = (
                    _DEFAULT_TARGET_QTY_WHEN_LONG
                    if target_qty_when_long is None
                    else float(target_qty_when_long)
                )
                self._inner = _build_inner_strategy(
                    symbols=symbols,
                    asset_class=asset_class,
                    timeframe=timeframe,
                    **runtime_parameters,
                )

            @property
            def strategy_id(self) -> str:
                """Return the stable strategy candidate identifier."""
                return CANDIDATE_ID

            @property
            def strategy_info(self) -> StrategyInfo:
                """Return strategy metadata with candidate-level provenance."""
                inner_info = resolve_strategy_info(self._inner, fallback_id=TEMPLATE_FAMILY)
                parameters = dict(inner_info.parameters)
                parameters.update(_STRATEGY_PARAMETERS)
                parameters["portfolio_mode"] = "{template.portfolio_mode}"
                parameters["candidate_id"] = CANDIDATE_ID
                parameters["runtime_builder_path"] = RUNTIME_BUILDER_PATH
                return StrategyInfo(
                    strategy_id=CANDIDATE_ID,
                    name=TEMPLATE_FAMILY,
                    version="1",
                    description="Generated source-backed research strategy candidate.",
                    parameters=parameters,
                    author="trader_research",
                    source=f"{{self.__class__.__module__}}.{{self.__class__.__qualname__}}",
                )

            def generate_orders(
                self,
                *,
                run_id: str,
                cycle_id: str,
                decision_ts: datetime,
                event_store: EventStore,
                portfolio: Portfolio,
            ) -> Sequence[Mapping[str, object]]:
                """Delegate order generation to the maintained inner strategy."""
                return self._inner.generate_orders(
                    run_id=run_id,
                    cycle_id=cycle_id,
                    decision_ts=decision_ts,
                    event_store=event_store,
                    portfolio=portfolio,
                )

            def generate_orders_for_symbol(
                self,
                symbol: str,
                *,
                run_id: str,
                cycle_id: str,
                decision_ts: datetime,
                event_store: EventStore,
                portfolio: Portfolio,
            ) -> Sequence[Mapping[str, object]]:
                """Delegate per-symbol order generation to the maintained inner strategy."""
                return self._inner.generate_orders_for_symbol(
                    symbol,
                    run_id=run_id,
                    cycle_id=cycle_id,
                    decision_ts=decision_ts,
                    event_store=event_store,
                    portfolio=portfolio,
                )


        def build_strategy(
            *,
            symbols: Sequence[str],
            asset_class: str,
            timeframe: str,
            target_qty_when_long: float | None = None,
        ) -> Strategy:
            """Instantiate the generated strategy candidate for a concrete data context."""
            return {class_name}(
                symbols=symbols,
                asset_class=asset_class,
                timeframe=timeframe,
                target_qty_when_long=target_qty_when_long,
            )
        '''
    )


def _builder_import_parts(runtime_builder_path: str) -> tuple[str, str]:
    if ":" not in runtime_builder_path:
        raise ValueError(f"runtime_builder_path must use module:function syntax: {runtime_builder_path}")
    module_name, function_name = runtime_builder_path.split(":", 1)
    if not module_name or not function_name:
        raise ValueError(f"runtime_builder_path must use module:function syntax: {runtime_builder_path}")
    return module_name, function_name


def _strategy_class_name(template_family: str) -> str:
    return f"{_pascal_case(template_family)}ResearchStrategy"


def _pascal_case(value: str) -> str:
    parts = [part for part in value.replace("-", "_").split("_") if part]
    return "".join(part[:1].upper() + part[1:] for part in parts) or "Generated"


def _strategy_candidate_error(
    *,
    blockers: Sequence[str],
    warnings: Sequence[str],
    template: StrategyTemplate,
) -> ToolEnvelope:
    return error_envelope(
        command=RESEARCH_CREATE_STRATEGY_CANDIDATE,
        side_effect=SideEffect.LOCAL_MUTATING,
        code="invalid_strategy_candidate",
        message="Strategy candidate construction failed",
        data={
            "blockers": list(blockers),
            "required_artifact_roles": _jsonable(template.required_artifact_roles),
            "supported_strategy_families": list(SUPPORTED_STRATEGY_FAMILIES),
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
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        blockers.append(f"{field_name} must be numeric")
        return None
    number = float(value)
    if not math.isfinite(number):
        blockers.append(f"{field_name} must be finite")
        return None
    return number


def _numeric_value(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _truthy(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _shared_parameters() -> tuple[StrategyTemplateParameter, ...]:
    return (
        StrategyTemplateParameter(
            name="target_qty_when_long",
            value_type="number",
            description="Fixed quantity used when the long/flat template opens long exposure.",
            default=1.0,
            constraints={"minimum": 0.0},
        ),
    )


def _entry_semantics(*, signal_roles: Sequence[str], require_all: bool) -> dict[str, Any]:
    return {
        "position_model": "long_flat",
        "direction": "long_only",
        "order_type": "market",
        "signal_roles": list(signal_roles),
        "threshold": 0.0,
        "condition": "all_positive" if require_all else "any_positive",
    }


def _exit_semantics(*, signal_roles: Sequence[str], require_all: bool) -> dict[str, Any]:
    return {
        "position_model": "long_flat",
        "order_type": "market",
        "signal_roles": list(signal_roles),
        "threshold": 0.0,
        "condition": "all_negative" if require_all else "any_negative",
    }


def _required_artifact_roles(*roles: str) -> tuple[Mapping[str, Any], ...]:
    return tuple(
        {
            "role": role,
            "artifact_type": METHOD_PACKAGE_MANIFEST,
            "runtime_contract": "trader.signals.Signal",
            "required": True,
        }
        for role in roles
    )


def _template_constraints(*, shorting_allowed: bool = False) -> dict[str, Any]:
    return {
        "arbitrary_strategy_code_allowed": False,
        "shorting_allowed": shorting_allowed,
        "broker_mutation_allowed": False,
        "dynamic_stop_policy_configuration": False,
    }


def _sizing_contract(*, allows_short: bool = False) -> dict[str, Any]:
    return {
        "model": "fixed_quantity",
        "parameter": "target_qty_when_long",
        "default_target_qty_when_long": 1.0,
        "allows_short": allows_short,
    }


def _risk_assumptions(
    *,
    portfolio_model: str = "single_target_quantity_per_symbol",
    position_direction: str = "long_only",
) -> dict[str, Any]:
    return {
        "position_direction": position_direction,
        "stop_policy": "not_exposed_in_v1_catalog",
        "order_type": "market",
        "portfolio_model": portfolio_model,
    }


def _backtest_context_requirements(*, portfolio_mode: str = "per_symbol_independent") -> dict[str, Any]:
    return {
        "market_data": "event_store_bars",
        "required_backtest_fields": ["symbols", "asset_class", "timeframe", "start", "end"],
        "candidate_fields": [],
        "bar_order": "latest_first",
        "warmup": "max_signal_window",
        "symbol_universe_source": "data_agent_dataset_manifest",
        "portfolio_mode": portfolio_mode,
    }


def _rebalance_cadence(value: str = "every_bar") -> dict[str, Any]:
    return {
        "cadence": value,
        "clock_source": "backtest_data_scope",
        "dates_bound_by_candidate": False,
    }


def _allocation_bounds(
    *,
    max_positions_parameter: str | None = None,
    allows_short: bool = False,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "allows_short": allows_short,
        "min_symbol_weight": -1.0 if allows_short else 0.0,
        "max_symbol_weight": 1.0,
        "target_quantity_parameter": "target_qty_when_long",
    }
    if max_positions_parameter is not None:
        payload["max_positions_parameter"] = max_positions_parameter
    return payload


def _portfolio_state_requirements(*requirements: str) -> dict[str, Any]:
    return {
        "required_state": list(requirements or ("positions_by_symbol",)),
        "state_source": "runtime_portfolio_snapshot",
    }


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


TREND_FOLLOWING_TEMPLATE = StrategyTemplate(
    template_family="trend_following",
    display_name="Trend Following",
    description="Long/flat strategy that opens on EMA or MACD crossover strength and exits on bearish crossover state.",
    runtime_builder_path="trader_standard.strategies:build_trend_following_strategy",
    runtime_strategy_id="trend_following",
    parameters=_shared_parameters()
    + (
        StrategyTemplateParameter(
            name="ema_fast_period",
            value_type="integer",
            description="Fast EMA period for the crossover signal.",
            default=12,
            constraints={"minimum": 1},
        ),
        StrategyTemplateParameter(
            name="ema_slow_period",
            value_type="integer",
            description="Slow EMA period for the crossover signal.",
            default=26,
            constraints={"minimum": 2, "must_exceed": "ema_fast_period"},
        ),
        StrategyTemplateParameter(
            name="macd_fast_period",
            value_type="integer",
            description="Fast EMA period used inside MACD.",
            default=12,
            constraints={"minimum": 1},
        ),
        StrategyTemplateParameter(
            name="macd_slow_period",
            value_type="integer",
            description="Slow EMA period used inside MACD.",
            default=26,
            constraints={"minimum": 2, "must_exceed": "macd_fast_period"},
        ),
        StrategyTemplateParameter(
            name="macd_signal_period",
            value_type="integer",
            description="Signal-line EMA period used inside MACD.",
            default=9,
            constraints={"minimum": 1},
        ),
    ),
    required_artifact_types=(METHOD_PACKAGE_MANIFEST,),
    required_artifact_roles=_required_artifact_roles("ema_crossover_signal", "macd_crossover_signal"),
    entry_semantics=_entry_semantics(signal_roles=("ema_crossover_signal", "macd_crossover_signal"), require_all=False),
    exit_semantics=_exit_semantics(signal_roles=("ema_crossover_signal", "macd_crossover_signal"), require_all=False),
    sizing=_sizing_contract(),
    risk_assumptions=_risk_assumptions(),
    backtest_context_requirements=_backtest_context_requirements(),
    portfolio_mode="per_symbol_independent",
    rebalance_cadence=_rebalance_cadence(),
    allocation_bounds=_allocation_bounds(),
    portfolio_state_requirements=_portfolio_state_requirements("positions_by_symbol"),
    constraints=_template_constraints(),
)

MEAN_REVERSION_TEMPLATE = StrategyTemplate(
    template_family="mean_reversion",
    display_name="Mean Reversion",
    description="Long/flat strategy that enters on oversold RSI plus downside SMA stretch and exits on recovery.",
    runtime_builder_path="trader_standard.strategies:build_mean_reversion_strategy",
    runtime_strategy_id="mean_reversion",
    parameters=_shared_parameters()
    + (
        StrategyTemplateParameter(
            name="rsi_period",
            value_type="integer",
            description="RSI period used for entry and recovery signals.",
            default=14,
            constraints={"minimum": 1},
        ),
        StrategyTemplateParameter(
            name="oversold",
            value_type="number",
            description="RSI threshold below which the entry signal is considered oversold.",
            default=30.0,
            constraints={"minimum": 0.0, "maximum": 100.0},
        ),
        StrategyTemplateParameter(
            name="exit_rsi",
            value_type="number",
            description="RSI threshold used to identify recovery exits.",
            default=50.0,
            constraints={"minimum": 0.0, "maximum": 100.0},
        ),
        StrategyTemplateParameter(
            name="mean_period",
            value_type="integer",
            description="SMA period used for the downside stretch signal.",
            default=20,
            constraints={"minimum": 1},
        ),
        StrategyTemplateParameter(
            name="stretch_pct",
            value_type="number",
            description="Minimum percentage below the SMA required for stretch entry.",
            default=0.02,
            constraints={"minimum": 0.0},
        ),
    ),
    required_artifact_types=(METHOD_PACKAGE_MANIFEST,),
    required_artifact_roles=_required_artifact_roles(
        "rsi_threshold_signal",
        "rsi_recovery_signal",
        "sma_stretch_signal",
    ),
    entry_semantics=_entry_semantics(signal_roles=("rsi_threshold_signal", "sma_stretch_signal"), require_all=True),
    exit_semantics=_exit_semantics(signal_roles=("rsi_recovery_signal", "sma_stretch_signal"), require_all=False),
    sizing=_sizing_contract(),
    risk_assumptions=_risk_assumptions(),
    backtest_context_requirements=_backtest_context_requirements(),
    portfolio_mode="per_symbol_independent",
    rebalance_cadence=_rebalance_cadence(),
    allocation_bounds=_allocation_bounds(),
    portfolio_state_requirements=_portfolio_state_requirements("positions_by_symbol"),
    constraints=_template_constraints(),
)

BOLLINGER_BAND_TEMPLATE = StrategyTemplate(
    template_family="bollinger_band",
    display_name="Bollinger Band",
    description="Long/flat strategy that opens on lower-band re-entry and exits on middle-band reversion.",
    runtime_builder_path="trader_standard.strategies:build_bollinger_band_strategy",
    runtime_strategy_id="bollinger_band",
    parameters=_shared_parameters()
    + (
        StrategyTemplateParameter(
            name="period",
            value_type="integer",
            description="Rolling period used for Bollinger Bands.",
            default=20,
            constraints={"minimum": 1},
        ),
        StrategyTemplateParameter(
            name="stddev_multiplier",
            value_type="number",
            description="Standard-deviation multiplier applied to the rolling band width.",
            default=2.0,
            constraints={"minimum": 0.0},
        ),
    ),
    required_artifact_types=(METHOD_PACKAGE_MANIFEST,),
    required_artifact_roles=_required_artifact_roles("bollinger_band_signal"),
    entry_semantics=_entry_semantics(signal_roles=("bollinger_band_signal",), require_all=True),
    exit_semantics=_exit_semantics(signal_roles=("bollinger_band_signal",), require_all=True),
    sizing=_sizing_contract(),
    risk_assumptions=_risk_assumptions(),
    backtest_context_requirements=_backtest_context_requirements(),
    portfolio_mode="per_symbol_independent",
    rebalance_cadence=_rebalance_cadence(),
    allocation_bounds=_allocation_bounds(),
    portfolio_state_requirements=_portfolio_state_requirements("positions_by_symbol"),
    constraints=_template_constraints(),
)

CROSS_SECTIONAL_MOMENTUM_TEMPLATE = StrategyTemplate(
    template_family="cross_sectional_momentum",
    display_name="Cross-Sectional Momentum",
    description="Ranks the supplied symbol universe by lookback return and allocates long exposure to top symbols.",
    runtime_builder_path="trader_standard.strategies:build_cross_sectional_momentum_strategy",
    runtime_strategy_id="cross_sectional_momentum",
    parameters=_shared_parameters()
    + (
        StrategyTemplateParameter(
            name="lookback_period",
            value_type="integer",
            description="Number of bars used to compute simple lookback return ranks.",
            default=20,
            constraints={"minimum": 1},
        ),
        StrategyTemplateParameter(
            name="top_n",
            value_type="integer",
            description="Maximum number of top-ranked symbols to hold long.",
            default=2,
            constraints={"minimum": 1},
        ),
        StrategyTemplateParameter(
            name="rebalance_cadence",
            value_type="string",
            description="Declarative cadence used by portfolio backtests to interpret rebalance timing.",
            default="every_bar",
            constraints={"allowed_values": ["every_bar", "daily"]},
        ),
    ),
    required_artifact_types=(METHOD_PACKAGE_MANIFEST,),
    required_artifact_roles=_required_artifact_roles("ranking_signal"),
    entry_semantics={
        "position_model": "long_only_top_n",
        "direction": "long_only",
        "order_type": "market",
        "ranking_role": "ranking_signal",
        "rank_order": "descending",
        "selection_parameter": "top_n",
    },
    exit_semantics={
        "position_model": "long_only_top_n",
        "order_type": "market",
        "condition": "drop_out_of_top_n",
    },
    sizing=_sizing_contract(),
    risk_assumptions=_risk_assumptions(portfolio_model="cross_sectional_top_n_equal_quantity"),
    backtest_context_requirements=_backtest_context_requirements(portfolio_mode="cross_sectional"),
    portfolio_mode="cross_sectional",
    rebalance_cadence=_rebalance_cadence(),
    allocation_bounds=_allocation_bounds(max_positions_parameter="top_n"),
    portfolio_state_requirements=_portfolio_state_requirements("positions_by_symbol", "cash_balance"),
    constraints=_template_constraints(),
)

PAIRS_MEAN_REVERSION_TEMPLATE = StrategyTemplate(
    template_family="pairs_mean_reversion",
    display_name="Pairs Mean Reversion",
    description="Long/short paired-asset spread strategy that enters on z-score divergence and exits on reversion.",
    runtime_builder_path="trader_standard.strategies:build_pairs_mean_reversion_strategy",
    runtime_strategy_id="pairs_mean_reversion",
    parameters=_shared_parameters()
    + (
        StrategyTemplateParameter(
            name="lookback_period",
            value_type="integer",
            description="Number of bars used to estimate spread mean and standard deviation.",
            default=60,
            constraints={"minimum": 2},
        ),
        StrategyTemplateParameter(
            name="entry_zscore",
            value_type="number",
            description="Absolute spread z-score at which a pair trade is opened.",
            default=2.0,
            constraints={"minimum": 0.0},
        ),
        StrategyTemplateParameter(
            name="exit_zscore",
            value_type="number",
            description="Absolute spread z-score at or below which an open pair trade is closed.",
            default=0.5,
            constraints={"minimum": 0.0},
        ),
        StrategyTemplateParameter(
            name="hedge_ratio",
            value_type="number",
            description="Fixed hedge ratio applied to the second leg in each deterministic pair.",
            default=1.0,
            constraints={"minimum": 0.000001},
        ),
        StrategyTemplateParameter(
            name="max_pairs",
            value_type="integer",
            description="Maximum number of disjoint sorted symbol pairs traded from the supplied universe.",
            default=1,
            constraints={"minimum": 1},
        ),
        StrategyTemplateParameter(
            name="pair_mode",
            value_type="string",
            description="Deterministic symbol pairing mode.",
            default="disjoint_sorted",
            constraints={"allowed_values": ["disjoint_sorted"]},
        ),
    ),
    required_artifact_types=(),
    required_artifact_roles=(),
    entry_semantics={
        "position_model": "long_short_pairs",
        "direction": "long_short",
        "order_type": "market",
        "spread_signal": "z_score",
        "entry_condition": "abs_zscore_at_or_above_entry_zscore",
        "pair_mode": "disjoint_sorted",
    },
    exit_semantics={
        "position_model": "long_short_pairs",
        "order_type": "market",
        "condition": "abs_zscore_at_or_below_exit_zscore",
    },
    sizing=_sizing_contract(allows_short=True),
    risk_assumptions=_risk_assumptions(
        portfolio_model="long_short_disjoint_pairs_fixed_quantity",
        position_direction="long_short",
    ),
    backtest_context_requirements=_backtest_context_requirements(portfolio_mode="pairs"),
    portfolio_mode="pairs",
    rebalance_cadence=_rebalance_cadence(),
    allocation_bounds=_allocation_bounds(max_positions_parameter="max_pairs", allows_short=True),
    portfolio_state_requirements=_portfolio_state_requirements("positions_by_symbol", "cash_balance"),
    constraints=_template_constraints(shorting_allowed=True),
)

STRATEGY_TEMPLATE_CATALOG = (
    TREND_FOLLOWING_TEMPLATE,
    MEAN_REVERSION_TEMPLATE,
    BOLLINGER_BAND_TEMPLATE,
    CROSS_SECTIONAL_MOMENTUM_TEMPLATE,
    PAIRS_MEAN_REVERSION_TEMPLATE,
)
_TEMPLATE_BY_FAMILY = {template.template_family: template for template in STRATEGY_TEMPLATE_CATALOG}
