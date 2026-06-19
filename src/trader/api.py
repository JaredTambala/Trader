"""REST API for starting and inspecting UI-driven backtests.

The API keeps lightweight in-memory run progress for active requests while also
persisting completed backtest results to the configured event store so results
can survive process restarts.
"""

from __future__ import annotations

from argparse import ArgumentParser
from datetime import datetime, timezone
from threading import Thread
from typing import Any, Mapping

import json
import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from .backtest import BacktestRunner, BacktestSpec, persist_backtest_result, serialize_backtest_result
from .event_store import build_event_store
from .config import build_config, load_yaml_config
from .identifiers import deterministic_run_session_id
from .timeframes import normalize_timeframe


class BacktestRequest(BaseModel):
    """Validated request body for creating a backtest run.

    Attributes:
        symbols: Non-empty symbol universe requested by the UI.
        timeframe: User-supplied timeframe normalized before replay.
        start: Inclusive replay window start timestamp.
        end: Inclusive replay window end timestamp.
        asset_class: Market-data table/source family to use.
        initial_cash: Cash balance seeded before the first cycle.
        strategy_params: Optional UI payload preserved for provenance.
        max_runs: Optional cap for short exploratory runs.
    """

    symbols: list[str]
    timeframe: str
    start: datetime
    end: datetime
    asset_class: str = Field(default="stocks")
    initial_cash: float = Field(default=0.0, ge=0.0)
    strategy_params: Mapping[str, Any] | None = None
    max_runs: int | None = None


class BacktestResponse(BaseModel):
    """Response body returned after a backtest worker has been queued.

    Attributes:
        run_id: Deterministic run-session identifier used for progress and
            result polling.
    """

    run_id: str


load_dotenv(".env")
app = FastAPI(title="Trader backend")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Shared runtime state
BACKEND_CONFIG_PATH: str | None = os.environ.get("BACKEND_CONFIG_PATH")
BACKEND_CONFIG_DATA: Mapping[str, Any] | None = None
BACKEND_CONFIG: object | None = None
BACKTEST_RUNS: dict[str, dict[str, Any]] = {}


def _sanitize_serializable(value: Any) -> Any:
    """Recursively convert datetimes and containers into JSON-safe values."""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _sanitize_serializable(v) for k, v in value.items()}
    if isinstance(value, list) or isinstance(value, tuple):
        return [_sanitize_serializable(v) for v in value]
    return value

def _run_backtest_worker(run_id: str, request: BacktestRequest) -> None:
    """Execute one requested backtest and update shared run state.

    The worker normalizes the request, builds a runner from the startup config,
    updates progress after each replay timestamp, persists the final result to
    the metrics table, and stores a sanitized copy in memory for fast UI reads.
    Exceptions are captured into the run state so the API can report failure
    without terminating the server process.
    """
    state = BACKTEST_RUNS.setdefault(run_id, {})
    state["status"] = "running"
    try:
        spec = BacktestSpec(
            start=request.start,
            end=request.end,
            timeframe=normalize_timeframe(request.timeframe),
            max_runs=request.max_runs,
        )
        config = BACKEND_CONFIG
        if config is None:
            raise RuntimeError("Backend config not initialized")
        runner = BacktestRunner(
            config=config,
            spec=spec,
            symbols=request.symbols,
            asset_class=request.asset_class,
            initial_cash=request.initial_cash,
            config_snapshot={"payload": request.dict(), "base_config": BACKEND_CONFIG_DATA},
        )
        # Attach progress callback to update run state
        def _progress(processed: int, total: int, last_ts: datetime | None) -> None:
            percent = 100.0 if total == 0 else min(100.0, (processed / total * 100))
            state["progress"] = {
                "processed": processed,
                "total": total,
                "percent": round(percent, 2),
                "last_ts": last_ts.isoformat() if last_ts else None,
            }

        result = runner.run(progress_callback=_progress)
        persist_backtest_result(run_id, result, BACKEND_CONFIG)
        progress = state.setdefault("progress", {})
        progress["percent"] = 100.0
        progress["processed"] = progress.get("total", progress.get("processed", 0))
        state["status"] = "completed"
        state["finished_at"] = datetime.now(timezone.utc)
        state["result"] = serialize_backtest_result(result)
    except Exception as exc:  # pragma: no cover - serious failure
        state["status"] = "failed"
        state["finished_at"] = datetime.now(timezone.utc)
        progress = state.setdefault("progress", {})
        progress["percent"] = 0.0
        state["error"] = str(exc)


@app.on_event("startup")
def _load_config() -> None:
    """Load backend config once during FastAPI startup.

    The config path must be provided through `BACKEND_CONFIG_PATH`. The parsed
    YAML data is retained for provenance, while the typed config object is used
    by workers and persisted-result lookups.
    """
    global BACKEND_CONFIG_PATH, BACKEND_CONFIG_DATA, BACKEND_CONFIG
    if not BACKEND_CONFIG_PATH:
        raise RuntimeError("BACKEND_CONFIG_PATH must be set before startup")
    data = load_yaml_config(BACKEND_CONFIG_PATH)
    config = build_config(data)
    BACKEND_CONFIG_DATA = data
    BACKEND_CONFIG = config


@app.post("/backtest", response_model=BacktestResponse)
def start_backtest(request: BacktestRequest) -> BacktestResponse:
    """Validate a request, register run progress, and start a worker thread.

    Returns immediately with a deterministic run-session ID while the replay
    continues in a daemon thread. The in-memory state is initialized before the
    worker starts so progress polling never races with run creation.
    """
    if not request.symbols:
        raise HTTPException(status_code=400, detail="symbols list cannot be empty")
    if request.start >= request.end:
        raise HTTPException(status_code=400, detail="start must be before end")
    run_id = deterministic_run_session_id("backtest", datetime.now(timezone.utc))
    BACKTEST_RUNS[run_id] = {
        "status": "queued",
        "started_at": datetime.now(timezone.utc),
        "request": _sanitize_serializable(request.dict()),
        "result": None,
        "error": None,
        "progress": {"processed": 0, "total": 0, "percent": 0.0, "last_ts": None},
    }
    worker = Thread(target=_run_backtest_worker, args=(run_id, request), daemon=True)
    worker.start()
    return BacktestResponse(run_id=run_id)


@app.get("/backtest/progress")
def get_backtest_progress(run_id: str) -> Mapping[str, Any]:
    """Return current in-memory progress for a queued or running backtest.

    Raises:
        HTTPException: If the requested run ID is unknown to this process.
    """
    state = BACKTEST_RUNS.get(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail="run_id not found")
    return {
        "run_id": run_id,
        "status": state.get("status", "unknown"),
        "progress": state.get("progress", {}),
        "error": state.get("error"),
    }


def _query_metrics_snapshot(run_id: str) -> Mapping[str, object] | None:
    """Read the latest persisted aggregate result for a completed backtest."""
    config = BACKEND_CONFIG
    if config is None:
        return None
    event_store = build_event_store(config)
    try:
        conn = getattr(event_store, "connection", lambda: None)()
        if conn is None or not hasattr(conn, "cursor"):
            return None
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT payload, ts, cycle_id
                FROM metrics_snapshots
                WHERE run_id = %s
                ORDER BY ts DESC
                LIMIT 1
                """,
                [run_id],
            )
            row = cursor.fetchone()
            if row is None:
                return None
            payload = row[0]
            if isinstance(payload, str):
                payload = json.loads(payload)
            return {
                "payload": payload,
                "ts": row[1].isoformat() if row[1] is not None else None,
                "cycle_id": row[2],
            }
    finally:
        event_store.close()


@app.get("/backtest/result")
def get_backtest_result(run_id: str) -> Mapping[str, Any]:
    """Return a completed backtest result from memory or durable storage.

    The in-memory result is preferred for active server processes. If it is not
    available, the endpoint falls back to the metrics snapshot written at worker
    completion and returns `404` only when neither source has the run.
    """
    state = BACKTEST_RUNS.get(run_id)
    if state and state.get("result") is not None:
        return {
            "run_id": run_id,
            "status": state.get("status", "completed"),
            "result": state["result"],
        }
    snapshot = _query_metrics_snapshot(run_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="result not found")
    return {
        "run_id": run_id,
        "status": "completed",
        "result": snapshot["payload"],
        "snapshot_ts": snapshot["ts"],
        "cycle_id": snapshot["cycle_id"],
    }



def main() -> None:
    """Parse server options, set the config path, and launch uvicorn.

    The config path is placed in the environment so FastAPI startup uses the
    same loading path as tests and deployed processes.
    """
    parser = ArgumentParser(description="Run the Trader backtest API.")
    parser.add_argument("config", help="Path to the YAML configuration.")
    parser.add_argument("--host", default="0.0.0.0", help="Host for the HTTP server.")
    parser.add_argument("--port", type=int, default=8000, help="Port for the HTTP server.")
    args = parser.parse_args()
    os.environ["BACKEND_CONFIG_PATH"] = args.config
    import uvicorn

    uvicorn.run(
        "trader.api:app",
        host=args.host,
        port=args.port,
        reload=False,
    )


if __name__ == "__main__":
    main()
