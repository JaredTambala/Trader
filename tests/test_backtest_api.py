"""API tests for the UI-driven backtest runner."""

from __future__ import annotations

import importlib
import os
from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi.testclient import TestClient

import trader.web.api as api


class _ImmediateThread:
    """Thread stub that runs immediately on start."""

    def __init__(self, *, target: Any, args: tuple[Any, ...], daemon: bool) -> None:
        self._target = target
        self._args = args
        self.daemon = daemon

    def start(self) -> None:
        self._target(*self._args)


@pytest.fixture(autouse=True)
def api_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Create a TestClient for the FastAPI app with simplified workers."""
    config = {
        "runtime": {"mode": "once"},
        "strategy": {"type": "noop", "timeframe": "1Min", "id": "noop"},
        "market_data": {"symbols": "AAPL", "asset_class": "stocks"},
        "database": {"event_store": "noop"},
        "broker": {"type": "noop"},
        "logging": {"persist": {"signals": False, "indicators": False, "orders": False, "fills": False, "positions": False}},
    }
    cfg_file = tmp_path / "test_config.yaml"
    cfg_file.write_text(yaml.dump(config))
    os.environ["BACKEND_CONFIG_PATH"] = str(cfg_file)
    importlib.reload(api)

    def fake_worker(run_id: str, request: api.BacktestRequest) -> None:
        state = api.BACKTEST_RUNS.setdefault(run_id, {})
        state["status"] = "running"
        state["progress"] = {
            "processed": 1,
            "total": 1,
            "percent": 50.0,
            "last_ts": request.start.isoformat(),
        }
        state["result"] = {"run_id": run_id, "strategy_performance": {"total_return": 0.0}}
        state["status"] = "completed"
        state["progress"]["percent"] = 100.0
        state["progress"]["processed"] = 1

    monkeypatch.setattr(api, "Thread", lambda *, target, args, daemon: _ImmediateThread(target=target, args=args, daemon=daemon))
    monkeypatch.setattr(api, "_run_backtest_worker", fake_worker)

    yield TestClient(api.app)


def test_post_backtest_returns_run_id(api_client: TestClient) -> None:
    """POST /backtest should return a generated run_id."""
    payload = {
        "symbols": ["AAPL"],
        "timeframe": "1Min",
        "start": "2026-01-01T00:00:00Z",
        "end": "2026-01-01T01:00:00Z",
    }
    response = api_client.post("/backtest", json=payload)
    assert response.status_code == 200
    data = response.json()
    run_id = data["run_id"]
    assert run_id in api.BACKTEST_RUNS
    assert api.BACKTEST_RUNS[run_id]["status"] == "completed"


def test_get_backtest_progress(api_client: TestClient) -> None:
    """GET /backtest/progress returns progress metadata."""
    run_id = "test-progress"
    api.BACKTEST_RUNS[run_id] = {
        "status": "running",
        "progress": {"processed": 2, "total": 5, "percent": 40.0, "last_ts": None},
        "error": None,
    }
    response = api_client.get("/backtest/progress", params={"run_id": run_id})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "running"
    assert data["progress"]["percent"] == 40.0


def test_get_backtest_result_returns_cached_payload(api_client: TestClient) -> None:
    """GET /backtest/result returns the cached payload when available."""
    run_id = "cached-result"
    api.BACKTEST_RUNS[run_id] = {
        "status": "completed",
        "result": {"run_id": run_id},
    }
    response = api_client.get("/backtest/result", params={"run_id": run_id})
    assert response.status_code == 200
    data = response.json()
    assert data["result"]["run_id"] == run_id


def test_get_backtest_result_404_when_missing(api_client: TestClient) -> None:
    """GET /backtest/result should 404 for unknown run_id and missing snapshot."""
    response = api_client.get("/backtest/result", params={"run_id": "missing"})
    assert response.status_code == 404
