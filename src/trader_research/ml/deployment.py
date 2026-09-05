"""Create and validate canonical raw-inference deployment manifests.

Deployment records bind exact model and feature evidence to an adapter profile,
output contract, inference policy, environment, parity fixture, and eligibility.
Validation reloads lineage and executes adapter parity before runtime use.
"""

from __future__ import annotations

from collections.abc import Mapping as MappingABC, Sequence as SequenceABC
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from trader.predictions import InferencePolicy, canonical_json_hash
from trader_research.foundation import (
    ApplicationResult,
    error_result,
    stable_research_id,
    success_result,
)
from trader_research.foundation.artifacts import (
    ResearchArtifactStore,
    ResearchArtifactStoreError,
    SCHEMA_VERSION,
    load_artifact_ref,
)
from trader_research.governance.artifacts import (
    DOMAIN_OWNER_BY_ARTIFACT_TYPE,
    ML_DEPLOYMENT_MANIFEST,
    ML_DEPLOYMENT_VALIDATION_REPORT,
    ML_FEATURE_SET_SPEC,
    ML_FEATURE_SET_VALIDATION_REPORT,
    ML_MODEL_VERSION_REF,
)

from .adapters import InferenceAdapterRegistry


ML_CREATE_DEPLOYMENT_MANIFEST = "ml_create_deployment_manifest"
ML_VALIDATE_DEPLOYMENT = "ml_validate_deployment"
INFERENCE_SCOPES = frozenset({"per_symbol", "cross_sectional", "portfolio"})
ELIGIBLE_ENVIRONMENTS = frozenset({"backtest", "paper"})


@dataclass(frozen=True)
class ArtifactPredictionDeploymentReader:
    """Resolve passed deployment evidence from the canonical artifact store."""

    artifact_store: ResearchArtifactStore

    def resolve_passed(self, validation_ref: str) -> Mapping[str, Any]:
        """Resolve passed deployment evidence for prediction consumers.

        The manifest and validation report are loaded through the fail-closed
        deployment reader. The returned mapping exposes pinned model, feature,
        adapter, output, scope, policy, and eligibility identity plus the complete
        manifest, but no loaded predictor.
        """
        manifest, report = load_passed_deployment(self.artifact_store, validation_ref)
        return {
            "deployment_id": manifest["deployment_id"],
            "deployment_validation_id": report["validation_id"],
            "model_version_id": manifest["model_version"]["payload"]["model_version_id"],
            "feature_set_id": manifest["feature_set"]["payload"]["feature_set_id"],
            "adapter_profile": dict(manifest["adapter_profile"]),
            "output_contract": [dict(item) for item in manifest["output_contract"]],
            "inference_scope": manifest["inference_scope"],
            "decision_scope": manifest["decision_scope"],
            "inference_policy": dict(manifest["inference_policy"]),
            "eligibility": list(manifest["eligibility"]),
            "manifest": dict(manifest),
        }


def create_deployment_manifest(
    *,
    model_version_ref: str,
    feature_set_validation_ref: str,
    adapter_profile: str,
    output_contract: Sequence[Mapping[str, Any]],
    inference_scope: str,
    inference_policy: Mapping[str, Any] | None = None,
    environment: Mapping[str, Any] | None = None,
    parity_fixture: Mapping[str, Any] | None = None,
    eligibility: Sequence[str] = ("backtest",),
    artifact_store: ResearchArtifactStore | None = None,
    adapter_registry: InferenceAdapterRegistry | None = None,
) -> ApplicationResult:
    """Create an immutable ML deployment over exact model and feature evidence.

    The model-version and passed feature-set validation are loaded and snapshotted,
    the adapter profile is resolved without loading a model, and output, scope,
    policy, environment, parity, and eligibility inputs are normalized into the
    content-derived deployment ID. Creation does not confer runtime eligibility.

    Returns:
        A result containing the persisted manifest and canonical reference, or a
        structured lineage, contract, adapter-profile, or storage failure.
    """
    command = ML_CREATE_DEPLOYMENT_MANIFEST
    if artifact_store is None:
        return _error(command, "research_artifact_store_required", "A ResearchArtifactStore is required.")
    if adapter_registry is None:
        return _error(command, "inference_adapter_registry_required", "An InferenceAdapterRegistry is required.")
    try:
        model = _load_model_version(artifact_store, model_version_ref)
        feature_set, feature_validation = _load_passed_feature_set(
            artifact_store, feature_set_validation_ref
        )
        profile = adapter_registry.get(adapter_profile).profile()
        if not profile.available:
            raise ValueError(profile.reason or "inference adapter is unavailable")
        normalized_outputs = _normalize_output_contract(output_contract)
        normalized_scope = str(inference_scope or "").strip()
        if normalized_scope not in INFERENCE_SCOPES:
            raise ValueError(f"unsupported inference_scope: {normalized_scope}")
        decision_scope = "per_symbol" if normalized_scope == "per_symbol" else "universe_snapshot"
        policy = InferencePolicy(**dict(inference_policy or {}))
        normalized_eligibility = tuple(
            sorted(set(str(item).strip() for item in eligibility if str(item).strip()))
        )
        if not normalized_eligibility or set(normalized_eligibility).difference(ELIGIBLE_ENVIRONMENTS):
            raise ValueError("deployment eligibility may contain only backtest and paper")
        normalized_environment = _mapping(environment or {}, "environment")
        _reject_credentials(normalized_environment)
        fixture = _normalize_parity_fixture(parity_fixture or {}, feature_set, normalized_outputs)
        identity = {
            "model_version": _snapshot(model),
            "feature_set": _snapshot(feature_set),
            "feature_set_validation": _snapshot(feature_validation),
            "adapter_profile": profile.to_dict(),
            "output_contract": normalized_outputs,
            "inference_scope": normalized_scope,
            "decision_scope": decision_scope,
            "inference_policy": policy.to_dict(),
            "environment": normalized_environment,
            "parity_fixture": fixture,
            "eligibility": list(normalized_eligibility),
        }
        deployment_id = stable_research_id("ml_deployment", identity)
        payload = {
            "artifact_type": ML_DEPLOYMENT_MANIFEST,
            "schema_version": SCHEMA_VERSION,
            "deployment_id": deployment_id,
            **identity,
            "status": "created",
            "policy": {
                "broker_mutation_allowed": False,
                "live_trading_allowed": False,
                "mcp_hot_path_allowed": False,
                "dynamic_alias_resolution_allowed": False,
            },
        }
        record = artifact_store.save_artifact(
            domain_owner=DOMAIN_OWNER_BY_ARTIFACT_TYPE[ML_DEPLOYMENT_MANIFEST],
            producer_tool=ML_CREATE_DEPLOYMENT_MANIFEST,
            artifact_type=ML_DEPLOYMENT_MANIFEST,
            artifact_id=deployment_id,
            payload=payload,
            status="created",
            source_hash=str(model.get("model_digest") or ""),
            metadata={
                "model_version_id": model["model_version_id"],
                "feature_set_id": feature_set["feature_set_id"],
                "adapter_profile": profile.profile_name,
                "decision_scope": decision_scope,
            },
        )
    except (ValueError, KeyError, ResearchArtifactStoreError) as exc:
        return _error(command, "ml_deployment_creation_failed", str(exc))
    return success_result(
        command=command,
        data={"ml_deployment_manifest": payload},
        artifacts={"ml_deployment_manifest": record.reference().to_dict()},
    )


def validate_deployment(
    *,
    deployment_id: str | None = None,
    deployment_uri: str | None = None,
    deployment_manifest: Mapping[str, Any] | None = None,
    artifact_store: ResearchArtifactStore | None = None,
    adapter_registry: InferenceAdapterRegistry | None = None,
) -> ApplicationResult:
    """Revalidate deployment lineage and execute its adapter parity fixture.

    Exactly one inline, ID, or URI manifest is resolved. Model and feature
    snapshots, deployment identity, adapter profile, output contract, and policy
    are rechecked before a pinned predictor runs the bounded fixture. A separate
    validation report is persisted for passed and blocked outcomes.

    Returns:
        A result containing validation and adapter evidence; ``ok`` is false for
        blockers, unavailable adapters, runtime failures, or storage errors.
    """
    command = ML_VALIDATE_DEPLOYMENT
    if artifact_store is None:
        return _error(command, "research_artifact_store_required", "A ResearchArtifactStore is required.")
    if adapter_registry is None:
        return _error(command, "inference_adapter_registry_required", "An InferenceAdapterRegistry is required.")
    try:
        manifest = _resolve_manifest(
            artifact_store,
            deployment_id=deployment_id,
            deployment_uri=deployment_uri,
            inline=deployment_manifest,
        )
        blockers = _manifest_blockers(artifact_store, manifest)
        adapter_evidence: Mapping[str, object] = {"status": "not_run"}
        profile_name = str(_mapping(manifest.get("adapter_profile"), "adapter_profile").get("profile_name") or "")
        adapter = adapter_registry.get(profile_name)
        if adapter.profile().to_dict() != dict(manifest.get("adapter_profile") or {}):
            blockers.append("inference adapter profile or configuration drifted")
        if not adapter.profile().available:
            blockers.append(adapter.profile().reason or "inference adapter is unavailable")
        if not blockers:
            try:
                adapter_evidence = dict(adapter.validate_deployment(manifest))
                if adapter_evidence.get("status") != "passed":
                    blockers.append(str(adapter_evidence.get("blocker") or "adapter parity validation failed"))
            except Exception as exc:
                blockers.append(f"adapter parity validation failed: {exc}")
    except (ValueError, KeyError, ResearchArtifactStoreError) as exc:
        return _error(command, "ml_deployment_resolution_failed", str(exc))
    identity = {
        "deployment_id": manifest["deployment_id"],
        "model_version_id": manifest["model_version"]["payload"]["model_version_id"],
        "feature_set_id": manifest["feature_set"]["payload"]["feature_set_id"],
        "adapter_profile": manifest["adapter_profile"],
        "adapter_evidence": dict(adapter_evidence),
        "blockers": blockers,
    }
    report = {
        "artifact_type": ML_DEPLOYMENT_VALIDATION_REPORT,
        "schema_version": SCHEMA_VERSION,
        "validation_id": stable_research_id("ml_deployment_validation", identity),
        **identity,
        "status": "passed" if not blockers else "blocked",
        "valid": not blockers,
        "warnings": [],
    }
    try:
        record = artifact_store.save_artifact(
            domain_owner=DOMAIN_OWNER_BY_ARTIFACT_TYPE[ML_DEPLOYMENT_VALIDATION_REPORT],
            producer_tool=ML_VALIDATE_DEPLOYMENT,
            artifact_type=ML_DEPLOYMENT_VALIDATION_REPORT,
            artifact_id=report["validation_id"],
            payload=report,
            status=report["status"],
            source_hash=str(manifest["model_version"]["payload"].get("model_digest") or ""),
            metadata={"deployment_id": manifest["deployment_id"]},
        )
    except ResearchArtifactStoreError as exc:
        return _error(command, "ml_deployment_validation_persistence_failed", str(exc))
    result = success_result(
        command=command,
        data={"ml_deployment_validation_report": report},
        artifacts={"ml_deployment_validation_report": record.reference().to_dict()},
    )
    if not blockers:
        return result
    return ApplicationResult(
        ok=False,
        operation=command,
        data=result.data,
        artifacts=result.artifacts,
        errors=({"code": "ml_deployment_validation_failed", "message": blockers[0]},),
    )


def load_passed_deployment(
    store: ResearchArtifactStore,
    validation_ref: str,
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    """Load a passed deployment and revalidate its complete dependency chain.

    The report must be passed, valid, blocker-free, and content-addressed to the
    manifest. Current model, feature-set, adapter, output, policy, and fixture
    evidence must still match before the pair is returned.

    Returns:
        The canonical deployment manifest and passed validation payload.

    Raises:
        ValueError: If status, identity, eligibility, or dependency evidence has
            drifted.
        ResearchArtifactStoreError: If a required artifact cannot be loaded.
    """
    report = load_artifact_ref(store, ML_DEPLOYMENT_VALIDATION_REPORT, validation_ref)
    if report.get("artifact_type") != ML_DEPLOYMENT_VALIDATION_REPORT:
        raise ValueError(f"artifact_type must be {ML_DEPLOYMENT_VALIDATION_REPORT}")
    if report.get("status") != "passed" or report.get("valid") is not True or report.get("blockers"):
        raise ValueError("deployment validation must be passed, valid, and blocker-free")
    manifest = load_artifact_ref(store, ML_DEPLOYMENT_MANIFEST, str(report.get("deployment_id") or ""))
    blockers = _manifest_blockers(store, manifest)
    if blockers:
        raise ValueError(blockers[0])
    expected_identity = {
        "deployment_id": manifest["deployment_id"],
        "model_version_id": manifest["model_version"]["payload"]["model_version_id"],
        "feature_set_id": manifest["feature_set"]["payload"]["feature_set_id"],
        "adapter_profile": manifest["adapter_profile"],
        "adapter_evidence": report.get("adapter_evidence") or {},
        "blockers": [],
    }
    if stable_research_id("ml_deployment_validation", expected_identity) != report.get("validation_id"):
        raise ValueError("deployment validation ID does not match canonical evidence")
    return manifest, report


def _manifest_blockers(store: ResearchArtifactStore, manifest: Mapping[str, Any]) -> list[str]:
    blockers: list[str] = []
    if manifest.get("artifact_type") != ML_DEPLOYMENT_MANIFEST:
        return [f"artifact_type must be {ML_DEPLOYMENT_MANIFEST}"]
    try:
        model_snapshot = _mapping(manifest.get("model_version"), "model_version")
        feature_snapshot = _mapping(manifest.get("feature_set"), "feature_set")
        feature_validation_snapshot = _mapping(
            manifest.get("feature_set_validation"), "feature_set_validation"
        )
        model = _load_model_version(
            store, str(_mapping(model_snapshot.get("payload"), "model payload").get("model_version_id") or "")
        )
        feature, validation = _load_passed_feature_set(
            store,
            str(
                _mapping(feature_validation_snapshot.get("payload"), "feature validation payload").get(
                    "validation_id"
                )
                or ""
            ),
        )
        if _snapshot(model) != model_snapshot:
            blockers.append("model version snapshot drifted")
        if _snapshot(feature) != feature_snapshot:
            blockers.append("feature set snapshot drifted")
        if _snapshot(validation) != feature_validation_snapshot:
            blockers.append("feature set validation snapshot drifted")
        identity = {
            key: manifest.get(key)
            for key in (
                "model_version",
                "feature_set",
                "feature_set_validation",
                "adapter_profile",
                "output_contract",
                "inference_scope",
                "decision_scope",
                "inference_policy",
                "environment",
                "parity_fixture",
                "eligibility",
            )
        }
        if stable_research_id("ml_deployment", identity) != manifest.get("deployment_id"):
            blockers.append("deployment ID does not match canonical content")
        InferencePolicy(**dict(manifest.get("inference_policy") or {}))
        _normalize_output_contract(manifest.get("output_contract") or [])
    except (ValueError, KeyError, ResearchArtifactStoreError) as exc:
        blockers.append(str(exc))
    return blockers


def _load_model_version(store: ResearchArtifactStore, ref: str) -> Mapping[str, Any]:
    payload = load_artifact_ref(store, ML_MODEL_VERSION_REF, ref)
    if payload.get("artifact_type") != ML_MODEL_VERSION_REF:
        raise ValueError(f"artifact_type must be {ML_MODEL_VERSION_REF}")
    if payload.get("status") not in {"registered", "passed"}:
        raise ValueError("model version must be registered or passed")
    required = (
        "model_version_id",
        "registered_model_name",
        "model_version",
        "model_digest",
        "signature_digest",
        "source_run_id",
        "model_uri",
    )
    for name in required:
        if not str(payload.get(name) or "").strip():
            raise ValueError(f"model version {name} is required")
    model_uri = str(payload["model_uri"])
    if model_uri.startswith("models:/"):
        registry_ref = model_uri.removeprefix("models:/")
        registry_parts = registry_ref.split("/")
        if (
            "@" in registry_ref
            or len(registry_parts) != 2
            or registry_parts[0] != str(payload["registered_model_name"])
            or registry_parts[1] != str(payload["model_version"])
        ):
            raise ValueError("MLflow model URI must pin the declared immutable registry version")
    if str(payload.get("resolved_alias") or "").strip() and payload.get("immutable") is not True:
        raise ValueError("alias-derived model versions must be resolved and immutable")
    return payload


def _load_passed_feature_set(
    store: ResearchArtifactStore, validation_ref: str
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    report = load_artifact_ref(store, ML_FEATURE_SET_VALIDATION_REPORT, validation_ref)
    if report.get("artifact_type") != ML_FEATURE_SET_VALIDATION_REPORT:
        raise ValueError(f"artifact_type must be {ML_FEATURE_SET_VALIDATION_REPORT}")
    if report.get("status") != "passed" or report.get("valid") is not True or report.get("blockers"):
        raise ValueError("feature set validation must be passed, valid, and blocker-free")
    feature_set = load_artifact_ref(store, ML_FEATURE_SET_SPEC, str(report.get("feature_set_id") or ""))
    if feature_set.get("artifact_type") != ML_FEATURE_SET_SPEC:
        raise ValueError(f"artifact_type must be {ML_FEATURE_SET_SPEC}")
    if feature_set.get("status") not in {"created", "passed"}:
        raise ValueError("feature set must be created or passed")
    if not str(feature_set.get("feature_set_id") or "").strip() or not str(
        feature_set.get("feature_set_digest") or ""
    ).strip():
        raise ValueError("feature set ID and digest are required")
    if report.get("feature_set_digest") != feature_set.get("feature_set_digest"):
        raise ValueError("feature set digest does not match validation")
    return feature_set, report


def _normalize_output_contract(value: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(value, SequenceABC) or isinstance(value, (str, bytes)) or not value:
        raise ValueError("output_contract must be a non-empty sequence")
    outputs: list[dict[str, Any]] = []
    names: set[str] = set()
    for raw in value:
        item = _mapping(raw, "output_contract item")
        name = str(item.get("name") or "").strip()
        semantics = str(item.get("semantics") or "").strip()
        horizon = str(item.get("horizon") or "").strip()
        dtype = str(item.get("dtype") or "float64").strip()
        shape = str(item.get("shape") or "scalar").strip()
        if not name or not semantics or not horizon:
            raise ValueError("output contract name, semantics, and horizon are required")
        if name in names:
            raise ValueError(f"duplicate output contract name: {name}")
        if shape not in {"scalar", "structured"}:
            raise ValueError("output contract shape must be scalar or structured")
        names.add(name)
        outputs.append(
            {
                "name": name,
                "semantics": semantics,
                "horizon": horizon,
                "dtype": dtype,
                "shape": shape,
                "units": str(item.get("units") or "").strip() or None,
                "nullable": bool(item.get("nullable", False)),
            }
        )
    return outputs


def _normalize_parity_fixture(
    value: Mapping[str, Any],
    feature_set: Mapping[str, Any],
    outputs: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    fixture = dict(value)
    decision_ts = str(fixture.get("decision_ts") or "").strip()
    if not decision_ts:
        raise ValueError("parity_fixture.decision_ts is required")
    rows = fixture.get("rows")
    if not isinstance(rows, SequenceABC) or isinstance(rows, (str, bytes)) or not rows:
        raise ValueError("parity_fixture.rows must be a non-empty sequence")
    expected = fixture.get("expected_outputs")
    if not isinstance(expected, SequenceABC) or isinstance(expected, (str, bytes)) or not expected:
        raise ValueError("parity_fixture.expected_outputs must be a non-empty sequence")
    output_by_name = {str(item["name"]): item for item in outputs}
    normalized_expected: list[dict[str, Any]] = []
    for raw in expected:
        item = _mapping(raw, "parity output")
        output_name = str(item.get("output_name") or "").strip()
        contract = output_by_name.get(output_name)
        if contract is None:
            raise ValueError(f"unknown parity output: {output_name}")
        if "value" not in item:
            raise ValueError("parity output value is required")
        normalized_expected.append(
            {
                "symbol": str(item.get("symbol") or "").strip().upper() or None,
                "output_name": output_name,
                "semantics": str(item.get("semantics") or contract["semantics"]),
                "value": item["value"],
                "horizon": str(item.get("horizon") or contract["horizon"]),
                "units": item.get("units", contract.get("units")),
                "uncertainty": item.get("uncertainty"),
                "metadata": dict(_mapping(item.get("metadata") or {}, "parity output metadata")),
            }
        )
    expected_names = {item["output_name"] for item in normalized_expected}
    if expected_names != {str(item["name"]) for item in outputs}:
        raise ValueError("parity fixture outputs must match the deployment output contract")
    return {
        "feature_set_id": feature_set["feature_set_id"],
        "decision_ts": decision_ts,
        "rows": [dict(_mapping(item, "parity row")) for item in rows],
        "expected_outputs": normalized_expected,
        "expected_outputs_digest": f"sha256:{canonical_json_hash(normalized_expected)}",
    }


def _resolve_manifest(
    store: ResearchArtifactStore,
    *,
    deployment_id: str | None,
    deployment_uri: str | None,
    inline: Mapping[str, Any] | None,
) -> Mapping[str, Any]:
    selected = [bool(deployment_id), bool(deployment_uri), inline is not None]
    if sum(selected) != 1:
        raise ValueError("exactly one deployment manifest input is required")
    if inline is not None:
        manifest = dict(inline)
        deployment_id = str(manifest.get("deployment_id") or "").strip()
        if not deployment_id:
            raise ValueError("inline deployment manifest requires deployment_id")
        persisted = load_artifact_ref(store, ML_DEPLOYMENT_MANIFEST, deployment_id)
        if persisted != manifest:
            raise ValueError("inline deployment manifest does not match persisted canonical content")
        return persisted
    return load_artifact_ref(store, ML_DEPLOYMENT_MANIFEST, str(deployment_uri or deployment_id or ""))


def _snapshot(payload: Mapping[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    return {"sha256": f"sha256:{canonical_json_hash(normalized)}", "payload": normalized}


def _mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, MappingABC):
        raise ValueError(f"{label} must be a mapping")
    return {str(key): inner for key, inner in value.items()}


def _reject_credentials(environment: Mapping[str, Any]) -> None:
    forbidden = {"password", "secret", "token", "api_key", "credentials", "tracking_uri", "registry_uri"}
    found = sorted(name for name in environment if name.lower() in forbidden)
    if found:
        raise ValueError(f"deployment environment cannot contain credentials or provider locations: {found}")


def _error(command: str, code: str, message: str) -> ApplicationResult:
    return error_result(command=command, code=code, message=message)
