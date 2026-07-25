"""Session-start resolution from ML evidence to provider-neutral runtime bindings."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from trader.predictions import InferencePolicy, PredictionRuntimeResolver, RuntimePredictionBinding
from trader_research.foundation import PredictionMapperCatalog, ResearchArtifactStore, json_payload_hash
from trader_standard.predictions import BarFeatureProvider

from .adapters import InferenceAdapterRegistry
from .deployment import load_passed_deployment


@dataclass(frozen=True)
class ArtifactPredictionRuntimeResolver(PredictionRuntimeResolver):
    """Resolve one canonical strategy binding exactly once at session composition."""

    artifact_store: ResearchArtifactStore
    adapter_registry: InferenceAdapterRegistry
    mapper_catalog: PredictionMapperCatalog

    def resolve(
        self,
        *,
        binding: Mapping[str, object],
        symbols: Sequence[str],
        asset_class: str,
        timeframe: str,
    ) -> RuntimePredictionBinding:
        """Revalidate lineage, load the pinned model, and construct runtime dependencies."""
        validation_id = str(binding.get("deployment_validation_id") or "").strip()
        manifest, report = load_passed_deployment(self.artifact_store, validation_id)
        if str(report.get("validation_id") or "") != validation_id:
            raise ValueError("prediction binding deployment validation identity drifted")
        if str(manifest.get("deployment_id") or "") != binding.get("deployment_id"):
            raise ValueError("prediction binding deployment identity drifted")
        manifest_hash = f"sha256:{json_payload_hash(manifest)}"
        if manifest_hash != binding.get("deployment_manifest_hash"):
            raise ValueError("prediction binding deployment manifest drifted")
        model = _mapping(_mapping(manifest["model_version"], "model_version")["payload"], "model payload")
        feature_set = _mapping(
            _mapping(manifest["feature_set"], "feature_set")["payload"],
            "feature set payload",
        )
        if model.get("model_version_id") != binding.get("model_version_id"):
            raise ValueError("prediction binding model version drifted")
        if feature_set.get("feature_set_id") != binding.get("feature_set_id"):
            raise ValueError("prediction binding feature set drifted")
        profile = _mapping(manifest["adapter_profile"], "adapter_profile")
        adapter = self.adapter_registry.get(str(profile["profile_name"]))
        if adapter.profile().to_dict() != profile:
            raise ValueError("prediction inference adapter profile drifted")
        if not adapter.profile().available:
            raise ValueError(adapter.profile().reason or "prediction inference adapter is unavailable")
        if manifest.get("decision_scope") != binding.get("decision_scope"):
            raise ValueError("prediction binding decision scope drifted")
        if manifest.get("inference_scope") != binding.get("inference_scope"):
            raise ValueError("prediction binding inference scope drifted")
        policy = InferencePolicy(**dict(manifest.get("inference_policy") or {}))
        if policy.failure_action == "validated_fallback":
            raise ValueError("validated prediction fallbacks require an explicitly configured runtime resolver")
        mapper = self.mapper_catalog.build_mapper(
            _mapping(binding.get("mapper"), "prediction mapper")
        )
        feature_provider = BarFeatureProvider(
            feature_set=feature_set,
            decision_scope=str(binding["decision_scope"]),
        )
        predictor = adapter.build_predictor(manifest)
        return RuntimePredictionBinding(
            binding_name=str(binding["name"]),
            deployment_id=str(binding["deployment_id"]),
            deployment_validation_id=validation_id,
            output_names=tuple(
                str(item["name"])
                for item in _sequence_of_mappings(binding.get("selected_outputs"), "selected_outputs")
            ),
            output_contract=tuple(
                _sequence_of_mappings(binding.get("selected_outputs"), "selected_outputs")
            ),
            decision_scope=str(binding["decision_scope"]),
            symbols=tuple(str(item).strip().upper() for item in symbols),
            asset_class=str(asset_class),
            timeframe=str(timeframe),
            feature_provider=feature_provider,
            predictor=predictor,
            mapper=mapper,
            policy=policy,
        )


def _mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be a mapping")
    return {str(key): item for key, item in value.items()}


def _sequence_of_mappings(value: object, label: str) -> tuple[dict[str, Any], ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{label} must be a sequence")
    return tuple(_mapping(item, f"{label} item") for item in value)
