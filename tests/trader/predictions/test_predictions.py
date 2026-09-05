"""Contracts for provider-neutral prediction values and runtime binding.

Subject: Point-in-time feature identity, prediction evidence, mapping, coverage, semantics, and failure policy.
Level: Deterministic domain and in-process runtime unit contracts.
Collaborators: Real prediction contracts and binding with fixed feature providers, predictors, mappers, and store.
Guarantees: Model outputs are validated and recorded before strategy mapping, with fail-closed evidence on ambiguity.
Non-goals: Loading MLflow models, feature engineering, strategy profitability, persistence, or model quality.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Mapping, Sequence

import pytest

from trader.event_store import EventStore
from trader.predictions import (
    FeatureBatch,
    FeatureColumn,
    FeatureRow,
    InferencePolicy,
    ModelIdentity,
    PredictionBatch,
    PredictionObservation,
    PredictionRequest,
    PredictionRuntimeError,
    RuntimePredictionBinding,
    StrategyPrediction,
)


NOW = datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc)


class RecordingStore(EventStore):
    """Capture append-only events without a database."""

    def __init__(self) -> None:
        self.events: list[tuple[str, Mapping[str, object]]] = []

    def record_event(self, event_type: str, payload: Mapping[str, object]) -> None:
        self.events.append((event_type, dict(payload)))


class FixtureFeatureProvider:
    """Build one deterministic close feature per requested symbol."""

    feature_set_id = "feature_set_fixture"
    feature_set_digest = "sha256:features"
    required_lookback = 2
    decision_scope = "universe_snapshot"

    def build(
        self,
        *,
        decision_ts: datetime,
        symbols: Sequence[str],
        asset_class: str,
        timeframe: str,
        event_store: EventStore,
    ) -> FeatureBatch:
        del asset_class, timeframe, event_store
        return FeatureBatch.build(
            feature_set_id=self.feature_set_id,
            feature_set_digest=self.feature_set_digest,
            decision_ts=decision_ts,
            schema=(FeatureColumn("close", "float64"),),
            rows=tuple(
                FeatureRow(
                    symbol=symbol,
                    as_of_ts=decision_ts,
                    availability_ts=decision_ts,
                    values={"close": float(index + 1)},
                )
                for index, symbol in enumerate(symbols)
            ),
        )


class FixturePredictor:
    """Return one expected-return output per feature row."""

    identity = ModelIdentity(
        registered_model_name="fixture",
        model_version="7",
        model_version_id="ml_model_version_fixture",
        model_digest="sha256:model",
        signature_digest="sha256:signature",
        source_run_id="mlflow_run_fixture",
        adapter_profile="fixture",
        adapter_version="1",
    )

    def predict(self, request: PredictionRequest) -> PredictionBatch:
        return PredictionBatch(
            model_identity=self.identity,
            feature_batch_hash=request.feature_batch.input_hash,
            decision_ts=request.feature_batch.decision_ts,
            observations=tuple(
                PredictionObservation(
                    symbol=row.symbol,
                    output_name="alpha",
                    semantics="expected_return",
                    value=float(row.values["close"]) / 100.0,
                    horizon="1bar",
                    units="return",
                )
                for row in request.feature_batch.rows
            ),
            status="success",
            latency_ms=2.5,
            coverage={"requested_symbols": list(request.feature_batch.symbols)},
        )


class FailingPredictor(FixturePredictor):
    """Raise a deterministic inference failure."""

    def predict(self, request: PredictionRequest) -> PredictionBatch:
        del request
        raise RuntimeError("model unavailable")


class TimeoutPredictor(FixturePredictor):
    """Return an explicit bounded timeout result."""

    def predict(self, request: PredictionRequest) -> PredictionBatch:
        return PredictionBatch(
            model_identity=self.identity,
            feature_batch_hash=request.feature_batch.input_hash,
            decision_ts=request.feature_batch.decision_ts,
            observations=(),
            status="timeout",
            latency_ms=float(request.timeout_ms),
            error="inference timeout exceeded",
        )


class IncompletePredictor(FixturePredictor):
    """Return only one symbol from a two-symbol universe."""

    def predict(self, request: PredictionRequest) -> PredictionBatch:
        return PredictionBatch(
            model_identity=self.identity,
            feature_batch_hash=request.feature_batch.input_hash,
            decision_ts=request.feature_batch.decision_ts,
            observations=(
                PredictionObservation(
                    symbol="AAA",
                    output_name="alpha",
                    semantics="expected_return",
                    value=0.01,
                    horizon="1bar",
                    units="return",
                ),
            ),
            status="success",
            latency_ms=1.0,
        )


class WrongSemanticsPredictor(FixturePredictor):
    """Return a renamed meaning under the same output name."""

    def predict(self, request: PredictionRequest) -> PredictionBatch:
        return PredictionBatch(
            model_identity=self.identity,
            feature_batch_hash=request.feature_batch.input_hash,
            decision_ts=request.feature_batch.decision_ts,
            observations=tuple(
                PredictionObservation(
                    symbol=row.symbol,
                    output_name="alpha",
                    semantics="rank_score",
                    value=0.1,
                    horizon="1bar",
                    units="return",
                )
                for row in request.feature_batch.rows
            ),
            status="success",
            latency_ms=1.0,
        )


class IdentityMapper:
    """Map expected-return observations to strategy alpha inputs."""

    mapper_id = "identity_mapper:1"
    parameters: Mapping[str, object] = {"output_name": "alpha"}

    def map_predictions(self, batch: PredictionBatch) -> Sequence[StrategyPrediction]:
        return tuple(
            StrategyPrediction(
                name="alpha",
                value=item.value,
                symbol=item.symbol,
                source_output_names=(item.output_name,),
            )
            for item in batch.observations
        )


def _binding(
    *, predictor: FixturePredictor | None = None, failure_action: str = "fail_closed"
) -> RuntimePredictionBinding:
    return RuntimePredictionBinding(
        binding_name="alpha_model",
        deployment_id="ml_deployment_fixture",
        deployment_validation_id="ml_deployment_validation_fixture",
        output_names=("alpha",),
        output_contract=(
            {
                "name": "alpha",
                "semantics": "expected_return",
                "horizon": "1bar",
                "shape": "scalar",
                "units": "return",
                "nullable": False,
            },
        ),
        decision_scope="universe_snapshot",
        symbols=("AAA", "BBB"),
        asset_class="stocks",
        timeframe="1Min",
        feature_provider=FixtureFeatureProvider(),
        predictor=predictor or FixturePredictor(),
        mapper=IdentityMapper(),
        policy=InferencePolicy(failure_action=failure_action),
    )


def test_feature_batch_hash_covers_ordered_point_in_time_values() -> None:
    """Ensure feature identity changes with ordered values, timing, or availability evidence."""
    provider = FixtureFeatureProvider()

    first = provider.build(
        decision_ts=NOW,
        symbols=("AAA", "BBB"),
        asset_class="stocks",
        timeframe="1Min",
        event_store=RecordingStore(),
    )
    second = provider.build(
        decision_ts=NOW,
        symbols=("BBB", "AAA"),
        asset_class="stocks",
        timeframe="1Min",
        event_store=RecordingStore(),
    )

    assert first.input_hash.startswith("sha256:")
    assert first.input_hash != second.input_hash
    assert first.to_dict(include_values=False)["rows"] == [
        {
            "symbol": "AAA",
            "as_of_ts": NOW.isoformat(),
            "availability_ts": NOW.isoformat(),
        },
        {
            "symbol": "BBB",
            "as_of_ts": NOW.isoformat(),
            "availability_ts": NOW.isoformat(),
        },
    ]


def test_runtime_binding_records_raw_predictions_before_mapping() -> None:
    """Ensure canonical prediction events are recorded before strategy-specific mapping begins."""
    store = RecordingStore()

    decision = _binding().evaluate(
        run_id="run_1",
        cycle_id="cycle_1",
        decision_ts=NOW,
        event_store=store,
    )

    assert [item.symbol for item in decision.strategy_inputs] == ["AAA", "BBB"]
    assert [item.value for item in decision.strategy_inputs] == [0.01, 0.02]
    assert len(decision.prediction_event_ids) == 2
    assert all(event_type == "prediction_events" for event_type, _ in store.events)
    assert {payload["symbol"] for _, payload in store.events} == {"AAA", "BBB"}
    assert {payload["model_version_id"] for _, payload in store.events} == {
        "ml_model_version_fixture"
    }


def test_universe_binding_rejects_partial_symbol_callbacks() -> None:
    """Ensure universe-scoped models reject incomplete symbol callbacks before inference."""
    with pytest.raises(
        PredictionRuntimeError, match="complete ordered symbol universe"
    ):
        _binding().evaluate(
            run_id="run_1",
            cycle_id="cycle_1",
            decision_ts=NOW,
            event_store=RecordingStore(),
            symbols=("AAA",),
        )


def test_fail_closed_records_failure_and_raises() -> None:
    """Ensure fail-closed policy records predictor failure before raising a runtime error."""
    store = RecordingStore()

    with pytest.raises(PredictionRuntimeError, match="model unavailable"):
        _binding(predictor=FailingPredictor()).evaluate(
            run_id="run_1",
            cycle_id="cycle_1",
            decision_ts=NOW,
            event_store=store,
        )

    assert len(store.events) == 1
    assert store.events[0][1]["status"] == "error"
    assert store.events[0][1]["error_message"] == "model unavailable"


def test_skip_decision_records_failure_without_strategy_inputs() -> None:
    """Ensure skip policy preserves failure evidence while returning no strategy inputs."""
    decision = _binding(
        predictor=FailingPredictor(), failure_action="skip_decision"
    ).evaluate(
        run_id="run_1",
        cycle_id="cycle_1",
        decision_ts=NOW,
        event_store=RecordingStore(),
    )

    assert decision.prediction_batch.status == "error"
    assert decision.strategy_inputs == ()


def test_timeout_status_is_preserved_in_failure_evidence() -> None:
    """Ensure predictor timeouts retain their distinct status in recorded failure evidence."""
    store = RecordingStore()

    with pytest.raises(PredictionRuntimeError, match="inference timeout exceeded"):
        _binding(predictor=TimeoutPredictor()).evaluate(
            run_id="run_1",
            cycle_id="cycle_1",
            decision_ts=NOW,
            event_store=store,
        )

    assert store.events[0][1]["status"] == "timeout"
    assert store.events[0][1]["latency_ms"] == 1_000.0


def test_incomplete_prediction_coverage_fails_closed_with_evidence() -> None:
    """Ensure missing requested symbols produce evidence and prevent partial strategy decisions."""
    store = RecordingStore()

    with pytest.raises(PredictionRuntimeError, match="every requested symbol"):
        _binding(predictor=IncompletePredictor()).evaluate(
            run_id="run_1",
            cycle_id="cycle_1",
            decision_ts=NOW,
            event_store=store,
        )

    assert store.events[0][1]["status"] == "error"


def test_runtime_rejects_output_semantics_drift_with_failure_evidence() -> None:
    """Ensure changed output meaning fails closed with an inspectable semantics error."""
    store = RecordingStore()

    with pytest.raises(PredictionRuntimeError, match="semantics drifted"):
        _binding(predictor=WrongSemanticsPredictor()).evaluate(
            run_id="run_1",
            cycle_id="cycle_1",
            decision_ts=NOW,
            event_store=store,
        )

    assert store.events[0][1]["status"] == "error"


def test_prediction_values_reject_non_finite_content() -> None:
    """Ensure NaN and infinite prediction values fail at the domain boundary."""
    with pytest.raises(ValueError, match="finite JSON-compatible"):
        PredictionObservation(
            output_name="alpha",
            semantics="expected_return",
            value=float("nan"),
            horizon="1bar",
        )
