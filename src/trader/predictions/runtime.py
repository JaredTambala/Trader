"""Runtime composition and bounded event evidence for model predictions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from typing import Mapping, Protocol, Sequence

from trader.event_store import EventStore

from .domain import (
    DECISION_SCOPES,
    FeatureBatch,
    InferencePolicy,
    PredictionBatch,
    PredictionObservation,
    PredictionRequest,
    StrategyPrediction,
    canonical_json_hash,
)
from .protocols import FeatureProvider, PredictionMapper, Predictor, ValidatedPredictionFallback


class PredictionRuntimeError(RuntimeError):
    """Raised when fail-closed inference cannot produce valid strategy inputs."""


@dataclass(frozen=True)
class PredictionDecision:
    """Raw and mapped evidence returned to a strategy for one decision."""

    binding_name: str
    deployment_id: str
    deployment_validation_id: str
    feature_batch: FeatureBatch
    prediction_batch: PredictionBatch
    strategy_inputs: tuple[StrategyPrediction, ...]
    prediction_event_ids: tuple[str, ...]
    mapper_id: str
    mapper_parameters: Mapping[str, object]


@dataclass(frozen=True)
class RuntimePredictionBinding:
    """Resolved provider-neutral predictor dependency injected into a strategy."""

    binding_name: str
    deployment_id: str
    deployment_validation_id: str
    output_names: tuple[str, ...]
    output_contract: tuple[Mapping[str, object], ...]
    decision_scope: str
    symbols: tuple[str, ...]
    asset_class: str
    timeframe: str
    feature_provider: FeatureProvider
    predictor: Predictor
    mapper: PredictionMapper
    policy: InferencePolicy
    fallback: ValidatedPredictionFallback | None = None

    def __post_init__(self) -> None:
        """Reject incompatible or incomplete runtime composition."""
        if not self.binding_name.strip() or not self.deployment_id.strip() or not self.deployment_validation_id.strip():
            raise ValueError("runtime prediction binding identity is required")
        if not self.output_names or len(set(self.output_names)) != len(self.output_names):
            raise ValueError("runtime prediction binding requires unique output names")
        contract_names = tuple(str(item.get("name") or "") for item in self.output_contract)
        if contract_names != self.output_names:
            raise ValueError("runtime prediction output contract must match bound output order")
        if self.decision_scope not in DECISION_SCOPES:
            raise ValueError(f"unsupported prediction decision scope: {self.decision_scope}")
        if self.feature_provider.decision_scope != self.decision_scope:
            raise ValueError("feature provider decision scope does not match binding")
        if not self.symbols:
            raise ValueError("runtime prediction binding requires symbols")
        if self.policy.failure_action == "validated_fallback":
            if self.fallback is None or self.fallback.validation_ref != self.policy.fallback_ref:
                raise ValueError("runtime fallback does not match the validated policy reference")
        elif self.fallback is not None:
            raise ValueError("runtime fallback is only allowed by validated_fallback policy")

    @property
    def required_lookback(self) -> int:
        """Return the feature provider warmup requirement."""
        return self.feature_provider.required_lookback

    def evaluate(
        self,
        *,
        run_id: str,
        cycle_id: str,
        decision_ts: datetime,
        event_store: EventStore,
        symbols: Sequence[str] | None = None,
    ) -> PredictionDecision:
        """Build features, predict, record bounded evidence, and map strategy inputs."""
        requested_symbols = tuple(str(item).strip().upper() for item in (symbols or self.symbols) if str(item).strip())
        if self.decision_scope == "universe_snapshot" and requested_symbols != self.symbols:
            raise PredictionRuntimeError("universe_snapshot inference requires the complete ordered symbol universe")
        feature_batch = self.feature_provider.build(
            decision_ts=decision_ts,
            symbols=requested_symbols,
            asset_class=self.asset_class,
            timeframe=self.timeframe,
            event_store=event_store,
        )
        request = PredictionRequest(
            run_id=run_id,
            cycle_id=cycle_id,
            feature_batch=feature_batch,
            requested_outputs=self.output_names,
            timeout_ms=self.policy.timeout_ms,
        )
        prediction_batch: PredictionBatch | None = None
        try:
            self._validate_feature_batch(feature_batch, requested_symbols)
            prediction_batch = self.predictor.predict(request)
            self._validate_prediction_batch(prediction_batch, feature_batch)
        except Exception as exc:
            return self._handle_failure(
                run_id=run_id,
                cycle_id=cycle_id,
                decision_ts=decision_ts,
                event_store=event_store,
                feature_batch=feature_batch,
                symbols=requested_symbols,
                reason=str(exc),
                status=(
                    prediction_batch.status
                    if prediction_batch is not None
                    and prediction_batch.status in {"stale", "timeout", "skipped"}
                    else "error"
                ),
                latency_ms=(prediction_batch.latency_ms if prediction_batch is not None else 0.0),
            )
        event_ids = self._record_batch(event_store, run_id, cycle_id, prediction_batch)
        strategy_inputs = tuple(self.mapper.map_predictions(prediction_batch))
        return PredictionDecision(
            binding_name=self.binding_name,
            deployment_id=self.deployment_id,
            deployment_validation_id=self.deployment_validation_id,
            feature_batch=feature_batch,
            prediction_batch=prediction_batch,
            strategy_inputs=strategy_inputs,
            prediction_event_ids=event_ids,
            mapper_id=self.mapper.mapper_id,
            mapper_parameters=dict(self.mapper.parameters),
        )

    def _validate_feature_batch(self, batch: FeatureBatch, symbols: Sequence[str]) -> None:
        if batch.feature_set_id != self.feature_provider.feature_set_id:
            raise PredictionRuntimeError("feature provider returned a different feature_set_id")
        if batch.feature_set_digest != self.feature_provider.feature_set_digest:
            raise PredictionRuntimeError("feature provider returned a different feature_set_digest")
        if batch.decision_ts is None:
            raise PredictionRuntimeError("feature batch decision timestamp is missing")
        if self.policy.require_complete_universe and tuple(batch.symbols) != tuple(symbols):
            raise PredictionRuntimeError("feature batch does not cover the complete requested universe")
        if batch.missing_features:
            raise PredictionRuntimeError(f"feature batch has missing features: {list(batch.missing_features)}")
        if batch.stale_features:
            raise PredictionRuntimeError(f"feature batch has stale features: {list(batch.stale_features)}")
        if self.policy.max_feature_age_seconds is not None:
            ages = [(batch.decision_ts - row.availability_ts).total_seconds() for row in batch.rows]
            if any(age > self.policy.max_feature_age_seconds for age in ages):
                raise PredictionRuntimeError("feature batch exceeds max_feature_age_seconds")

    def _validate_prediction_batch(self, batch: PredictionBatch, feature_batch: FeatureBatch) -> None:
        if batch.model_identity != self.predictor.identity:
            raise PredictionRuntimeError("predictor returned a different model identity")
        if batch.feature_batch_hash != feature_batch.input_hash:
            raise PredictionRuntimeError("prediction result feature hash does not match its request")
        if batch.decision_ts != feature_batch.decision_ts:
            raise PredictionRuntimeError("prediction result decision timestamp does not match its request")
        if batch.status != "success":
            raise PredictionRuntimeError(batch.error or f"prediction status is {batch.status}")
        returned = {item.output_name for item in batch.observations}
        if returned != set(self.output_names):
            raise PredictionRuntimeError("prediction result outputs do not match the binding")
        contract_by_name = {
            str(item["name"]): item for item in self.output_contract
        }
        for observation in batch.observations:
            contract = contract_by_name[observation.output_name]
            if observation.semantics != contract.get("semantics"):
                raise PredictionRuntimeError(
                    f"prediction output {observation.output_name} semantics drifted"
                )
            if observation.horizon != contract.get("horizon"):
                raise PredictionRuntimeError(
                    f"prediction output {observation.output_name} horizon drifted"
                )
            if observation.units != contract.get("units"):
                raise PredictionRuntimeError(
                    f"prediction output {observation.output_name} units drifted"
                )
            _validate_observation_shape(observation, contract)
        symbol_outputs = {
            (item.symbol, item.output_name) for item in batch.observations if item.symbol is not None
        }
        if symbol_outputs:
            expected = {
                (symbol, output_name)
                for symbol in feature_batch.symbols
                for output_name in self.output_names
            }
            if symbol_outputs != expected:
                raise PredictionRuntimeError(
                    "prediction result does not cover every requested symbol and output"
                )
        elif len(batch.observations) != len(self.output_names):
            raise PredictionRuntimeError(
                "global prediction result must contain each requested output exactly once"
            )

    def _handle_failure(
        self,
        *,
        run_id: str,
        cycle_id: str,
        decision_ts: datetime,
        event_store: EventStore,
        feature_batch: FeatureBatch,
        symbols: Sequence[str],
        reason: str,
        status: str,
        latency_ms: float,
    ) -> PredictionDecision:
        failed = PredictionBatch(
            model_identity=self.predictor.identity,
            feature_batch_hash=feature_batch.input_hash,
            decision_ts=decision_ts,
            observations=(),
            status=status,
            latency_ms=latency_ms,
            coverage={"requested_symbols": list(symbols), "returned_symbols": []},
            error=reason,
        )
        event_ids = self._record_batch(event_store, run_id, cycle_id, failed)
        if self.policy.failure_action == "fail_closed":
            raise PredictionRuntimeError(f"prediction failed closed: {reason}")
        if self.policy.failure_action == "skip_decision":
            inputs: tuple[StrategyPrediction, ...] = ()
        else:
            if self.fallback is None:
                raise PredictionRuntimeError("validated fallback is unavailable")
            inputs = tuple(self.fallback.fallback(decision_ts=decision_ts, symbols=symbols, reason=reason))
        return PredictionDecision(
            binding_name=self.binding_name,
            deployment_id=self.deployment_id,
            deployment_validation_id=self.deployment_validation_id,
            feature_batch=feature_batch,
            prediction_batch=failed,
            strategy_inputs=inputs,
            prediction_event_ids=event_ids,
            mapper_id=self.mapper.mapper_id,
            mapper_parameters=dict(self.mapper.parameters),
        )

    def _record_batch(
        self,
        event_store: EventStore,
        run_id: str,
        cycle_id: str,
        batch: PredictionBatch,
    ) -> tuple[str, ...]:
        observations: Sequence[PredictionObservation | None] = batch.observations or (None,)
        event_ids: list[str] = []
        for observation in observations:
            identity = {
                "run_id": run_id,
                "cycle_id": cycle_id,
                "deployment_id": self.deployment_id,
                "feature_batch_hash": batch.feature_batch_hash,
                "symbol": observation.symbol if observation else None,
                "output_name": observation.output_name if observation else None,
                "status": batch.status,
            }
            event_id = f"prediction_event_{canonical_json_hash(identity)[:24]}"
            event_store.record_event(
                "prediction_events",
                {
                    "prediction_event_id": event_id,
                    "run_id": run_id,
                    "session_id": run_id,
                    "cycle_id": cycle_id,
                    "deployment_id": self.deployment_id,
                    "deployment_validation_id": self.deployment_validation_id,
                    "model_version_id": batch.model_identity.model_version_id,
                    "feature_set_id": self.feature_provider.feature_set_id,
                    "feature_batch_hash": batch.feature_batch_hash,
                    "decision_ts": batch.decision_ts,
                    "symbol": observation.symbol if observation else None,
                    "output_name": observation.output_name if observation else None,
                    "semantics": observation.semantics if observation else None,
                    "horizon": observation.horizon if observation else None,
                    "value_payload": json.dumps(observation.to_dict(), sort_keys=True) if observation else None,
                    "latency_ms": batch.latency_ms,
                    "status": batch.status,
                    "error_message": batch.error,
                    "payload": json.dumps(
                        {
                            "coverage": dict(batch.coverage),
                            "warnings": list(batch.warnings),
                            "model_identity": batch.model_identity.to_dict(),
                        },
                        sort_keys=True,
                    ),
                },
            )
            event_ids.append(event_id)
        return tuple(event_ids)


class PredictionRuntimeResolver(Protocol):
    """Resolve canonical strategy binding evidence into runtime dependencies."""

    def resolve(
        self,
        *,
        binding: Mapping[str, object],
        symbols: Sequence[str],
        asset_class: str,
        timeframe: str,
    ) -> RuntimePredictionBinding:
        """Build one immutable runtime binding at session start."""


def _validate_observation_shape(
    observation: PredictionObservation,
    contract: Mapping[str, object],
) -> None:
    value = observation.value
    if value is None:
        if not bool(contract.get("nullable", False)):
            raise PredictionRuntimeError(
                f"prediction output {observation.output_name} is not nullable"
            )
        return
    shape = str(contract.get("shape") or "scalar")
    structured = isinstance(value, Mapping) or (
        isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))
    )
    if shape == "scalar" and structured:
        raise PredictionRuntimeError(
            f"prediction output {observation.output_name} must be scalar"
        )
    if shape == "structured" and not structured:
        raise PredictionRuntimeError(
            f"prediction output {observation.output_name} must be structured"
        )
