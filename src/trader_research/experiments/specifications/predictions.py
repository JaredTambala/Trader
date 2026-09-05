"""Resolve typed prediction requirements into canonical strategy bindings.

Bindings pin passed deployment evidence and an exact mapper configuration for
each implementation requirement. Revalidation reconstructs those bindings from
canonical dependencies and rejects missing providers, mismatches, or drift.
"""

from __future__ import annotations

from collections.abc import Mapping as MappingABC, Sequence as SequenceABC
from typing import Any, Mapping, Sequence

from trader_research.foundation import (
    PredictionDeploymentReader,
    PredictionMapperCatalog,
    json_payload_hash,
    research_artifact_uri,
)


def build_prediction_bindings(
    *,
    requirements: Sequence[Mapping[str, Any]],
    requested_bindings: Sequence[Mapping[str, Any]] | None,
    deployment_reader: PredictionDeploymentReader | None,
    mapper_catalog: PredictionMapperCatalog | None,
) -> tuple[list[dict[str, Any]], str]:
    """Resolve requested prediction bindings against declared requirements.

    Each named requirement must have exactly one compatible passed deployment and
    mapper configuration. Output semantics, horizon, asset scope, timeframe, and
    decision scope are normalized and pinned; all bindings must agree on the
    strategy decision scope.

    Returns:
        Bindings sorted by requirement name and their shared decision scope.

    Raises:
        ValueError: If providers are unavailable or a binding is missing,
            duplicated, incompatible, or mixes decision scopes.
    """
    normalized_requirements = {str(item["name"]): dict(item) for item in requirements}
    raw_bindings = _mappings(requested_bindings or (), "prediction_bindings")
    if not normalized_requirements:
        if raw_bindings:
            raise ValueError("strategy implementation declares no prediction requirements")
        return [], "per_symbol"
    if deployment_reader is None:
        raise ValueError("prediction deployment reader is required for model-backed strategies")
    if mapper_catalog is None:
        raise ValueError("prediction mapper catalog is required for model-backed strategies")
    names = [str(item.get("name") or "").strip() for item in raw_bindings]
    if any(not name for name in names) or len(set(names)) != len(names):
        raise ValueError("prediction binding names must be present and unique")
    unknown = sorted(set(names).difference(normalized_requirements))
    if unknown:
        raise ValueError(f"prediction bindings do not match implementation requirements: {unknown}")
    missing = sorted(
        name
        for name, requirement in normalized_requirements.items()
        if requirement.get("required", True) and name not in names
    )
    if missing:
        raise ValueError(f"required prediction bindings are missing: {missing}")
    bindings = [
        _build_binding(
            requested=item,
            requirement=normalized_requirements[str(item["name"])],
            deployment_reader=deployment_reader,
            mapper_catalog=mapper_catalog,
        )
        for item in raw_bindings
    ]
    decision_scopes = {str(item["decision_scope"]) for item in bindings}
    if len(decision_scopes) > 1:
        raise ValueError("strategy prediction bindings cannot mix per-symbol and universe decision scopes")
    return sorted(bindings, key=lambda item: item["name"]), next(iter(decision_scopes), "per_symbol")


def revalidate_prediction_bindings(
    *,
    requirements: Sequence[Mapping[str, Any]],
    persisted_bindings: Sequence[Mapping[str, Any]],
    deployment_reader: PredictionDeploymentReader | None,
    mapper_catalog: PredictionMapperCatalog | None,
) -> tuple[list[dict[str, Any]], str]:
    """Rebuild persisted prediction bindings and reject dependency drift.

    Persisted bindings are converted back to the minimal request form and passed
    through the normal resolver. The rebuilt canonical payload must match exactly,
    including deployment, validation, mapper, semantics, and scope identity.

    Returns:
        The revalidated canonical bindings and shared decision scope.

    Raises:
        ValueError: If persisted evidence is malformed or no longer matches its
            canonical deployment and mapper dependencies.
    """
    requested = [
        {
            "name": item.get("name"),
            "deployment_validation_ref": item.get("deployment_validation_id"),
            "output_names": [output.get("name") for output in item.get("selected_outputs", [])],
            "mapper_id": _mapping(item.get("mapper"), "prediction binding mapper").get("mapper_id"),
            "mapper_parameters": _mapping(
                _mapping(item.get("mapper"), "prediction binding mapper").get("parameters") or {},
                "prediction binding mapper parameters",
            ),
        }
        for item in _mappings(persisted_bindings, "prediction_bindings")
    ]
    rebuilt, decision_scope = build_prediction_bindings(
        requirements=requirements,
        requested_bindings=requested,
        deployment_reader=deployment_reader,
        mapper_catalog=mapper_catalog,
    )
    if rebuilt != [dict(item) for item in persisted_bindings]:
        raise ValueError("strategy prediction binding dependency evidence drifted")
    return rebuilt, decision_scope


def _build_binding(
    *,
    requested: Mapping[str, Any],
    requirement: Mapping[str, Any],
    deployment_reader: PredictionDeploymentReader,
    mapper_catalog: PredictionMapperCatalog,
) -> dict[str, Any]:
    allowed = {
        "name",
        "deployment_validation_ref",
        "output_names",
        "mapper_id",
        "mapper_parameters",
    }
    unknown = sorted(set(requested).difference(allowed))
    if unknown:
        raise ValueError(f"unknown prediction binding fields: {unknown}")
    validation_ref = str(requested.get("deployment_validation_ref") or "").strip()
    if not validation_ref:
        raise ValueError("prediction binding deployment_validation_ref is required")
    deployment = dict(deployment_reader.resolve_passed(validation_ref))
    inference_scope = str(deployment.get("inference_scope") or "")
    if inference_scope not in requirement["inference_scopes"]:
        raise ValueError(
            f"prediction binding {requirement['name']} does not accept inference scope {inference_scope}"
        )
    if "backtest" not in deployment.get("eligibility", []):
        raise ValueError("prediction deployment is not eligible for backtests")
    output_names = _strings(requested.get("output_names"), "prediction binding output_names")
    if not output_names:
        raise ValueError("prediction binding output_names cannot be empty")
    contract_by_name = {
        str(item["name"]): dict(item)
        for item in _mappings(deployment.get("output_contract"), "deployment output_contract")
    }
    unknown_outputs = sorted(set(output_names).difference(contract_by_name))
    if unknown_outputs:
        raise ValueError(f"prediction binding selects unknown deployment outputs: {unknown_outputs}")
    selected_outputs = [contract_by_name[name] for name in output_names]
    for output in selected_outputs:
        if output.get("semantics") not in requirement["accepted_semantics"]:
            raise ValueError(
                f"prediction output {output['name']} semantics are incompatible with {requirement['name']}"
            )
        if output.get("horizon") not in requirement["accepted_horizons"]:
            raise ValueError(
                f"prediction output {output['name']} horizon is incompatible with {requirement['name']}"
            )
        if output.get("shape") not in requirement["accepted_output_shapes"]:
            raise ValueError(
                f"prediction output {output['name']} shape is incompatible with {requirement['name']}"
            )
    mapper = dict(
        mapper_catalog.resolve_configuration(
            mapper_id=str(requested.get("mapper_id") or ""),
            consumer_kind=str(requirement["consumer_kind"]),
            output_contract=selected_outputs,
            parameters=_mapping(requested.get("mapper_parameters") or {}, "mapper_parameters"),
        )
    )
    deployment_manifest = _mapping(deployment.get("manifest"), "deployment manifest")
    validation_id = str(deployment.get("deployment_validation_id") or "")
    return {
        "name": str(requirement["name"]),
        "requirement": dict(requirement),
        "deployment_validation_id": validation_id,
        "deployment_validation_uri": research_artifact_uri(
            "ml_deployment_validation_report", validation_id
        ),
        "deployment_id": str(deployment["deployment_id"]),
        "model_version_id": str(deployment["model_version_id"]),
        "feature_set_id": str(deployment["feature_set_id"]),
        "deployment_manifest_hash": f"sha256:{json_payload_hash(deployment_manifest)}",
        "inference_scope": inference_scope,
        "decision_scope": str(deployment["decision_scope"]),
        "selected_outputs": selected_outputs,
        "mapper": mapper,
    }


def _mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, MappingABC):
        raise ValueError(f"{label} must be a mapping")
    return {str(key): item for key, item in value.items()}


def _mappings(value: object, label: str) -> tuple[dict[str, Any], ...]:
    if not isinstance(value, SequenceABC) or isinstance(value, (str, bytes)):
        raise ValueError(f"{label} must be an array")
    return tuple(_mapping(item, f"{label} item") for item in value)


def _strings(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, SequenceABC) or isinstance(value, (str, bytes)):
        raise ValueError(f"{label} must be an array")
    normalized = tuple(str(item).strip() for item in value if str(item).strip())
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{label} must contain unique values")
    return normalized
