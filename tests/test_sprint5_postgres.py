from __future__ import annotations

from pathlib import Path

import pytest

from trader.tools.discovery import DiscoveryRequest, run_discovery


@pytest.mark.postgres
def test_discovery_sample_workflow_persists_experiment_runs(
    postgres_settings: dict[str, object],
    tmp_path: Path,
) -> None:
    config_data = {
        "runtime": {"mode": "once"},
        "logging": {"level": "WARNING"},
        "strategy": {
            "id": "trend_following",
            "timeframe": "1Min",
            "trend_following": {
                "ema_fast_period": 2,
                "ema_slow_period": 4,
                "macd_fast_period": 3,
                "macd_slow_period": 6,
                "macd_signal_period": 3,
            },
        },
        "market_data": {"source": "noop", "asset_class": "stocks", "symbols": ["DEMO"]},
        "database": {
            "event_store": "postgres",
            "pg": {
                "host": postgres_settings["host"],
                "port": postgres_settings["port"],
                "db": postgres_settings["dbname"],
                "user": postgres_settings["user"],
                "password": postgres_settings["password"],
            },
        },
        "broker": {"type": "internal"},
        "backtest": {
            "start": "2026-01-20T12:00:00Z",
            "end": "2026-01-20T12:11:00Z",
            "symbols": ["DEMO"],
            "asset_class": "stocks",
            "timeframe": "1Min",
            "initial_cash": 1000,
            "initial_positions": [],
            "assumptions": {
                "fees": {"fixed_per_order": 0.1, "bps": 0, "minimum_fee": 0.1},
                "slippage": {"bps": 10},
            },
        },
        "data_quality": {
            "symbols": ["DEMO"],
            "asset_class": "stocks",
            "timeframe": "1Min",
        },
    }
    request = DiscoveryRequest(
        symbols=("DEMO",),
        asset_class="stocks",
        timeframe="1Min",
        strategy_families=("trend_following", "mean_reversion"),
        data_mode="sample",
        max_runs=2,
        output_dir=str(tmp_path / "discovery"),
        experiment_name=f"sprint5_postgres_smoke_{tmp_path.name}",
    )

    envelope = run_discovery(config_data, request)
    payload = envelope.to_dict()

    assert payload["ok"] is True
    assert payload["side_effect"] == "local_mutating"
    assert len(payload["data"]["runs"]) == 2
    assert len(payload["data"]["comparison"]["rows"]) >= 2
    assert payload["data"]["recommendations"]["recommendation_id"].startswith("rec_")
    assert Path(payload["artifacts"]["comparison"]).exists()
