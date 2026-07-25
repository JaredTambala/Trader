"""Canonical executable implementation value objects."""

from __future__ import annotations

from trader_research.foundation.artifacts import SCHEMA_VERSION

from collections.abc import Mapping as MappingABC, Sequence as SequenceABC
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from trader_research.foundation import source_hash
from trader_research.foundation import stable_research_id
from trader_research.governance.artifacts import IMPLEMENTATION_VERSION


IMPLEMENTATION_KINDS = frozenset(
    {"indicator", "signal", "strategy", "risk_manager", "optimization_objective"}
)
PREDICTION_CONSUMER_KINDS = frozenset(
    {"directional", "ranking", "regime", "gating", "allocation"}
)
PREDICTION_INFERENCE_SCOPES = frozenset({"per_symbol", "cross_sectional", "portfolio"})
PREDICTION_OUTPUT_SHAPES = frozenset({"scalar", "structured"})
RUNTIME_CONTRACT_BY_KIND = {
    "indicator": "trader.indicators.Indicator",
    "signal": "trader.signals.Signal",
    "strategy": "trader.strategies.Strategy",
    "risk_manager": "trader.risk.RiskManager",
    "optimization_objective": "trader_research.experiments.optimization.OptimizationObjective",
}


@dataclass(frozen=True)
class ImplementationVersion:
    """Immutable DB-backed executable implementation record."""

    implementation_version_id: str
    implementation_kind: str
    name: str
    version: str
    source_code: str
    source_hash: str
    entrypoint: Mapping[str, Any]
    parameter_schema: Mapping[str, Any]
    dependencies: tuple[str, ...] = ()
    authoring_origin: str = "supplied"
    capabilities: tuple[str, ...] = ()
    runtime_requirements: Mapping[str, Any] = field(default_factory=dict)
    resource_bounds: Mapping[str, Any] = field(default_factory=dict)
    provenance_refs: tuple[Mapping[str, Any], ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)
    status: str = "registered"

    def to_dict(self) -> dict[str, Any]:
        """Return the canonical JSON payload."""
        return {
            "artifact_type": IMPLEMENTATION_VERSION,
            "schema_version": SCHEMA_VERSION,
            "implementation_version_id": self.implementation_version_id,
            "implementation_kind": self.implementation_kind,
            "name": self.name,
            "version": self.version,
            "source_code": self.source_code,
            "source_hash": self.source_hash,
            "entrypoint": dict(self.entrypoint),
            "parameter_schema": dict(self.parameter_schema),
            "dependencies": list(self.dependencies),
            "authoring_origin": self.authoring_origin,
            "capabilities": list(self.capabilities),
            "runtime_requirements": dict(self.runtime_requirements),
            "resource_bounds": dict(self.resource_bounds),
            "provenance_refs": [dict(item) for item in self.provenance_refs],
            "metadata": dict(self.metadata),
            "policy": {
                "backtest_only": True,
                "broker_mutation_allowed": False,
                "live_trading_allowed": False,
                "raw_sql_allowed": False,
            },
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ImplementationVersion":
        """Parse and validate a persisted implementation payload."""
        if str(payload.get("artifact_type") or "") != IMPLEMENTATION_VERSION:
            raise ValueError(f"artifact_type must be {IMPLEMENTATION_VERSION}")
        kind = str(payload.get("implementation_kind") or "").strip()
        if kind not in IMPLEMENTATION_KINDS:
            raise ValueError(f"unsupported implementation_kind: {kind}")
        code = str(payload.get("source_code") or "")
        digest = str(payload.get("source_hash") or "")
        if not code or source_hash(code) != digest:
            raise ValueError("implementation source_hash does not match source_code")
        entrypoint = _mapping(payload.get("entrypoint"), "entrypoint")
        if not str(entrypoint.get("factory_name") or "").strip():
            raise ValueError("implementation entrypoint.factory_name is required")
        implementation_id = _required(payload, "implementation_version_id")
        dependencies = _strings(payload.get("dependencies"))
        capabilities = _strings(payload.get("capabilities"))
        runtime_requirements = _normalize_runtime_requirements(
            kind,
            _mapping(payload.get("runtime_requirements") or {}, "runtime_requirements"),
        )
        resource_bounds = _mapping(payload.get("resource_bounds") or {}, "resource_bounds")
        provenance_refs = _mappings(payload.get("provenance_refs"))
        metadata = _mapping(payload.get("metadata") or {}, "metadata")
        identity = _implementation_identity(
            implementation_kind=kind,
            name=_required(payload, "name"),
            version=_required(payload, "version"),
            source_digest=digest,
            entrypoint=entrypoint,
            parameter_schema=_mapping(payload.get("parameter_schema") or {}, "parameter_schema"),
            dependencies=dependencies,
            authoring_origin=str(payload.get("authoring_origin") or "supplied"),
            capabilities=capabilities,
            runtime_requirements=runtime_requirements,
            resource_bounds=resource_bounds,
            provenance_refs=provenance_refs,
            metadata=metadata,
        )
        if stable_research_id("implementation_version", identity) != implementation_id:
            raise ValueError("implementation_version_id does not match canonical implementation content")
        return cls(
            implementation_version_id=implementation_id,
            implementation_kind=kind,
            name=identity["name"],
            version=identity["version"],
            source_code=code,
            source_hash=digest,
            entrypoint=entrypoint,
            parameter_schema=identity["parameter_schema"],
            dependencies=tuple(identity["dependencies"]),
            authoring_origin=identity["authoring_origin"],
            capabilities=tuple(identity["capabilities"]),
            runtime_requirements=identity["runtime_requirements"],
            resource_bounds=identity["resource_bounds"],
            provenance_refs=tuple(identity["provenance_refs"]),
            metadata=identity["metadata"],
            status=str(payload.get("status") or "registered"),
        )


def build_implementation_version(
    *,
    implementation_kind: str,
    name: str,
    version: str,
    source_code: str,
    class_name: str | None,
    factory_name: str,
    parameter_schema: Mapping[str, Any] | None,
    dependencies: Sequence[str] | None,
    authoring_origin: str,
    capabilities: Sequence[str] | None,
    runtime_requirements: Mapping[str, Any] | None,
    resource_bounds: Mapping[str, Any] | None,
    provenance_refs: Sequence[Mapping[str, Any]] | None,
    metadata: Mapping[str, Any] | None,
) -> ImplementationVersion:
    """Normalize registration inputs and derive a content-addressed version ID."""
    kind = str(implementation_kind or "").strip()
    if kind not in IMPLEMENTATION_KINDS:
        raise ValueError(f"unsupported implementation_kind: {kind}")
    normalized_name = str(name or "").strip()
    normalized_version = str(version or "").strip()
    normalized_source = str(source_code or "")
    normalized_factory = str(factory_name or "").strip()
    if not normalized_name or not normalized_version or not normalized_source or not normalized_factory:
        raise ValueError("name, version, source_code, and factory_name are required")
    if len(normalized_source.encode("utf-8")) > 512_000:
        raise ValueError("source_code exceeds the 512000-byte registration limit")
    normalized_schema = _normalize_parameter_schema(parameter_schema or {})
    entrypoint = {
        "factory_name": normalized_factory,
        "class_name": str(class_name or "").strip() or None,
        "runtime_contract": RUNTIME_CONTRACT_BY_KIND[kind],
    }
    identity = _implementation_identity(
        implementation_kind=kind,
        name=normalized_name,
        version=normalized_version,
        source_digest=source_hash(normalized_source),
        entrypoint=entrypoint,
        parameter_schema=normalized_schema,
        dependencies=_strings(dependencies),
        authoring_origin=str(authoring_origin or "supplied").strip(),
        capabilities=_strings(capabilities),
        runtime_requirements=_normalize_runtime_requirements(kind, runtime_requirements or {}),
        resource_bounds=dict(resource_bounds or {}),
        provenance_refs=_mappings(provenance_refs),
        metadata=dict(metadata or {}),
    )
    return ImplementationVersion(
        implementation_version_id=stable_research_id("implementation_version", identity),
        implementation_kind=kind,
        name=normalized_name,
        version=normalized_version,
        source_code=normalized_source,
        source_hash=identity["source_hash"],
        entrypoint=entrypoint,
        parameter_schema=normalized_schema,
        dependencies=tuple(identity["dependencies"]),
        authoring_origin=identity["authoring_origin"],
        capabilities=tuple(identity["capabilities"]),
        runtime_requirements=identity["runtime_requirements"],
        resource_bounds=identity["resource_bounds"],
        provenance_refs=tuple(identity["provenance_refs"]),
        metadata=identity["metadata"],
    )


def _implementation_identity(
    *,
    implementation_kind: str,
    name: str,
    version: str,
    source_digest: str,
    entrypoint: Mapping[str, Any],
    parameter_schema: Mapping[str, Any],
    dependencies: Sequence[str],
    authoring_origin: str,
    capabilities: Sequence[str],
    runtime_requirements: Mapping[str, Any],
    resource_bounds: Mapping[str, Any],
    provenance_refs: Sequence[Mapping[str, Any]],
    metadata: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "implementation_kind": implementation_kind,
        "name": name,
        "version": version,
        "source_hash": source_digest,
        "entrypoint": dict(entrypoint),
        "parameter_schema": dict(parameter_schema),
        "dependencies": sorted(set(dependencies)),
        "authoring_origin": authoring_origin,
        "capabilities": sorted(set(capabilities)),
        "runtime_requirements": dict(runtime_requirements),
        "resource_bounds": dict(resource_bounds),
        "provenance_refs": [dict(item) for item in provenance_refs],
        "metadata": dict(metadata),
    }


def parameter_defaults(schema: Mapping[str, Any]) -> dict[str, Any]:
    """Return explicit parameter defaults from a JSON-schema-like mapping."""
    properties = _mapping(schema.get("properties") or {}, "parameter_schema.properties")
    return {
        str(name): dict(spec).get("default")
        for name, spec in properties.items()
        if isinstance(spec, MappingABC) and "default" in spec
    }


def validate_parameters(schema: Mapping[str, Any], parameters: Mapping[str, Any]) -> tuple[str, ...]:
    """Validate scalar parameters against the maintained bounded schema subset."""
    properties = _mapping(schema.get("properties") or {}, "parameter_schema.properties")
    required = set(_strings(schema.get("required")))
    blockers: list[str] = []
    for name in sorted(set(parameters).difference(properties)):
        blockers.append(f"unknown parameter: {name}")
    for name in sorted(required.difference(parameters)):
        blockers.append(f"required parameter is missing: {name}")
    for name, value in parameters.items():
        spec = properties.get(name)
        if not isinstance(spec, MappingABC):
            continue
        expected = str(spec.get("type") or "")
        if expected == "integer" and (isinstance(value, bool) or not isinstance(value, int)):
            blockers.append(f"parameter {name} must be an integer")
            continue
        if expected == "number" and (isinstance(value, bool) or not isinstance(value, (int, float))):
            blockers.append(f"parameter {name} must be numeric")
            continue
        if expected == "string" and not isinstance(value, str):
            blockers.append(f"parameter {name} must be a string")
            continue
        if expected == "boolean" and not isinstance(value, bool):
            blockers.append(f"parameter {name} must be boolean")
            continue
        if "enum" in spec and value not in spec["enum"]:
            blockers.append(f"parameter {name} must be one of {list(spec['enum'])}")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if "minimum" in spec and float(value) < float(spec["minimum"]):
                blockers.append(f"parameter {name} must be >= {spec['minimum']}")
            if "maximum" in spec and float(value) > float(spec["maximum"]):
                blockers.append(f"parameter {name} must be <= {spec['maximum']}")
    return tuple(blockers)


def _normalize_parameter_schema(schema: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(schema)
    payload.setdefault("type", "object")
    payload.setdefault("properties", {})
    payload.setdefault("required", [])
    if payload["type"] != "object" or not isinstance(payload["properties"], MappingABC):
        raise ValueError("parameter_schema must describe an object with properties")
    if not isinstance(payload["required"], SequenceABC) or isinstance(payload["required"], (str, bytes)):
        raise ValueError("parameter_schema.required must be an array")
    return payload


def _normalize_runtime_requirements(
    implementation_kind: str,
    value: Mapping[str, Any],
) -> dict[str, Any]:
    payload = _mapping(value, "runtime_requirements")
    unknown = sorted(set(payload).difference({"prediction_requirements"}))
    if unknown:
        raise ValueError(f"unknown runtime_requirements fields: {unknown}")
    raw_requirements = payload.get("prediction_requirements")
    if raw_requirements is None:
        return {}
    if implementation_kind != "strategy":
        raise ValueError("prediction_requirements are only valid for strategy implementations")
    if not isinstance(raw_requirements, SequenceABC) or isinstance(raw_requirements, (str, bytes)):
        raise ValueError("runtime_requirements.prediction_requirements must be an array")
    requirements: list[dict[str, Any]] = []
    names: set[str] = set()
    allowed_fields = {
        "name",
        "accepted_semantics",
        "accepted_horizons",
        "accepted_output_shapes",
        "inference_scopes",
        "consumer_kind",
        "required",
    }
    for raw in raw_requirements:
        item = _mapping(raw, "prediction requirement")
        unknown_fields = sorted(set(item).difference(allowed_fields))
        if unknown_fields:
            raise ValueError(f"unknown prediction requirement fields: {unknown_fields}")
        name = str(item.get("name") or "").strip()
        if not name or name in names:
            raise ValueError("prediction requirement names must be present and unique")
        semantics = _required_strings(item.get("accepted_semantics"), "accepted_semantics")
        horizons = _required_strings(item.get("accepted_horizons"), "accepted_horizons")
        shapes = _required_strings(item.get("accepted_output_shapes"), "accepted_output_shapes")
        scopes = _required_strings(item.get("inference_scopes"), "inference_scopes")
        consumer_kind = str(item.get("consumer_kind") or "").strip()
        if set(shapes).difference(PREDICTION_OUTPUT_SHAPES):
            raise ValueError(f"unsupported prediction output shape in requirement {name}")
        if set(scopes).difference(PREDICTION_INFERENCE_SCOPES):
            raise ValueError(f"unsupported prediction inference scope in requirement {name}")
        if consumer_kind not in PREDICTION_CONSUMER_KINDS:
            raise ValueError(f"unsupported prediction consumer_kind in requirement {name}")
        names.add(name)
        requirements.append(
            {
                "name": name,
                "accepted_semantics": list(semantics),
                "accepted_horizons": list(horizons),
                "accepted_output_shapes": list(shapes),
                "inference_scopes": list(scopes),
                "consumer_kind": consumer_kind,
                "required": bool(item.get("required", True)),
            }
        )
    if not requirements:
        raise ValueError("prediction_requirements cannot be empty when supplied")
    return {"prediction_requirements": sorted(requirements, key=lambda item: item["name"])}


def _required_strings(value: Any, label: str) -> tuple[str, ...]:
    values = tuple(sorted(set(_strings(value))))
    if not values:
        raise ValueError(f"prediction requirement {label} cannot be empty")
    return values


def _required(payload: Mapping[str, Any], name: str) -> str:
    value = str(payload.get(name) or "").strip()
    if not value:
        raise ValueError(f"implementation {name} is required")
    return value


def _mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, MappingABC):
        raise ValueError(f"{name} must be a mapping")
    return {str(key): item for key, item in value.items()}


def _mappings(value: Any) -> tuple[Mapping[str, Any], ...]:
    if value is None:
        return ()
    if not isinstance(value, SequenceABC) or isinstance(value, (str, bytes)):
        raise ValueError("provenance_refs must be an array")
    return tuple(_mapping(item, "provenance_refs item") for item in value)


def _strings(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, SequenceABC) or isinstance(value, (str, bytes)):
        raise ValueError("value must be an array of strings")
    return tuple(str(item).strip() for item in value if str(item).strip())
