from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

import pytest

from tests.support.duckdb_store import DuckDBEventStore
from trader.config import Config
from trader.market_data.sample import load_sample_market_data_csv
from trader_research.backtests import (
    RESEARCH_COMPARE_BACKTEST_RESULTS,
    RESEARCH_GET_BACKTEST_RESULTS,
    RESEARCH_RUN_BACKTEST,
    compare_backtest_results,
    get_backtest_results,
    run_baseline_backtest,
)
from trader_research.data import DataInventoryRequest, DataQualityRequest, data_summarize_quality, get_data_inventory
from trader_research.domain import BACKTEST_RUN_REF, COMPARISON_REPORT, BacktestRunRef
from trader_research.method_implementations.io import file_sha256
from trader_research.method_implementations.manifest import SIGNAL_RUNTIME_CONTRACT
from trader_research.method_packages import MethodPackageManifest
from trader_research.strategies import create_strategy_candidate
from trader_research.strategy_validation import validate_strategy_candidate


SAMPLE_CSV = Path("examples/data/demo_stock_1min.csv")
SAMPLE_START = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
SAMPLE_END = datetime(2026, 1, 20, 12, 11, tzinfo=timezone.utc)


def test_data_scoped_baseline_backtest_writes_artifact_bundle(tmp_path: Path) -> None:
    store, manifest, quality_report = _sample_store_and_reports(tmp_path)
    candidate, validation_report = _validated_candidate(tmp_path)

    payload = run_baseline_backtest(
        artifact_root=tmp_path,
        event_store=store,
        config=_config(tmp_path),
        strategy_candidate_manifest=candidate,
        strategy_candidate_validation_report=validation_report,
        dataset_manifest=manifest,
        data_quality_report=quality_report,
        assumptions={"fees": {"fixed_per_order": 0.0}, "slippage": {"bps": 0.0}},
        max_runs=5,
    ).to_dict()

    assert payload["ok"] is True
    assert payload["command"] == RESEARCH_RUN_BACKTEST
    assert payload["agent_owner"] == "Quant Research Supervisor Agent"
    run_ref = payload["data"]["backtest_run_ref"]
    assert run_ref["artifact_type"] == BACKTEST_RUN_REF
    assert run_ref["candidate_id"] == candidate["candidate_id"]
    assert run_ref["validation_id"] == validation_report["validation_id"]
    assert run_ref["dataset_id"] == manifest["dataset_id"]
    assert run_ref["data_scope"]["symbols"] == ["DEMO"]
    assert run_ref["data_scope"]["time_range"] == {
        "start": "2026-01-20T12:00:00+00:00",
        "end": "2026-01-20T12:11:00+00:00",
    }
    assert payload["data"]["summary"]["run_id"] == run_ref["run_id"]
    assert payload["data"]["summary"]["total_runs"] == 5

    artifact_paths = run_ref["artifact_paths"]
    for key in (
        "backtest_run_ref",
        "result",
        "metrics",
        "provenance",
        "equity_curve",
        "benchmark_curve",
        "positions",
    ):
        assert Path(artifact_paths[key]).exists()
    persisted_ref = json.loads(Path(artifact_paths["backtest_run_ref"]).read_text(encoding="utf-8"))
    assert persisted_ref == run_ref
    assert payload["artifacts"]["backtest_run_ref"]["artifact_type"] == BACKTEST_RUN_REF


def test_backtest_run_id_is_deterministic_for_same_inputs(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    candidate, validation_report = _validated_candidate(artifact_root)
    first_store, first_manifest, first_quality = _sample_store_and_reports(tmp_path / "one")
    second_store, second_manifest, second_quality = _sample_store_and_reports(tmp_path / "two")

    first = run_baseline_backtest(
        artifact_root=artifact_root,
        event_store=first_store,
        config=_config(tmp_path / "one"),
        strategy_candidate_manifest=candidate,
        strategy_candidate_validation_report=validation_report,
        dataset_manifest=first_manifest,
        data_quality_report=first_quality,
        max_runs=5,
    ).to_dict()
    second = run_baseline_backtest(
        artifact_root=artifact_root,
        event_store=second_store,
        config=_config(tmp_path / "two"),
        strategy_candidate_manifest=candidate,
        strategy_candidate_validation_report=validation_report,
        dataset_manifest=second_manifest,
        data_quality_report=second_quality,
        max_runs=5,
    ).to_dict()

    assert (
        first["data"]["backtest_run_ref"]["run_id"]
        == second["data"]["backtest_run_ref"]["run_id"]
    )


def test_backtest_results_lookup_by_run_id_dir_and_inline_ref(tmp_path: Path) -> None:
    payload = _run_successful_backtest(tmp_path)
    run_ref = payload["data"]["backtest_run_ref"]

    by_id = get_backtest_results(artifact_root=tmp_path, run_id=run_ref["run_id"]).to_dict()
    by_dir = get_backtest_results(artifact_root=tmp_path, artifact_dir=run_ref["artifact_dir"]).to_dict()
    by_ref = get_backtest_results(artifact_root=tmp_path, backtest_run_ref=run_ref).to_dict()

    assert by_id["ok"] is True
    assert by_id["command"] == RESEARCH_GET_BACKTEST_RESULTS
    assert by_id["data"]["backtest_run_ref"]["run_id"] == run_ref["run_id"]
    assert by_id["data"]["summary"]["run_id"] == run_ref["run_id"]
    assert by_dir["data"]["summary"] == by_id["data"]["summary"]
    assert by_ref["data"]["data_scope"] == by_id["data"]["data_scope"]


def test_compare_backtest_results_writes_deterministic_report(tmp_path: Path) -> None:
    first = _run_successful_backtest(tmp_path, max_runs=4)
    second = _run_successful_backtest(tmp_path, max_runs=5)
    first_ref = first["data"]["backtest_run_ref"]
    second_ref = second["data"]["backtest_run_ref"]
    _update_metrics(first_ref, sharpe=1.0, total_return=0.01)
    _update_metrics(second_ref, sharpe=2.0, total_return=0.02)

    first_payload = compare_backtest_results(
        artifact_root=tmp_path,
        backtest_runs=[{"backtest_run_ref": first_ref}, {"backtest_run_ref": second_ref}],
    ).to_dict()
    second_payload = compare_backtest_results(
        artifact_root=tmp_path,
        backtest_runs=[{"backtest_run_ref": first_ref}, {"backtest_run_ref": second_ref}],
    ).to_dict()

    assert first_payload["ok"] is True
    assert first_payload["command"] == RESEARCH_COMPARE_BACKTEST_RESULTS
    assert first_payload["agent_owner"] == "Quant Research Supervisor Agent"
    report = first_payload["data"]["comparison_report"]
    assert report["artifact_type"] == COMPARISON_REPORT
    assert report["ranking_metric"] == "sharpe"
    assert report["sort_order"] == "descending"
    assert report["best_run_id"] == second_ref["run_id"]
    assert report["ranked_rows"][0]["rank"] == 1
    assert report["ranked_rows"][0]["run_id"] == second_ref["run_id"]
    assert report["ranked_rows"][1]["rank"] == 2
    assert report["ranked_rows"][1]["run_id"] == first_ref["run_id"]
    assert report["comparison_id"] == second_payload["data"]["comparison_report"]["comparison_id"]
    report_path = Path(first_payload["artifacts"]["comparison_report"]["path"])
    assert report_path.exists()
    assert json.loads(report_path.read_text(encoding="utf-8")) == report


def test_compare_backtest_results_supports_mixed_refs_and_ranking_metrics(tmp_path: Path) -> None:
    first = _run_successful_backtest(tmp_path, max_runs=3)
    second = _run_successful_backtest(tmp_path, max_runs=4)
    third = _run_successful_backtest(tmp_path, max_runs=5)
    first_ref = first["data"]["backtest_run_ref"]
    second_ref = second["data"]["backtest_run_ref"]
    third_ref = third["data"]["backtest_run_ref"]
    _update_metrics(first_ref, max_drawdown=0.30, total_return=0.03)
    _update_metrics(second_ref, max_drawdown=0.10, total_return=0.01)
    _update_metrics(third_ref, max_drawdown=0.20, total_return=0.02)

    payload = compare_backtest_results(
        artifact_root=tmp_path,
        backtest_runs=[
            {"run_id": first_ref["run_id"]},
            {"artifact_dir": second_ref["artifact_dir"]},
            {"backtest_run_ref": third_ref},
        ],
        ranking_metric="max_drawdown",
    ).to_dict()

    assert payload["ok"] is True
    report = payload["data"]["comparison_report"]
    assert report["sort_order"] == "ascending"
    assert [row["run_id"] for row in report["ranked_rows"]] == [
        second_ref["run_id"],
        third_ref["run_id"],
        first_ref["run_id"],
    ]
    assert report["best_run_id"] == second_ref["run_id"]


def test_compare_backtest_results_warns_for_non_like_for_like_runs(tmp_path: Path) -> None:
    first = _run_successful_backtest(tmp_path, max_runs=4)
    second = _run_successful_backtest(tmp_path, max_runs=5)
    first_ref = first["data"]["backtest_run_ref"]
    second_ref = second["data"]["backtest_run_ref"]
    _update_metrics(first_ref, sharpe=1.0)
    _update_metrics(second_ref, sharpe=2.0)
    _update_run_ref(
        second_ref,
        dataset_id="dataset_other",
        candidate_id="strategy_candidate_other",
        validation_id="validation_other",
        data_scope={**second_ref["data_scope"], "symbols": ["OTHER"], "timeframe": "5Min"},
    )

    payload = compare_backtest_results(
        artifact_root=tmp_path,
        backtest_runs=[{"artifact_dir": first_ref["artifact_dir"]}, {"artifact_dir": second_ref["artifact_dir"]}],
    ).to_dict()

    assert payload["ok"] is True
    report = payload["data"]["comparison_report"]
    assert "Compared runs differ in dataset ID." in report["warnings"]
    assert "Compared runs differ in symbols." in report["warnings"]
    assert "Compared runs differ in timeframe." in report["warnings"]
    assert "Compared runs differ in candidate ID." in report["warnings"]
    assert "Compared runs differ in validation ID." in report["warnings"]
    assert report["comparable_dimensions"]["dataset_id"]["comparable"] is False


@pytest.mark.parametrize(
    ("refs_factory", "expected_message"),
    [
        (lambda refs: [{"backtest_run_ref": refs[0]}], "at least two backtest run refs"),
        (
            lambda refs: [{"backtest_run_ref": refs[0]}, {"artifact_dir": refs[0]["artifact_dir"]}],
            "duplicate backtest run_id",
        ),
        (lambda _refs: [{"run_id": "missing"}, {"run_id": "also_missing"}], "backtest_run_ref.json not found"),
    ],
)
def test_compare_backtest_results_rejects_invalid_refs(
    tmp_path: Path,
    refs_factory: Any,
    expected_message: str,
) -> None:
    first = _run_successful_backtest(tmp_path, max_runs=4)
    second = _run_successful_backtest(tmp_path, max_runs=5)

    payload = compare_backtest_results(
        artifact_root=tmp_path,
        backtest_runs=refs_factory([first["data"]["backtest_run_ref"], second["data"]["backtest_run_ref"]]),
    ).to_dict()

    assert payload["ok"] is False
    assert payload["errors"][0]["code"] == "backtest_comparison_failed"
    assert expected_message in payload["errors"][0]["message"]


@pytest.mark.parametrize(
    ("mutator", "expected_message"),
    [
        (lambda refs: _update_run_ref(refs[0], artifact_type="wrong_type"), "artifact_type must be backtest_run_ref"),
        (lambda refs: Path(refs[0]["artifact_paths"]["metrics"]).unlink(), "metrics.json not found"),
        (lambda refs: _update_metrics(refs[0], sharpe=None), "at least two runs must have numeric ranking_metric=sharpe"),
    ],
)
def test_compare_backtest_results_rejects_invalid_bundles(
    tmp_path: Path,
    mutator: Any,
    expected_message: str,
) -> None:
    first = _run_successful_backtest(tmp_path, max_runs=4)
    second = _run_successful_backtest(tmp_path, max_runs=5)
    refs = [first["data"]["backtest_run_ref"], second["data"]["backtest_run_ref"]]
    _update_metrics(refs[0], sharpe=1.0)
    _update_metrics(refs[1], sharpe=2.0)
    mutator(refs)

    payload = compare_backtest_results(
        artifact_root=tmp_path,
        backtest_runs=[{"artifact_dir": ref["artifact_dir"]} for ref in refs],
    ).to_dict()

    assert payload["ok"] is False
    assert expected_message in payload["errors"][0]["message"]


def test_compare_backtest_results_rejects_invalid_metric_and_sort_order(tmp_path: Path) -> None:
    first = _run_successful_backtest(tmp_path, max_runs=4)
    second = _run_successful_backtest(tmp_path, max_runs=5)
    refs = [first["data"]["backtest_run_ref"], second["data"]["backtest_run_ref"]]

    bad_metric = compare_backtest_results(
        artifact_root=tmp_path,
        backtest_runs=[{"backtest_run_ref": ref} for ref in refs],
        ranking_metric="unknown_metric",
    ).to_dict()
    bad_order = compare_backtest_results(
        artifact_root=tmp_path,
        backtest_runs=[{"backtest_run_ref": ref} for ref in refs],
        sort_order="sideways",
    ).to_dict()

    assert bad_metric["ok"] is False
    assert "unsupported ranking_metric" in bad_metric["errors"][0]["message"]
    assert bad_order["ok"] is False
    assert "sort_order must be ascending or descending" in bad_order["errors"][0]["message"]


@pytest.mark.parametrize(
    ("mutator", "expected_message"),
    [
        (lambda manifest: {**manifest, "complete": False}, "dataset_manifest.complete must be true"),
        (lambda manifest: {**manifest, "total_rows": 0}, "dataset_manifest.total_rows must be positive"),
        (
            lambda manifest: {**manifest, "requested_window": {"start": SAMPLE_END.isoformat(), "end": SAMPLE_START.isoformat()}},
            "time_range.start must be <= time_range.end",
        ),
        (lambda manifest: {**manifest, "source_filter": "sample"}, "source_filter is not supported"),
    ],
)
def test_backtest_rejects_invalid_dataset_manifests(
    tmp_path: Path,
    mutator: Any,
    expected_message: str,
) -> None:
    store, manifest, _quality_report = _sample_store_and_reports(tmp_path)
    candidate, validation_report = _validated_candidate(tmp_path)

    payload = run_baseline_backtest(
        artifact_root=tmp_path,
        event_store=store,
        config=_config(tmp_path),
        strategy_candidate_manifest=candidate,
        strategy_candidate_validation_report=validation_report,
        dataset_manifest=mutator(manifest),
    ).to_dict()

    assert payload["ok"] is False
    assert payload["errors"][0]["code"] == "backtest_input_validation_failed"
    assert expected_message in payload["errors"][0]["message"]


def test_backtest_rejects_raw_scope_fields(tmp_path: Path) -> None:
    store, manifest, _quality_report = _sample_store_and_reports(tmp_path)
    candidate, validation_report = _validated_candidate(tmp_path)

    payload = run_baseline_backtest(
        artifact_root=tmp_path,
        event_store=store,
        config=_config(tmp_path),
        strategy_candidate_manifest=candidate,
        strategy_candidate_validation_report=validation_report,
        dataset_manifest=manifest,
        symbols=("DEMO",),
    ).to_dict()

    assert payload["ok"] is False
    assert payload["errors"][0]["code"] == "raw_backtest_scope_rejected"
    assert payload["data"]["rejected_fields"] == ["symbols"]


@pytest.mark.parametrize(
    ("validation_mutator", "expected_message"),
    [
        (lambda report: {**report, "status": "failed"}, "validation report status must be passed"),
        (lambda report: {**report, "candidate_id": "other_candidate"}, "candidate_id does not match"),
    ],
)
def test_backtest_rejects_invalid_validation_reports(
    tmp_path: Path,
    validation_mutator: Any,
    expected_message: str,
) -> None:
    store, manifest, _quality_report = _sample_store_and_reports(tmp_path)
    candidate, validation_report = _validated_candidate(tmp_path)

    payload = run_baseline_backtest(
        artifact_root=tmp_path,
        event_store=store,
        config=_config(tmp_path),
        strategy_candidate_manifest=candidate,
        strategy_candidate_validation_report=validation_mutator(validation_report),
        dataset_manifest=manifest,
    ).to_dict()

    assert payload["ok"] is False
    assert expected_message in payload["errors"][0]["message"]


def test_backtest_rejects_tampered_strategy_source(tmp_path: Path) -> None:
    store, manifest, _quality_report = _sample_store_and_reports(tmp_path)
    candidate, validation_report = _validated_candidate(tmp_path)
    source_path = Path(candidate["strategy_source"]["path"])
    source_path.write_text(source_path.read_text(encoding="utf-8") + "\n# tampered\n", encoding="utf-8")

    payload = run_baseline_backtest(
        artifact_root=tmp_path,
        event_store=store,
        config=_config(tmp_path),
        strategy_candidate_manifest=candidate,
        strategy_candidate_validation_report=validation_report,
        dataset_manifest=manifest,
    ).to_dict()

    assert payload["ok"] is False
    assert "source_hash does not match current source file" in payload["errors"][0]["message"]


def test_backtest_rejects_mismatched_data_quality_report(tmp_path: Path) -> None:
    store, manifest, quality_report = _sample_store_and_reports(tmp_path)
    candidate, validation_report = _validated_candidate(tmp_path)
    mismatched_report = {**quality_report, "symbols": ["OTHER"]}

    payload = run_baseline_backtest(
        artifact_root=tmp_path,
        event_store=store,
        config=_config(tmp_path),
        strategy_candidate_manifest=candidate,
        strategy_candidate_validation_report=validation_report,
        dataset_manifest=manifest,
        data_quality_report=mismatched_report,
    ).to_dict()

    assert payload["ok"] is False
    assert "data_quality_report.symbols does not match" in payload["errors"][0]["message"]


def test_backtest_run_ref_round_trip_includes_data_scope() -> None:
    ref = BacktestRunRef(
        experiment_id="experiment_demo",
        experiment_run_id="experiment_run_demo",
        run_id="backtest_run_demo",
        artifact_dir="artifacts/research/backtests/runs/backtest_run_demo",
        candidate_id="strategy_candidate_demo",
        validation_id="strategy_validation_demo",
        dataset_id="dataset_demo",
        data_scope={"dataset_id": "dataset_demo", "symbols": ["DEMO"]},
        status="passed",
        summary={"total_runs": 3},
    )

    payload = ref.to_dict()

    assert payload["artifact_type"] == BACKTEST_RUN_REF
    assert payload["data_scope"]["symbols"] == ["DEMO"]
    assert BacktestRunRef.from_dict(payload).to_dict() == payload


def _run_successful_backtest(root: Path, *, max_runs: int = 5) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    store, manifest, quality_report = _sample_store_and_reports(root)
    candidate, validation_report = _validated_candidate(root)
    payload = run_baseline_backtest(
        artifact_root=root,
        event_store=store,
        config=_config(root),
        strategy_candidate_manifest=candidate,
        strategy_candidate_validation_report=validation_report,
        dataset_manifest=manifest,
        data_quality_report=quality_report,
        max_runs=max_runs,
    ).to_dict()
    assert payload["ok"] is True
    return payload


def _update_metrics(run_ref: dict[str, Any], **updates: Any) -> None:
    metrics_path = Path(run_ref["artifact_paths"]["metrics"])
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    metrics.update(updates)
    metrics_path.write_text(json.dumps(metrics, indent=2, sort_keys=True), encoding="utf-8")


def _update_run_ref(run_ref: dict[str, Any], **updates: Any) -> None:
    run_ref_path = Path(run_ref["artifact_paths"]["backtest_run_ref"])
    persisted = json.loads(run_ref_path.read_text(encoding="utf-8"))
    persisted.update(updates)
    run_ref_path.write_text(json.dumps(persisted, indent=2, sort_keys=True), encoding="utf-8")


def _sample_store_and_reports(root: Path) -> tuple[DuckDBEventStore, dict[str, Any], dict[str, Any]]:
    root.mkdir(parents=True, exist_ok=True)
    store = DuckDBEventStore(str(root / "events.duckdb"))
    load_sample_market_data_csv(store, SAMPLE_CSV)
    inventory = get_data_inventory(
        store,
        DataInventoryRequest(
            symbols=("DEMO",),
            asset_class="stocks",
            timeframe="1Min",
            start=SAMPLE_START,
            end=SAMPLE_END,
        ),
    ).to_dict()
    quality = data_summarize_quality(
        store,
        DataQualityRequest(
            symbols=("DEMO",),
            asset_class="stocks",
            timeframe="1Min",
            start=SAMPLE_START,
            end=SAMPLE_END,
        ),
    ).to_dict()
    assert inventory["ok"] is True
    assert quality["ok"] is True
    return store, inventory["data"]["dataset_manifest"], quality["data"]["data_quality_report"]


def _validated_candidate(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    candidate_payload = create_strategy_candidate(
        artifact_root=root,
        template_family="bollinger_band",
        method_package_refs=[
            {"role": "bollinger_band_signal", "package_manifest": _signal_package("method_package_bollinger")}
        ],
        parameters={"period": 3, "stddev_multiplier": 2.0},
        sizing={"target_qty_when_long": 1.0, "max_position_qty": 5.0},
    ).to_dict()
    assert candidate_payload["ok"] is True
    candidate = candidate_payload["data"]["strategy_candidate_manifest"]
    source_path = Path(candidate["strategy_source"]["path"])
    assert file_sha256(source_path) == candidate["strategy_source"]["source_hash"]
    validation_payload = validate_strategy_candidate(
        artifact_root=root,
        strategy_candidate_manifest=candidate,
    ).to_dict()
    assert validation_payload["ok"] is True
    return candidate, validation_payload["data"]["strategy_candidate_validation_report"]


def _signal_package(package_id: str) -> dict[str, Any]:
    return MethodPackageManifest(
        package_id=package_id,
        method_id=f"method_{package_id}",
        runtime_contract=SIGNAL_RUNTIME_CONTRACT,
        implementation_id=f"implementation_{package_id}",
        entrypoint=f"trader_standard.signals:{package_id}",
        class_name="DemoSignal",
        source_path=f"src/trader_standard/signals/{package_id}.py",
        source_hash=f"hash_{package_id}",
        source_provenance={"kind": "validated_fixture"},
        constructor_kwargs={},
        method_contract={"method_id": f"method_{package_id}"},
        method_card_ids=("method_card_bollinger_band",),
        validation_report_ref={
            "artifact_type": "signal_implementation_validation_report",
            "validation_id": f"validation_{package_id}",
            "status": "passed",
            "path": f"artifacts/research/validations/{package_id}.json",
        },
        validation_summary={"status": "passed", "fixture_count": 1},
        safety_profile={"imports": "static_allowlist"},
        dependency_allowlist=("trader", "trader_standard"),
    ).to_dict()


def _config(tmp_path: Path) -> Config:
    return Config(
        mode="once",
        strategy_type="research",
        strategy_id="research",
        strategy_timeframe="1Min",
        sma_short_window=2,
        sma_long_window=3,
        db_path=str(tmp_path / "events.duckdb"),
        event_store="postgres",
        market_data_source="noop",
        market_data_asset_class="stocks",
        market_data_stock_feed="iex",
        market_data_symbols=("DEMO",),
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
