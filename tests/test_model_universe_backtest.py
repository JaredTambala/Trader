"""Synchronized-universe backtest qualification for model-backed strategies."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from trader.backtest import BacktestRunner, BacktestSpec
from trader.predictions import (
    InferencePolicy,
    ModelIdentity,
    PredictionBatch,
    PredictionObservation,
    PredictionRequest,
    RuntimePredictionBinding,
)
from trader_standard import NoOpRiskManager
from trader_standard.predictions import (
    BarFeatureProvider,
    MaintainedPredictionMapperCatalog,
)
from trader_standard.strategies import PredictionDrivenStrategy
from tests.support.duckdb_store import DuckDBEventStore
from tests.test_model_backtest_integration import _config, _record_bar


class _CountingRankPredictor:
    """Return cross-sectional rank scores and retain bounded call evidence."""

    identity = ModelIdentity(
        registered_model_name="rank_model",
        model_version="1",
        model_version_id="model_version_rank_1",
        model_digest="sha256:rank-model",
        signature_digest="sha256:rank-signature",
        source_run_id="training_run_rank_1",
        adapter_profile="fixture_local",
        adapter_version="1",
    )

    def __init__(self) -> None:
        self.requests: list[PredictionRequest] = []

    def predict(self, request: PredictionRequest) -> PredictionBatch:
        self.requests.append(request)
        return PredictionBatch(
            model_identity=self.identity,
            feature_batch_hash=request.feature_batch.input_hash,
            decision_ts=request.feature_batch.decision_ts,
            observations=tuple(
                PredictionObservation(
                    output_name="rank_score",
                    semantics="rank_score",
                    value=float(row.values["return_1"]),
                    horizon="1bar",
                    symbol=row.symbol,
                )
                for row in request.feature_batch.rows
            ),
            status="success",
            latency_ms=1.0,
        )


def test_model_backtest_runs_once_per_complete_universe_timestamp(
    tmp_path: Path,
) -> None:
    event_store = DuckDBEventStore(str(tmp_path / "universe-model.duckdb"))
    start = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    for symbol, prior, current in (("AAA", 100.0, 101.0), ("BBB", 100.0, 99.0)):
        _record_bar(event_store, symbol, start - timedelta(minutes=1), prior)
        _record_bar(event_store, symbol, start, current)
    _record_bar(event_store, "AAA", start + timedelta(minutes=1), 102.0)

    feature_set = {
        "feature_set_id": "feature_set_rank_1",
        "feature_set_digest": "sha256:rank-features",
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
    }
    output_contract = (
        {
            "name": "rank_score",
            "semantics": "rank_score",
            "horizon": "1bar",
            "shape": "scalar",
            "dtype": "float64",
            "units": None,
            "nullable": False,
        },
    )
    catalog = MaintainedPredictionMapperCatalog()
    mapper = catalog.build_mapper(
        catalog.resolve_configuration(
            mapper_id="identity_numeric:v1",
            consumer_kind="ranking",
            output_contract=output_contract,
            parameters={"target_name": "rank"},
        )
    )
    predictor = _CountingRankPredictor()
    binding = RuntimePredictionBinding(
        binding_name="rank_model",
        deployment_id="deployment_rank_1",
        deployment_validation_id="deployment_validation_rank_1",
        output_names=("rank_score",),
        output_contract=output_contract,
        decision_scope="universe_snapshot",
        symbols=("AAA", "BBB"),
        asset_class="stocks",
        timeframe="1Min",
        feature_provider=BarFeatureProvider(
            feature_set=feature_set,
            decision_scope="universe_snapshot",
        ),
        predictor=predictor,
        mapper=mapper,
        policy=InferencePolicy(require_complete_universe=True),
    )
    strategy = PredictionDrivenStrategy(
        symbols=("AAA", "BBB"),
        asset_class="stocks",
        timeframe="1Min",
        prediction_bindings=(binding,),
        prediction_binding_name="rank_model",
        input_name="rank",
        consumer_kind="ranking",
        order_qty=1.0,
        long_count=1,
        short_count=1,
    )
    config = replace(
        _config(tmp_path / "universe-model.duckdb"),
        market_data_symbols=("AAA", "BBB"),
    )
    result = BacktestRunner(
        config,
        BacktestSpec(
            start=start,
            end=start + timedelta(minutes=1),
            timeframe="1Min",
        ),
        strategy=strategy,
        risk_manager=NoOpRiskManager(),
        symbols=("AAA", "BBB"),
        asset_class="stocks",
        event_store=event_store,
        initial_cash=100_000.0,
    ).run()

    assert len(predictor.requests) == 1
    assert predictor.requests[0].feature_batch.symbols == ("AAA", "BBB")
    assert len(result.trades) == 2
    assert any("Skipped 1 incomplete universe timestamps" in item for item in result.warnings)
    assert event_store.connection().execute(
        "SELECT COUNT(*) FROM prediction_events WHERE decision_ts = ?",
        [start],
    ).fetchone()[0] == 2
