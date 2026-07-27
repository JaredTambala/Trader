"""End-to-end direct evidence chain for one model-backed strategy backtest."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Mapping

from trader.config import Config
from trader.predictions import (
    ModelIdentity,
    PredictionBatch,
    PredictionObservation,
    PredictionRequest,
    Predictor,
)
from trader_research.experiments import (
    create_backtest_specification,
    create_strategy_specification,
    register_strategy_implementation,
    run_backtest_specification,
    validate_backtest_specification,
    validate_strategy_implementation,
    validate_strategy_specification,
)
from trader_research.foundation import InMemoryResearchArtifactStore
from trader_research.governance.artifacts import (
    DOMAIN_OWNER_BY_ARTIFACT_TYPE,
    ML_FEATURE_SET_SPEC,
    ML_FEATURE_SET_VALIDATION_REPORT,
    ML_MODEL_VERSION_REF,
)
from trader_research.ml import (
    ArtifactPredictionDeploymentReader,
    ArtifactPredictionRuntimeResolver,
    InferenceAdapterProfile,
    InferenceAdapterRegistry,
    create_deployment_manifest,
    validate_deployment,
)
from trader_standard.predictions import MaintainedPredictionMapperCatalog
from tests.support.duckdb_store import DuckDBEventStore


MODEL_STRATEGY_SOURCE = '''
from trader_standard.strategies import build_prediction_driven_strategy


def build_strategy(**kwargs):
    return build_prediction_driven_strategy(**kwargs)
'''


class ReturnPredictor:
    """Return the declared point-in-time input as expected return."""

    identity = ModelIdentity(
        registered_model_name="return_model",
        model_version="1",
        model_version_id="model_version_1",
        model_digest="sha256:model",
        signature_digest="sha256:signature",
        source_run_id="training_run_1",
        adapter_profile="fixture_local",
        adapter_version="1",
    )

    def predict(self, request: PredictionRequest) -> PredictionBatch:
        return PredictionBatch(
            model_identity=self.identity,
            feature_batch_hash=request.feature_batch.input_hash,
            decision_ts=request.feature_batch.decision_ts,
            observations=tuple(
                PredictionObservation(
                    output_name="alpha",
                    semantics="expected_return",
                    value=float(row.values["return_1"]),
                    horizon="1bar",
                    symbol=row.symbol,
                    units="return",
                )
                for row in request.feature_batch.rows
            ),
            status="success",
            latency_ms=1.0,
            coverage={"requested_symbols": list(request.feature_batch.symbols)},
        )


class FixtureInferenceAdapter:
    """Qualified deterministic adapter used without MLflow in the direct graph."""

    _profile = InferenceAdapterProfile(
        profile_name="fixture_local",
        provider="fixture",
        adapter_version="1",
        configuration_digest="sha256:fixture",
        capabilities=("local_model",),
        available=True,
    )

    def profile(self) -> InferenceAdapterProfile:
        return self._profile

    def validate_deployment(self, manifest: Mapping[str, object]) -> Mapping[str, object]:
        del manifest
        return {"status": "passed", "parity": "fixture", "latency_ms": 1.0}

    def build_predictor(self, manifest: Mapping[str, object]) -> Predictor:
        del manifest
        return ReturnPredictor()


def _config(path: Path) -> Config:
    return Config(
        mode="once",
        strategy_type="model",
        strategy_id="model",
        strategy_timeframe="1Min",
        sma_short_window=2,
        sma_long_window=3,
        db_path=str(path),
        event_store="postgres",
        market_data_source="noop",
        market_data_asset_class="stocks",
        market_data_stock_feed="iex",
        market_data_symbols=("EURUSD",),
        market_data_max_age_seconds=60,
        alpaca_api_key="",
        alpaca_secret_key="",
        alpaca_data_base_url="https://data.alpaca.markets",
        alpaca_base_url="https://paper-api.alpaca.markets",
        pg_dsn="",
        pg_host="",
        pg_port=5432,
        pg_db="",
        pg_user="",
        pg_password="",
        buffered_event_store=False,
        buffer_flush_interval_ms=250,
        buffer_max_batch_size=500,
        buffer_max_queue_size=10000,
        buffer_block_on_full=True,
        log_signal_events=True,
        log_indicator_events=True,
        log_order_events=True,
        log_fill_events=True,
        log_position_snapshots=True,
        broker_type="noop",
    )


def _seed_ml_evidence(store: InMemoryResearchArtifactStore) -> str:
    artifacts = (
        (
            ML_MODEL_VERSION_REF,
            "model_version_1",
            {
                "artifact_type": ML_MODEL_VERSION_REF,
                "model_version_id": "model_version_1",
                "registered_model_name": "return_model",
                "model_version": "1",
                "model_digest": "sha256:model",
                "signature_digest": "sha256:signature",
                "source_run_id": "training_run_1",
                "model_uri": "fixture:/return_model/1",
                "status": "registered",
                "immutable": True,
            },
            "registered",
        ),
        (
            ML_FEATURE_SET_SPEC,
            "feature_set_1",
            {
                "artifact_type": ML_FEATURE_SET_SPEC,
                "feature_set_id": "feature_set_1",
                "feature_set_digest": "sha256:feature-set",
                "status": "created",
                "schema": [
                    {
                        "name": "return_1",
                        "dtype": "float64",
                        "nullable": False,
                        "transform": {
                            "kind": "simple_return",
                            "field": "close",
                            "periods": 1,
                            "lag": 0,
                        },
                    }
                ],
            },
            "created",
        ),
        (
            ML_FEATURE_SET_VALIDATION_REPORT,
            "feature_validation_1",
            {
                "artifact_type": ML_FEATURE_SET_VALIDATION_REPORT,
                "validation_id": "feature_validation_1",
                "feature_set_id": "feature_set_1",
                "feature_set_digest": "sha256:feature-set",
                "status": "passed",
                "valid": True,
                "blockers": [],
            },
            "passed",
        ),
    )
    for artifact_type, artifact_id, payload, status in artifacts:
        store.save_artifact(
            artifact_type=artifact_type,
            artifact_id=artifact_id,
            domain_owner=DOMAIN_OWNER_BY_ARTIFACT_TYPE[artifact_type],
            producer_tool="test_model_backtest_fixture",
            payload=payload,
            status=status,
        )
    registry = InferenceAdapterRegistry((FixtureInferenceAdapter(),))
    created = create_deployment_manifest(
        model_version_ref="model_version_1",
        feature_set_validation_ref="feature_validation_1",
        adapter_profile="fixture_local",
        output_contract=(
            {
                "name": "alpha",
                "semantics": "expected_return",
                "horizon": "1bar",
                "shape": "scalar",
                "units": "return",
            },
        ),
        inference_scope="per_symbol",
        inference_policy={"timeout_ms": 1_000, "failure_action": "fail_closed"},
        environment={"environment_digest": "sha256:fixture-env"},
        parity_fixture={
            "decision_ts": "2026-01-01T00:01:00+00:00",
            "rows": [
                {
                    "symbol": "EURUSD",
                    "as_of_ts": "2026-01-01T00:01:00+00:00",
                    "availability_ts": "2026-01-01T00:01:00+00:00",
                    "values": {"return_1": 0.01},
                }
            ],
            "expected_outputs": [
                {
                    "symbol": "EURUSD",
                    "output_name": "alpha",
                    "value": 0.01,
                }
            ],
        },
        artifact_store=store,
        adapter_registry=registry,
    )
    deployment_id = created.data["ml_deployment_manifest"]["deployment_id"]
    validated = validate_deployment(
        deployment_id=deployment_id,
        artifact_store=store,
        adapter_registry=registry,
    )
    assert validated.ok
    return str(validated.data["ml_deployment_validation_report"]["validation_id"])


def _record_bar(store: DuckDBEventStore, symbol: str, ts: datetime, close: float) -> None:
    store.record_event(
        "stock_bar_events",
        {
            "symbol": symbol,
            "timeframe": "1Min",
            "ts": ts,
            "ingested_at": ts,
            "open": close,
            "high": close,
            "low": close,
            "close": close,
            "volume": 100.0,
            "trade_count": 1.0,
            "vwap": close,
            "source": "fixture",
        },
    )


def test_model_deployment_binding_executes_backtest_with_prediction_lineage(tmp_path: Path) -> None:
    artifact_store = InMemoryResearchArtifactStore()
    deployment_validation_id = _seed_ml_evidence(artifact_store)
    adapter_registry = InferenceAdapterRegistry((FixtureInferenceAdapter(),))
    deployment_reader = ArtifactPredictionDeploymentReader(artifact_store)
    mapper_catalog = MaintainedPredictionMapperCatalog()
    runtime_resolver = ArtifactPredictionRuntimeResolver(
        artifact_store=artifact_store,
        adapter_registry=adapter_registry,
        mapper_catalog=mapper_catalog,
    )
    registered = register_strategy_implementation(
        name="prediction_driven",
        version="1",
        source_code=MODEL_STRATEGY_SOURCE,
        factory_name="build_strategy",
        parameter_schema={
            "type": "object",
            "properties": {
                "prediction_binding_name": {"type": "string", "default": "alpha_model"},
                "input_name": {"type": "string", "default": "alpha"},
                "consumer_kind": {"type": "string", "default": "directional"},
                "order_qty": {"type": "number", "default": 1.0, "minimum": 0.01},
                "decision_threshold": {"type": "number", "default": 0.0, "minimum": 0.0},
            },
            "required": [
                "prediction_binding_name",
                "input_name",
                "consumer_kind",
                "order_qty",
                "decision_threshold",
            ],
        },
        runtime_requirements={
            "prediction_requirements": [
                {
                    "name": "alpha_model",
                    "accepted_semantics": ["expected_return"],
                    "accepted_horizons": ["1bar"],
                    "accepted_output_shapes": ["scalar"],
                    "inference_scopes": ["per_symbol"],
                    "consumer_kind": "directional",
                }
            ]
        },
        artifact_store=artifact_store,
    )
    implementation_id = registered.data["implementation_version"]["implementation_version_id"]
    implementation_validation = validate_strategy_implementation(
        implementation_version_id=implementation_id,
        artifact_store=artifact_store,
    )
    assert implementation_validation.ok
    strategy_created = create_strategy_specification(
        implementation_validation_ref=implementation_validation.data[
            "implementation_validation_report"
        ]["validation_id"],
        parameters={
            "prediction_binding_name": "alpha_model",
            "input_name": "alpha",
            "consumer_kind": "directional",
            "order_qty": 1.0,
            "decision_threshold": 0.0,
        },
        prediction_bindings=(
            {
                "name": "alpha_model",
                "deployment_validation_ref": deployment_validation_id,
                "output_names": ["alpha"],
                "mapper_id": "identity_numeric:v1",
                "mapper_parameters": {"target_name": "alpha"},
            },
        ),
        prediction_deployment_reader=deployment_reader,
        prediction_mapper_catalog=mapper_catalog,
        artifact_store=artifact_store,
    )
    strategy_id = strategy_created.data["strategy_specification"]["strategy_specification_id"]
    strategy_validation = validate_strategy_specification(
        strategy_specification_id=strategy_id,
        prediction_deployment_reader=deployment_reader,
        prediction_mapper_catalog=mapper_catalog,
        artifact_store=artifact_store,
    )
    assert strategy_validation.ok

    event_store = DuckDBEventStore(str(tmp_path / "model-backtest.duckdb"))
    start = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    _record_bar(event_store, "EURUSD", start - timedelta(minutes=1), 101.0)
    _record_bar(event_store, "EURUSD", start, 100.0)
    _record_bar(event_store, "EURUSD", start + timedelta(minutes=1), 102.0)
    manifest = {
        "dataset_id": "dataset_model_backtest",
        "symbols": ["EURUSD"],
        "asset_class": "stocks",
        "timeframe": "1Min",
        "time_range": {"start": start.isoformat(), "end": (start + timedelta(minutes=1)).isoformat()},
        "total_rows": 2,
        "complete": True,
        "source_filter": None,
    }
    quality = {
        "symbols": ["EURUSD"],
        "asset_class": "stocks",
        "timeframe": "1Min",
        "time_range": manifest["time_range"],
        "complete": True,
    }
    backtest_created = create_backtest_specification(
        strategy_specification_validation_ref=strategy_validation.data[
            "strategy_specification_validation_report"
        ]["validation_id"],
        dataset_manifest=manifest,
        data_quality_report=quality,
        initial_cash=100_000.0,
        prediction_deployment_reader=deployment_reader,
        prediction_mapper_catalog=mapper_catalog,
        artifact_store=artifact_store,
    )
    backtest_id = backtest_created.data["backtest_specification"]["backtest_specification_id"]
    backtest_validation = validate_backtest_specification(
        backtest_specification_id=backtest_id,
        prediction_deployment_reader=deployment_reader,
        prediction_mapper_catalog=mapper_catalog,
        artifact_store=artifact_store,
    )
    assert backtest_validation.ok

    result = run_backtest_specification(
        event_store=event_store,
        config=_config(tmp_path / "model-backtest.duckdb"),
        backtest_specification_validation_ref=backtest_validation.data[
            "backtest_specification_validation_report"
        ]["validation_id"],
        prediction_deployment_reader=deployment_reader,
        prediction_mapper_catalog=mapper_catalog,
        prediction_runtime_resolver=runtime_resolver,
        artifact_store=artifact_store,
    )

    assert result.ok
    run = result.data["backtest_run"]
    assert run["status"] == "passed"
    assert run["summary"]["trade_count"] >= 2
    assert run["prediction_bindings"][0]["model_version_id"] == "model_version_1"
    prediction_rows = event_store.connection().execute(
        "SELECT model_version_id, feature_set_id, symbol, status FROM prediction_events ORDER BY decision_ts"
    ).fetchall()
    signal_rows = event_store.connection().execute(
        "SELECT signal_name, mapper_id, prediction_event_refs FROM signal_events ORDER BY generated_at"
    ).fetchall()
    order_rows = event_store.connection().execute(
        "SELECT decision_evidence FROM order_events WHERE status = 'created' ORDER BY created_at"
    ).fetchall()
    assert prediction_rows == [
        ("model_version_1", "feature_set_1", "EURUSD", "success"),
        ("model_version_1", "feature_set_1", "EURUSD", "success"),
    ]
    assert all(row[0] == "alpha" and row[1] == "identity_numeric:v1" for row in signal_rows)
    assert all("prediction_event_" in row[2] for row in signal_rows)
    assert order_rows and all("model_version_1" in row[0] for row in order_rows)
