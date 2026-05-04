from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_backfill_dry_run_json_is_parseable(tmp_path: Path) -> None:
    config_path = _config(tmp_path)

    result = subprocess.run(
        [
            sys.executable,
            "run_market_data_backfill.py",
            str(config_path),
            "--dry-run",
            "--json",
            "--symbols",
            "DEMO",
            "--asset-class",
            "stocks",
            "--timeframe",
            "1Min",
            "--since",
            "1d",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["command"] == "market_data_backfill"
    assert payload["side_effect"] == "read_only"
    assert payload["data"]["dry_run"] is True
    assert payload["data"]["dataset_id"].startswith("dataset_")


def test_data_quality_json_envelope_writes_report(tmp_path: Path) -> None:
    config_path = _config(tmp_path)
    report_path = tmp_path / "dq.json"

    result = subprocess.run(
        [
            sys.executable,
            "run_data_quality.py",
            str(config_path),
            "--output-json",
            str(report_path),
            "--json",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["command"] == "data_quality"
    assert payload["side_effect"] == "read_only"
    assert payload["data"]["report_path"] == str(report_path)
    assert report_path.exists()


def test_research_discovery_plan_json_is_parseable(tmp_path: Path) -> None:
    config_path = _config(tmp_path)

    result = subprocess.run(
        [
            sys.executable,
            "run_research_discovery.py",
            str(config_path),
            "--data-mode",
            "plan",
            "--symbols",
            "DEMO",
            "--asset-class",
            "stocks",
            "--timeframe",
            "1Min",
            "--strategies",
            "trend_following,mean_reversion",
            "--json",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["command"] == "research_discovery"
    assert payload["side_effect"] == "read_only"
    assert payload["data"]["will_run_backtests"] is False
    assert payload["data"]["request"]["strategy_families"] == ["trend_following", "mean_reversion"]
    assert payload["data"]["suite"]["member_count"] == 2


def test_research_recommendations_json_writes_artifact(tmp_path: Path) -> None:
    config_path = _config(tmp_path)
    output_path = tmp_path / "recommendations.json"

    result = subprocess.run(
        [
            sys.executable,
            "run_research_recommendations.py",
            str(config_path),
            "--experiment",
            "empty_demo",
            "--output",
            str(output_path),
            "--allow-missing-data-quality",
            "--json",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["command"] == "research_recommendations"
    assert payload["artifacts"]["recommendations"] == str(output_path)
    assert output_path.exists()


def test_prepare_paper_promotion_json_writes_packet(tmp_path: Path) -> None:
    config_path = _config(tmp_path, broker_type="alpaca")
    recommendation_path = tmp_path / "recommendations.json"
    recommendation_path.write_text(
        json.dumps(
            {
                "experiment_name": "demo",
                "accepted_candidates": [
                    {
                        "recommendation_id": "rec_good",
                        "promotion_ready": True,
                        "run_id": "run_good",
                        "experiment_run_id": "exp_run_good",
                        "strategy_id": "trend_following",
                        "strategy_name": "Trend Following",
                        "strategy_version": "1",
                        "artifact_dir": "artifacts/research/good",
                    }
                ],
                "rejected_candidates": [],
            }
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "run_prepare_paper_promotion.py",
            str(config_path),
            "--recommendation-json",
            str(recommendation_path),
            "--recommendation-id",
            "rec_good",
            "--output-dir",
            str(tmp_path / "promotions"),
            "--dry-run",
            "--json",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["command"] == "prepare_paper_promotion"
    assert payload["side_effect"] == "local_mutating"
    assert payload["data"]["promotion_ready"] is True
    assert Path(payload["artifacts"]["promotion_packet"]).exists()


def _config(tmp_path: Path, *, broker_type: str = "noop") -> Path:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        f"""
runtime:
  mode: once
logging:
  level: WARNING
strategy:
  id: trend_following
  timeframe: 1Min
market_data:
  source: noop
  asset_class: stocks
  symbols:
    - DEMO
database:
  event_store: noop
broker:
  type: {broker_type}
backtest:
  start: "2026-01-20T12:00:00Z"
  end: "2026-01-20T12:11:00Z"
  symbols:
    - DEMO
  asset_class: stocks
  timeframe: 1Min
data_quality:
  symbols:
    - DEMO
  asset_class: stocks
  timeframe: 1Min
""",
        encoding="utf-8",
    )
    return config_path
