"""Maintained versioned mappers from raw predictions to strategy inputs."""

from __future__ import annotations

from collections.abc import Mapping as MappingABC, Sequence as SequenceABC
from dataclasses import dataclass
import math
from typing import Any, Mapping, Sequence

from trader.predictions import PredictionBatch, PredictionMapper, StrategyPrediction, canonical_json_hash


@dataclass(frozen=True)
class _MapperDefinition:
    mapper_id: str
    consumer_kinds: tuple[str, ...]
    implementation_digest: str


_DEFINITIONS = {
    "identity_numeric:v1": _MapperDefinition(
        mapper_id="identity_numeric:v1",
        consumer_kinds=("directional", "ranking"),
        implementation_digest="sha256:identity-numeric-v1",
    ),
    "probability_threshold:v1": _MapperDefinition(
        mapper_id="probability_threshold:v1",
        consumer_kinds=("directional", "gating"),
        implementation_digest="sha256:probability-threshold-v1",
    ),
    "target_weight:v1": _MapperDefinition(
        mapper_id="target_weight:v1",
        consumer_kinds=("allocation",),
        implementation_digest="sha256:target-weight-v1",
    ),
    "categorical_regime:v1": _MapperDefinition(
        mapper_id="categorical_regime:v1",
        consumer_kinds=("regime", "gating"),
        implementation_digest="sha256:categorical-regime-v1",
    ),
}


class MaintainedPredictionMapperCatalog:
    """Resolve and construct only maintained, version-pinned mappers."""

    def resolve_configuration(
        self,
        *,
        mapper_id: str,
        consumer_kind: str,
        output_contract: Sequence[Mapping[str, Any]],
        parameters: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        """Validate mapper compatibility and return immutable evidence."""
        try:
            definition = _DEFINITIONS[str(mapper_id)]
        except KeyError as exc:
            raise ValueError(f"unknown maintained prediction mapper: {mapper_id}") from exc
        if consumer_kind not in definition.consumer_kinds:
            raise ValueError(f"mapper {mapper_id} does not support consumer_kind {consumer_kind}")
        contracts = _normalize_output_contract(output_contract)
        _validate_semantics(definition.mapper_id, contracts[0])
        normalized_parameters = _normalize_parameters(definition.mapper_id, parameters)
        identity = {
            "mapper_id": definition.mapper_id,
            "implementation_digest": definition.implementation_digest,
            "consumer_kind": consumer_kind,
            "output_contract": contracts,
            "parameters": normalized_parameters,
        }
        return {**identity, "configuration_digest": f"sha256:{canonical_json_hash(identity)}"}

    def build_mapper(self, snapshot: Mapping[str, Any]) -> PredictionMapper:
        """Revalidate one snapshot and construct its runtime mapper."""
        expected = self.resolve_configuration(
            mapper_id=str(snapshot.get("mapper_id") or ""),
            consumer_kind=str(snapshot.get("consumer_kind") or ""),
            output_contract=_sequence(snapshot.get("output_contract"), "output_contract"),
            parameters=_mapping(snapshot.get("parameters") or {}, "parameters"),
        )
        if dict(expected) != dict(snapshot):
            raise ValueError("prediction mapper snapshot drifted")
        mapper_id = str(expected["mapper_id"])
        if mapper_id == "identity_numeric:v1":
            return _IdentityNumericMapper(expected)
        if mapper_id == "probability_threshold:v1":
            return _ProbabilityThresholdMapper(expected)
        if mapper_id == "target_weight:v1":
            return _TargetWeightMapper(expected)
        if mapper_id == "categorical_regime:v1":
            return _CategoricalRegimeMapper(expected)
        raise ValueError(f"unknown maintained prediction mapper: {mapper_id}")


class _BaseMapper:
    def __init__(self, snapshot: Mapping[str, Any]) -> None:
        self._snapshot = dict(snapshot)

    @property
    def mapper_id(self) -> str:
        return str(self._snapshot["mapper_id"])

    @property
    def parameters(self) -> Mapping[str, object]:
        return dict(self._snapshot["parameters"])

    @property
    def _output_name(self) -> str:
        return str(self._snapshot["output_contract"][0]["name"])

    @property
    def _target_name(self) -> str:
        return str(self.parameters["target_name"])

    def _matching(self, batch: PredictionBatch):
        return tuple(item for item in batch.observations if item.output_name == self._output_name)


class _IdentityNumericMapper(_BaseMapper):
    def map_predictions(self, batch: PredictionBatch) -> Sequence[StrategyPrediction]:
        return tuple(
            StrategyPrediction(
                name=self._target_name,
                value=_finite_number(item.value, self._output_name),
                symbol=item.symbol,
                source_output_names=(item.output_name,),
            )
            for item in self._matching(batch)
        )


class _ProbabilityThresholdMapper(_BaseMapper):
    def map_predictions(self, batch: PredictionBatch) -> Sequence[StrategyPrediction]:
        lower = float(self.parameters["short_threshold"])
        upper = float(self.parameters["long_threshold"])
        output: list[StrategyPrediction] = []
        for item in self._matching(batch):
            value = _finite_number(item.value, self._output_name)
            direction = 1.0 if value >= upper else -1.0 if value <= lower else 0.0
            output.append(
                StrategyPrediction(
                    name=self._target_name,
                    value=direction,
                    symbol=item.symbol,
                    source_output_names=(item.output_name,),
                    metadata={"raw_probability": value},
                )
            )
        return tuple(output)


class _TargetWeightMapper(_BaseMapper):
    def map_predictions(self, batch: PredictionBatch) -> Sequence[StrategyPrediction]:
        minimum = float(self.parameters["min_weight"])
        maximum = float(self.parameters["max_weight"])
        output: list[StrategyPrediction] = []
        for item in self._matching(batch):
            value = _finite_number(item.value, self._output_name)
            if value < minimum or value > maximum:
                raise ValueError(f"target weight {value} is outside validated mapper bounds")
            output.append(
                StrategyPrediction(
                    name=self._target_name,
                    value=value,
                    symbol=item.symbol,
                    source_output_names=(item.output_name,),
                )
            )
        return tuple(output)


class _CategoricalRegimeMapper(_BaseMapper):
    def map_predictions(self, batch: PredictionBatch) -> Sequence[StrategyPrediction]:
        return tuple(
            StrategyPrediction(
                name=self._target_name,
                value=item.value,
                symbol=item.symbol,
                source_output_names=(item.output_name,),
            )
            for item in self._matching(batch)
        )


def _normalize_output_contract(value: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    contracts = [dict(item) for item in value]
    if len(contracts) != 1:
        raise ValueError("maintained prediction mappers currently require exactly one selected output")
    item = contracts[0]
    required = ("name", "semantics", "horizon", "shape")
    if any(not str(item.get(name) or "").strip() for name in required):
        raise ValueError("prediction mapper output contract is incomplete")
    if item["shape"] != "scalar":
        raise ValueError("maintained prediction mappers currently require scalar outputs")
    return [
        {
            "name": str(item["name"]),
            "semantics": str(item["semantics"]),
            "horizon": str(item["horizon"]),
            "shape": "scalar",
            "dtype": str(item.get("dtype") or "float64"),
            "units": str(item.get("units") or "") or None,
            "nullable": bool(item.get("nullable", False)),
        }
    ]


def _normalize_parameters(mapper_id: str, value: Mapping[str, Any]) -> dict[str, object]:
    parameters = dict(value)
    if mapper_id == "identity_numeric:v1":
        allowed = {"target_name"}
        defaults: dict[str, object] = {"target_name": "prediction"}
    elif mapper_id == "probability_threshold:v1":
        allowed = {"target_name", "short_threshold", "long_threshold"}
        defaults = {"target_name": "direction", "short_threshold": 0.4, "long_threshold": 0.6}
    elif mapper_id == "target_weight:v1":
        allowed = {"target_name", "min_weight", "max_weight"}
        defaults = {"target_name": "target_weight", "min_weight": -1.0, "max_weight": 1.0}
    else:
        allowed = {"target_name"}
        defaults = {"target_name": "regime"}
    unknown = sorted(set(parameters).difference(allowed))
    if unknown:
        raise ValueError(f"unknown {mapper_id} parameters: {unknown}")
    normalized = {**defaults, **parameters}
    target_name = str(normalized["target_name"] or "").strip()
    if not target_name:
        raise ValueError("prediction mapper target_name is required")
    normalized["target_name"] = target_name
    if mapper_id == "probability_threshold:v1":
        lower = _bounded_number(normalized["short_threshold"], "short_threshold", 0.0, 1.0)
        upper = _bounded_number(normalized["long_threshold"], "long_threshold", 0.0, 1.0)
        if lower >= upper:
            raise ValueError("short_threshold must be below long_threshold")
        normalized.update({"short_threshold": lower, "long_threshold": upper})
    elif mapper_id == "target_weight:v1":
        minimum = _bounded_number(normalized["min_weight"], "min_weight", -1.0, 1.0)
        maximum = _bounded_number(normalized["max_weight"], "max_weight", -1.0, 1.0)
        if minimum >= maximum:
            raise ValueError("min_weight must be below max_weight")
        normalized.update({"min_weight": minimum, "max_weight": maximum})
    return normalized


def _validate_semantics(mapper_id: str, contract: Mapping[str, Any]) -> None:
    semantics = str(contract["semantics"])
    if mapper_id == "probability_threshold:v1" and semantics not in {
        "probability",
        "class_probability",
    }:
        raise ValueError("probability_threshold:v1 requires probability semantics")
    if mapper_id == "target_weight:v1" and semantics != "target_weight":
        raise ValueError("target_weight:v1 requires target_weight semantics")
    if mapper_id == "categorical_regime:v1" and semantics != "regime":
        raise ValueError("categorical_regime:v1 requires regime semantics")


def _finite_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise ValueError(f"prediction {label} must be finite numeric content")
    return float(value)


def _bounded_number(value: object, label: str, minimum: float, maximum: float) -> float:
    number = _finite_number(value, label)
    if number < minimum or number > maximum:
        raise ValueError(f"{label} must be between {minimum} and {maximum}")
    return number


def _mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, MappingABC):
        raise ValueError(f"{label} must be a mapping")
    return {str(key): item for key, item in value.items()}


def _sequence(value: object, label: str) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, SequenceABC) or isinstance(value, (str, bytes)):
        raise ValueError(f"{label} must be a sequence")
    return tuple(_mapping(item, f"{label} item") for item in value)
