from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Any

import pytest

from tests.support.duckdb_store import DuckDBEventStore
from tests.test_research_backtests import _config, _signal_package
from trader_research.backtests import RESEARCH_RUN_PORTFOLIO_BACKTEST, run_portfolio_backtest
from trader_research.data import DataInventoryRequest, DataQualityRequest, data_summarize_quality, get_data_inventory
from trader_research.domain import PORTFOLIO_BACKTEST_RUN_REF
from trader_research.evaluation import generate_performance_report
from trader_research.portfolio_stacks import create_strategy_risk_stack, validate_strategy_risk_stack
from trader_research.risk_managers import create_risk_manager_candidate, validate_risk_manager_candidate
from trader_research.strategy_candidates import create_strategy_candidate, validate_strategy_candidate


PORTFOLIO_SYMBOLS = ("ALPHA", "BETA", "GAMMA")
PORTFOLIO_START = datetime(2026, 2, 3, 14, 30, tzinfo=timezone.utc)
PORTFOLIO_END = datetime(2026, 2, 3, 14, 35, tzinfo=timezone.utc)


def test_risk_scoped_portfolio_backtest_writes_bundle(tmp_path: Path) -> None:
    store, dataset_manifest, quality_report = _multi_asset_store_and_reports(tmp_path)
    stack_report, stack_manifest = _validated_stack(tmp_path)

    payload = run_portfolio_backtest(
        artifact_root=tmp_path,
        event_store=store,
        config=_portfolio_config(tmp_path),
        strategy_risk_stack_validation_report=stack_report,
        dataset_manifest=dataset_manifest,
        data_quality_report=quality_report,
        assumptions={"fees": {"fixed_per_order": 0.0}, "slippage": {"bps": 0.0}},
        max_runs=12,
    ).to_dict()

    assert payload["ok"] is True
    assert payload["command"] == RESEARCH_RUN_PORTFOLIO_BACKTEST
    assert payload["agent_owner"] == "Quant Research Supervisor Agent"
    run_ref = payload["data"]["portfolio_backtest_run_ref"]
    assert run_ref["artifact_type"] == PORTFOLIO_BACKTEST_RUN_REF
    assert run_ref["strategy_risk_stack_id"] == stack_manifest["stack_id"]
    assert run_ref["strategy_risk_stack_validation_id"] == stack_report["validation_id"]
    assert run_ref["dataset_id"] == dataset_manifest["dataset_id"]
    assert run_ref["data_scope"]["symbols"] == list(PORTFOLIO_SYMBOLS)
    assert payload["data"]["risk_decisions"]["manager_count"] == 1
    assert payload["data"]["risk_measure_summary"]["missing_required_telemetry"] == []
    assert set(payload["data"]["symbol_metrics"]) == set(PORTFOLIO_SYMBOLS)

    for key in (
        "portfolio_backtest_run_ref",
        "result",
        "metrics",
        "provenance",
        "equity_curve",
        "positions",
        "symbol_metrics",
        "exposure_summary",
        "risk_decisions",
        "risk_limit_breaches",
        "risk_measure_summary",
    ):
        assert Path(run_ref["artifact_paths"][key]).exists()
    persisted = json.loads(Path(run_ref["artifact_paths"]["portfolio_backtest_run_ref"]).read_text(encoding="utf-8"))
    assert persisted == run_ref


def test_portfolio_backtest_run_id_is_deterministic_for_same_inputs(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    stack_report, _stack_manifest = _validated_stack(artifact_root)
    first_store, first_manifest, first_quality = _multi_asset_store_and_reports(tmp_path / "one")
    second_store, second_manifest, second_quality = _multi_asset_store_and_reports(tmp_path / "two")

    first = run_portfolio_backtest(
        artifact_root=artifact_root,
        event_store=first_store,
        config=_portfolio_config(tmp_path / "one"),
        strategy_risk_stack_validation_report=stack_report,
        dataset_manifest=first_manifest,
        data_quality_report=first_quality,
        max_runs=12,
    ).to_dict()
    second = run_portfolio_backtest(
        artifact_root=artifact_root,
        event_store=second_store,
        config=_portfolio_config(tmp_path / "two"),
        strategy_risk_stack_validation_report=stack_report,
        dataset_manifest=second_manifest,
        data_quality_report=second_quality,
        max_runs=12,
    ).to_dict()

    assert first["ok"] is True
    assert second["ok"] is True
    assert (
        first["data"]["portfolio_backtest_run_ref"]["run_id"]
        == second["data"]["portfolio_backtest_run_ref"]["run_id"]
    )


@pytest.mark.parametrize(
    ("mutator", "expected_message"),
    [
        (lambda report: {**report, "status": "failed"}, "validation report status must be passed"),
        (lambda report: {**report, "blockers": ["blocked"]}, "must not contain blockers"),
    ],
)
def test_portfolio_backtest_rejects_non_passed_stack_validation(
    tmp_path: Path,
    mutator: Any,
    expected_message: str,
) -> None:
    store, dataset_manifest, quality_report = _multi_asset_store_and_reports(tmp_path)
    stack_report, _stack_manifest = _validated_stack(tmp_path)

    payload = run_portfolio_backtest(
        artifact_root=tmp_path,
        event_store=store,
        config=_portfolio_config(tmp_path),
        strategy_risk_stack_validation_report=mutator(stack_report),
        dataset_manifest=dataset_manifest,
        data_quality_report=quality_report,
    ).to_dict()

    assert payload["ok"] is False
    assert payload["errors"][0]["code"] == "portfolio_backtest_input_validation_failed"
    assert expected_message in payload["errors"][0]["message"]


def test_portfolio_backtest_rejects_raw_scope_fields(tmp_path: Path) -> None:
    store, dataset_manifest, quality_report = _multi_asset_store_and_reports(tmp_path)
    stack_report, _stack_manifest = _validated_stack(tmp_path)

    payload = run_portfolio_backtest(
        artifact_root=tmp_path,
        event_store=store,
        config=_portfolio_config(tmp_path),
        strategy_risk_stack_validation_report=stack_report,
        dataset_manifest=dataset_manifest,
        data_quality_report=quality_report,
        symbols=PORTFOLIO_SYMBOLS,
    ).to_dict()

    assert payload["ok"] is False
    assert payload["errors"][0]["code"] == "raw_backtest_scope_rejected"
    assert payload["data"]["rejected_fields"] == ["symbols"]


def test_portfolio_backtest_rejects_source_filtered_dataset_manifest(tmp_path: Path) -> None:
    store, dataset_manifest, quality_report = _multi_asset_store_and_reports(tmp_path)
    stack_report, _stack_manifest = _validated_stack(tmp_path)

    payload = run_portfolio_backtest(
        artifact_root=tmp_path,
        event_store=store,
        config=_portfolio_config(tmp_path),
        strategy_risk_stack_validation_report=stack_report,
        dataset_manifest={**dataset_manifest, "source_filter": "fixture"},
        data_quality_report=quality_report,
    ).to_dict()

    assert payload["ok"] is False
    assert "source_filter is not supported" in payload["errors"][0]["message"]


def test_portfolio_backtest_rejects_tampered_risk_manager_source(tmp_path: Path) -> None:
    store, dataset_manifest, quality_report = _multi_asset_store_and_reports(tmp_path)
    stack_report, stack_manifest = _validated_stack(tmp_path)
    risk_manifest_path = Path(stack_manifest["risk_manager_refs"][0]["path"])
    risk_manifest = json.loads(risk_manifest_path.read_text(encoding="utf-8"))
    source_path = Path(risk_manifest["risk_manager_source"]["path"])
    source_path.write_text(source_path.read_text(encoding="utf-8") + "\n# tampered\n", encoding="utf-8")

    payload = run_portfolio_backtest(
        artifact_root=tmp_path,
        event_store=store,
        config=_portfolio_config(tmp_path),
        strategy_risk_stack_validation_report=stack_report,
        dataset_manifest=dataset_manifest,
        data_quality_report=quality_report,
    ).to_dict()

    assert payload["ok"] is False
    assert "risk_manager_0 source_hash does not match" in payload["errors"][0]["message"]


def test_evaluation_report_consumes_portfolio_backtest_bundle(tmp_path: Path) -> None:
    run_payload, quality_report = _run_successful_portfolio_backtest(tmp_path)
    run_ref = run_payload["data"]["portfolio_backtest_run_ref"]

    payload = generate_performance_report(
        artifact_root=tmp_path,
        portfolio_backtest_run_ref=run_ref,
        data_quality_report=quality_report,
    ).to_dict()

    assert payload["ok"] is True
    report = payload["data"]["evaluation_report"]
    assert report["status"] == "passed"
    assert report["backtest_kind"] == "portfolio"
    assert report["strategy_risk_stack_id"] == run_ref["strategy_risk_stack_id"]
    assert report["strategy_risk_stack_validation_id"] == run_ref["strategy_risk_stack_validation_id"]
    assert report["symbol_metrics"]
    assert report["exposure_summary"]
    assert report["risk_decisions"]["manager_count"] == 1
    assert report["risk_measure_summary"]["missing_required_telemetry"] == []


def test_evaluation_report_blocks_when_portfolio_risk_evidence_is_missing(tmp_path: Path) -> None:
    run_payload, quality_report = _run_successful_portfolio_backtest(tmp_path)
    run_ref = run_payload["data"]["portfolio_backtest_run_ref"]
    Path(run_ref["artifact_paths"]["risk_decisions"]).unlink()

    payload = generate_performance_report(
        artifact_root=tmp_path,
        portfolio_backtest_run_ref=run_ref,
        data_quality_report=quality_report,
    ).to_dict()

    assert payload["ok"] is True
    report = payload["data"]["evaluation_report"]
    assert report["status"] == "blocked"
    assert "missing_portfolio_risk_evidence" in {blocker["code"] for blocker in report["blockers"]}


def test_evaluation_report_blocks_for_missing_required_risk_telemetry(tmp_path: Path) -> None:
    run_payload, quality_report = _run_successful_portfolio_backtest(
        tmp_path,
        risk_template_family="var_cvar_limit",
        risk_parameters={"max_var_fraction": 0.05, "max_cvar_fraction": 0.08},
    )
    run_ref = run_payload["data"]["portfolio_backtest_run_ref"]

    payload = generate_performance_report(
        artifact_root=tmp_path,
        portfolio_backtest_run_ref=run_ref,
        data_quality_report=quality_report,
    ).to_dict()

    assert payload["ok"] is True
    report = payload["data"]["evaluation_report"]
    assert report["status"] == "blocked"
    assert "missing_required_risk_telemetry" in {blocker["code"] for blocker in report["blockers"]}


def _run_successful_portfolio_backtest(
    root: Path,
    *,
    risk_template_family: str = "gross_exposure_cap",
    risk_parameters: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    store, dataset_manifest, quality_report = _multi_asset_store_and_reports(root)
    stack_report, _stack_manifest = _validated_stack(
        root,
        risk_template_family=risk_template_family,
        risk_parameters=risk_parameters,
    )
    payload = run_portfolio_backtest(
        artifact_root=root,
        event_store=store,
        config=_portfolio_config(root),
        strategy_risk_stack_validation_report=stack_report,
        dataset_manifest=dataset_manifest,
        data_quality_report=quality_report,
        max_runs=12,
    ).to_dict()
    assert payload["ok"] is True
    return payload, quality_report


def _validated_stack(
    root: Path,
    *,
    risk_template_family: str = "gross_exposure_cap",
    risk_parameters: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    strategy = create_strategy_candidate(
        artifact_root=root,
        template_family="cross_sectional_momentum",
        method_package_refs=[{"role": "ranking_signal", "package_manifest": _signal_package("method_package_rank")}],
        parameters={"lookback_period": 1, "top_n": 2, "rebalance_cadence": "every_bar"},
        sizing={"target_qty_when_long": 1.0, "max_position_qty": 10.0},
    ).to_dict()
    assert strategy["ok"] is True
    strategy_report = validate_strategy_candidate(
        artifact_root=root,
        strategy_candidate_manifest=strategy["data"]["strategy_candidate_manifest"],
    ).to_dict()
    assert strategy_report["ok"] is True
    risk = create_risk_manager_candidate(
        artifact_root=root,
        template_family=risk_template_family,
        parameters=risk_parameters or {"max_gross_exposure": 1_000_000.0},
    ).to_dict()
    assert risk["ok"] is True
    risk_report = validate_risk_manager_candidate(
        artifact_root=root,
        risk_manager_candidate_manifest=risk["data"]["risk_manager_candidate_manifest"],
    ).to_dict()
    assert risk_report["ok"] is True
    stack = create_strategy_risk_stack(
        artifact_root=root,
        strategy_candidate_validation_report=strategy_report["data"]["strategy_candidate_validation_report"],
        risk_manager_validation_refs=[
            {"risk_manager_candidate_validation_report": risk_report["data"]["risk_manager_candidate_validation_report"]}
        ],
    ).to_dict()
    assert stack["ok"] is True
    validation = validate_strategy_risk_stack(
        artifact_root=root,
        strategy_risk_stack_manifest=stack["data"]["strategy_risk_stack_manifest"],
    ).to_dict()
    assert validation["ok"] is True
    return (
        validation["data"]["strategy_risk_stack_validation_report"],
        stack["data"]["strategy_risk_stack_manifest"],
    )


def _multi_asset_store_and_reports(root: Path) -> tuple[DuckDBEventStore, dict[str, Any], dict[str, Any]]:
    root.mkdir(parents=True, exist_ok=True)
    store = DuckDBEventStore(str(root / "portfolio_events.duckdb"))
    _load_portfolio_bars(store)
    request = {
        "symbols": PORTFOLIO_SYMBOLS,
        "asset_class": "stocks",
        "timeframe": "1Min",
        "start": PORTFOLIO_START,
        "end": PORTFOLIO_END,
    }
    inventory = get_data_inventory(store, DataInventoryRequest(**request)).to_dict()
    quality = data_summarize_quality(store, DataQualityRequest(**request)).to_dict()
    assert inventory["ok"] is True
    assert quality["ok"] is True
    return store, inventory["data"]["dataset_manifest"], quality["data"]["data_quality_report"]


def _load_portfolio_bars(store: DuckDBEventStore) -> None:
    closes_by_symbol = {
        "ALPHA": (10.0, 11.0, 12.0, 13.0, 14.0, 15.0),
        "BETA": (20.0, 19.0, 20.5, 21.0, 22.0, 23.0),
        "GAMMA": (30.0, 30.5, 30.0, 29.5, 29.0, 28.5),
    }
    for symbol, closes in closes_by_symbol.items():
        for index, close in enumerate(closes):
            ts = PORTFOLIO_START + timedelta(minutes=index)
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
                    "volume": 100.0 + index,
                    "trade_count": 1.0,
                    "vwap": close,
                    "source": "portfolio_fixture",
                },
            )


def _portfolio_config(root: Path):
    return replace(
        _config(root),
        market_data_symbols=PORTFOLIO_SYMBOLS,
        db_path=str(root / "portfolio_events.duckdb"),
    )
