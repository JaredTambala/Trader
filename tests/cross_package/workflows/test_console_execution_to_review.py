"""Real Console execution-to-review qualification.

Subject: Data scope → immutable definition → durable worker → BacktestRunner →
Console review → human next decision.
Level: Multi-process PostgreSQL/API/worker qualification.
Collaborators: Test-owned Docker PostgreSQL, the real Console API, the local
worker entrypoint, the maintained strategy catalogue, and producer-owned read
projections.
Guarantees: One exact saved scope survives authoring and a concrete worker
execution; the deterministic run is reviewable with assumptions, risk, fills,
warnings, scope identity, comparison eligibility, and a human decision. A
worker restart or idempotent command replay does not create a second run.
Non-goals: Funded-live trading, external provider calls, statistical claims,
and the browser rendering assertions owned by the Console Playwright journey.
Failure-state coverage: Focused worker/API tests cover failed and ambiguous
outcomes; this qualification proves a fresh worker process reconciles an
expired reserved run without replaying it. The same full journey proves
standalone comparison is explicitly ineligible.
Cohesion: The module stays one owned Console execution-to-review workflow;
its restart assertions reuse the same isolated command store and frozen run.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import sha256
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any

import httpx
import psycopg
from psycopg.types.json import Jsonb
import pytest

from examples.console_demo.runtime import bootstrap, demo_dsn
from tests.cross_package.workflows.console_stack import (
    REPO_ROOT,
    api_command,
    database,
    free_port,
    server,
)
from tests.trader_console_api.support import implementation_lineage
from trader_research.foundation import research_artifact_uri


pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        os.environ.get("CONSOLE_EXECUTION_TESTS") != "1",
        reason="Set CONSOLE_EXECUTION_TESTS=1 to provision a test-owned Docker database",
    ),
]


BASE_TS = datetime(2026, 6, 21, 0, 0, tzinfo=UTC)
SYMBOL = "QUALIFIED/USD"
SCOPE_ID = "00000000-0000-0000-0000-000000000041"


def _insert_fixture_bars(port: int) -> None:
    """Seed warmup and replay bars in the database owned by this test."""
    with psycopg.connect(demo_dsn(port)) as connection:
        # Twenty-one warmup bars satisfy the maintained Bollinger catalogue;
        # the first two replay bars create a deterministic entry and exit.
        prices = [100.0] * 21 + [80.0, 100.0, 102.0, 101.0, 103.0]
        for index, price in enumerate(prices):
            ts = BASE_TS - timedelta(minutes=21 - index) if index < 21 else BASE_TS + timedelta(minutes=index - 21)
            connection.execute(
                """
                INSERT INTO crypto_bar_events
                    (symbol, timeframe, ts, ingested_at, open, high, low, close, volume, source)
                VALUES (%s, '1Min', %s, %s, %s, %s, %s, %s, %s, 'fixture')
                """,
                [SYMBOL, ts, ts, price, price + 1.0, price - 1.0, price, 1_000.0 + index],
            )


def _config_file(tmp_path: Path, port: int) -> Path:
    """Write the explicit core configuration consumed by the worker process."""
    path = tmp_path / "console-backtest.yaml"
    path.write_text(
        f"""runtime:\n  mode: once\nlogging:\n  persist:\n    signals: true\n    indicators: true\n    orders: true\n    fills: true\n    positions: true\nstrategy:\n  id: console-qualification\n  timeframe: 1Min\nbroker:\n  type: internal\n  time_in_force: day\nmarket_data:\n  source: fixture\n  asset_class: crypto\n  symbols: [{SYMBOL}]\ndatabase:\n  event_store: postgres\n  pg:\n    host: 127.0.0.1\n    port: {port}\n    db: trader_console_demo\n    user: console_demo\n    password: console_demo_local\nmetrics:\n  enable_snapshots: false\n  interval_seconds: 0\n""",
        encoding="utf-8",
    )
    return path


def _scope_payload() -> dict[str, Any]:
    """Return one exact saved-scope request for the deterministic fixture."""
    return {
        "name": "Execution qualification scope",
        "asset_class": "crypto",
        "symbols": [SYMBOL],
        "universe": None,
        "timeframe": "1Min",
        "interval": "1Min",
        "start": BASE_TS.isoformat(),
        "end": (BASE_TS + timedelta(minutes=4)).isoformat(),
        "source_policy": {"provider": "fixture", "source": "fixture", "allow_fallback": False},
        "research_role": "backtest_authoring",
        "manifest_artifact_id": "qualification-manifest",
        "quality_artifact_id": "qualification-quality",
        "evidence_status": "active",
        "created_by": "human:console-demo",
        "idempotency_key": "qualification-scope-v1",
    }


def _definition_payload(scope: dict[str, Any]) -> dict[str, Any]:
    """Carry the saved scope and admitted implementation lineage into authoring."""
    strategy = implementation_lineage("bollinger_band")
    risk = implementation_lineage("noop", kind="risk", suffix="risk")
    handoff = {
        key: scope[key]
        for key in (
            "saved_scope_id", "fingerprint", "asset_class", "symbols", "universe",
            "timeframe", "interval", "start", "end", "source_policy",
            "manifest_artifact_id", "quality_artifact_id", "evidence_status", "evidence_reason",
        )
    }
    return {
        "display_name": "Console execution qualification",
        "strategy_profile_id": "bollinger_band",
        "strategy_catalogue_version": "standard-1",
        "strategy_parameters": {"period": 20, "stddev_multiplier": 2.0, "target_qty_when_long": 1.0},
        "strategy_implementation_lineage": strategy.model_dump(mode="json"),
        "risk_profile_id": "noop",
        "risk_catalogue_version": "standard-1",
        "risk_parameters": {},
        "risk_implementation_lineage": risk.model_dump(mode="json"),
        "asset_class": "crypto",
        "symbols": [SYMBOL],
        "timeframe": "1Min",
        "start": scope["start"],
        "end": scope["end"],
        "initial_cash": 100_000.0,
        "initial_positions": [],
        "assumptions": {
            "fill_model": "full_fill",
            "latency_ms": 0,
            "fee_fixed_per_order": 0.0,
            "fee_bps": 1.0,
            "fee_minimum": 0.0,
            "slippage_bps": 2.0,
            "allow_latest_prior_bar": True,
            "allow_price_carry_forward": True,
        },
        "benchmark_id": "buy_hold",
        "resource_limits": {"max_cycles": 100, "max_bars": 1_000, "timeout_seconds": 120},
        "data_scope": handoff,
    }


def _run_worker(config_path: Path, port: int) -> subprocess.CompletedProcess[str]:
    """Run one real worker process against the test-owned command queue."""
    environment = dict(
        os.environ,
        TRADER_CONSOLE_DATABASE_URL=demo_dsn(port),
        TRADER_CONSOLE_SCOPE_ID="console-demo",
        TRADER_CONSOLE_SCOPE_ENVIRONMENT="synthetic_demo",
        TRADER_CONSOLE_BACKTEST_CONFIG_PATH=str(config_path),
        TRADER_CONSOLE_WORKER_ID="qualification-worker",
    )
    return subprocess.run(
        [sys.executable, "-m", "trader_console_api.worker_entrypoint", "--once"],
        cwd=REPO_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=180,
    )


def _wait_for_terminal(client: httpx.Client, execution_id: str) -> dict[str, Any]:
    """Poll the durable command until the worker records a terminal state."""
    terminal = {"completed", "partial", "failed", "reconciliation_required"}
    for _ in range(120):
        response = client.get(f"/api/backtests/executions/{execution_id}")
        response.raise_for_status()
        record = response.json()
        if record["status"] in terminal:
            return record
        time.sleep(0.25)
    raise AssertionError("backtest worker did not reach a terminal state")


def _seed_review_artifacts(port: int, run_id: str, scope_fingerprint: str) -> None:
    """Seed canonical review artifacts required by the human decision command."""
    artifacts = [
        (
            "backtest_run", run_id, "Experiments", "backtest_worker",
            "completed", {"run_id": run_id, "scope_fingerprint": scope_fingerprint},
        ),
        (
            "dataset_manifest", "qualification-manifest", "Data", "data_fixture",
            "active", {"scope_fingerprint": scope_fingerprint, "run_id": run_id},
        ),
        (
            "implementation_validation", "qualification-implementation", "Strategy", "strategy_fixture",
            "passed", {"run_id": run_id},
        ),
        (
            "implementation_version", "qualification-implementation", "Experiments", "strategy_fixture",
            "admitted", {"run_id": run_id},
        ),
        (
            "evaluation_report", "qualification-evaluation", "Review", "evaluation_fixture",
            "passed", {
                "run_id": run_id,
                "claim_scope": {"run_id": run_id, "scope_fingerprint": scope_fingerprint},
            },
        ),
    ]
    with psycopg.connect(demo_dsn(port)) as connection:
        for artifact_type, artifact_id, owner, producer, status, payload in artifacts:
            metadata = (
                {"session_id": "qualification-review-session", "session_digest": sha256(run_id.encode()).hexdigest(),
                 "graph_digest": sha256(f"{run_id}:review-graph".encode()).hexdigest(),
                 "branch_id": "evaluation", "revision": 1}
                if artifact_type == "evaluation_report" else {}
            )
            connection.execute(
                """
                INSERT INTO research_artifacts
                    (artifact_type, artifact_id, domain_owner, producer_tool, status, schema_version, source_hash, metadata, payload)
                VALUES (%s, %s, %s, %s, %s, '1', %s, %s, %s)
                ON CONFLICT (artifact_type, artifact_id) DO UPDATE
                SET status = EXCLUDED.status, metadata = EXCLUDED.metadata, payload = EXCLUDED.payload
                """,
                [artifact_type, artifact_id, owner, producer, status, f"hash-{artifact_id}",
                 Jsonb(metadata), Jsonb(payload)],
            )


def test_real_execution_survives_replay_and_reaches_review_decision(tmp_path: Path) -> None:
    """Prove one fresh data-to-review run through the real worker and API."""
    with database() as (port, _compose, _environment):
        bootstrap(port)
        _insert_fixture_bars(port)
        api_port = free_port()
        origin = f"http://127.0.0.1:{api_port}"
        with server(api_command(port, api_port), f"{origin}/health/ready"):
            with httpx.Client(base_url=origin, timeout=15) as client:
                scope_response = client.post("/api/data-scopes", json=_scope_payload())
                assert scope_response.status_code == 201, scope_response.text
                scope = scope_response.json()
                reopened = client.get(f"/api/data-scopes/{scope['saved_scope_id']}")
                reopened.raise_for_status()
                assert reopened.json()["fingerprint"] == scope["fingerprint"]

                definition_response = client.post(
                    "/api/backtests/definitions", json=_definition_payload(scope)
                )
                assert definition_response.status_code == 201, definition_response.text
                definition = definition_response.json()
                execution_response = client.post(
                    "/api/backtests/executions",
                    json={
                        "definition_id": definition["definition_id"],
                        "idempotency_key": "qualification-execution-v1",
                    },
                )
                assert execution_response.status_code == 202, execution_response.text
                queued = execution_response.json()

                config_path = _config_file(tmp_path, port)
                worker = _run_worker(config_path, port)
                assert worker.returncode == 0, worker.stderr or worker.stdout
                completed = _wait_for_terminal(client, queued["execution_id"])
                assert completed["status"] == "completed", completed
                assert completed["run_id"]

                replay = client.post(
                    "/api/backtests/executions",
                    json={
                        "definition_id": definition["definition_id"],
                        "idempotency_key": "qualification-execution-v1",
                    },
                )
                assert replay.status_code == 202
                assert replay.json()["execution_id"] == queued["execution_id"]
                assert replay.json()["run_id"] == completed["run_id"]

                restarted = _run_worker(config_path, port)
                assert restarted.returncode == 0, restarted.stderr or restarted.stdout
                with psycopg.connect(demo_dsn(port)) as connection:
                    assert connection.execute(
                        "SELECT count(*) FROM runs WHERE run_id = %s",
                        [completed["run_id"]],
                    ).fetchone() == (1,)

                run_id = completed["run_id"]
                detail_response = client.get(f"/api/runs/{run_id}")
                assert detail_response.status_code == 200, detail_response.text
                detail = detail_response.json()
                assert detail["run"]["status"] == "success"
                assert detail["run"]["comparison_eligible"] is True
                assert detail["run"]["comparison_exclusion_reason"] is None
                assert detail["scope"]["scope_fingerprint"].startswith("sha256:")
                assert detail["scope"]["data_scope_fingerprint"] == scope["fingerprint"]
                assert detail["scope"]["saved_scope_id"] == scope["saved_scope_id"]
                assert detail["assumptions"]["fill_model"] == "full_fill"
                assert detail["risk_summary"]["risk_evidence_status"] == "recorded"
                assert detail["fills"], detail
                assert "warnings" in detail

                _seed_review_artifacts(port, run_id, detail["scope"]["scope_fingerprint"])
                decision_payload = {
                    "decision_id": "qualification-decision",
                    "revision": 1,
                    "outcome": "reject",
                    "rationale": "The bounded fixture is useful evidence but does not support advancement.",
                    "source_run_ref": {
                            "artifact_id": run_id,
                            "artifact_type": "backtest_run",
                            "domain_owner": "Experiments",
                        "uri": research_artifact_uri("backtest_run", run_id),
                    },
                    "data_ref": {
                        "artifact_id": "qualification-manifest",
                        "artifact_type": "dataset_manifest",
                        "domain_owner": "Data",
                        "uri": research_artifact_uri("dataset_manifest", "qualification-manifest"),
                        "metadata": {"scope_fingerprint": detail["scope"]["scope_fingerprint"]},
                    },
                    "implementation_refs": [{
                        "artifact_id": "qualification-implementation",
                        "artifact_type": "implementation_version",
                        "domain_owner": "Experiments",
                        "uri": research_artifact_uri("implementation_version", "qualification-implementation"),
                    }],
                    "assumptions": {"fixture": "deterministic"},
                    "review_refs": [{
                            "artifact_id": "qualification-evaluation",
                            "artifact_type": "evaluation_report",
                            "domain_owner": "Review",
                        "uri": research_artifact_uri("evaluation_report", "qualification-evaluation"),
                    }],
                    "limitations": ["Single deterministic fixture window"],
                }
                decision_response = client.post(
                    f"/api/runs/{run_id}/next-decisions", json=decision_payload
                )
                assert decision_response.status_code == 201, decision_response.text
                decision = decision_response.json()
                assert decision["outcome"] == "reject"
                listed = client.get(f"/api/runs/{run_id}/next-decisions")
                assert listed.status_code == 200, listed.text
                assert listed.json()["items"][0]["artifact_id"] == decision["artifact_id"]

                reserved = client.post(
                    "/api/backtests/executions",
                    json={
                        "definition_id": definition["definition_id"],
                        "idempotency_key": "qualification-expired-reservation",
                    },
                )
                assert reserved.status_code == 202, reserved.text
                reserved_id = reserved.json()["execution_id"]
                with psycopg.connect(demo_dsn(port)) as connection:
                    connection.execute(
                        "UPDATE console_app.backtest_executions "
                        "SET status = 'running', attempt = 1, worker_id = 'lost-worker', "
                        "run_id = 'reserved-without-producer-proof', "
                        "started_at = transaction_timestamp() - interval '2 minutes', "
                        "heartbeat_at = transaction_timestamp() - interval '2 minutes', "
                        "lease_expires_at = transaction_timestamp() - interval '1 minute' "
                        "WHERE execution_id = %s",
                        [reserved_id],
                    )
                recovered = _run_worker(config_path, port)
                assert recovered.returncode == 0, recovered.stderr or recovered.stdout
                status = _wait_for_terminal(client, reserved_id)
                assert status["status"] == "reconciliation_required"
                assert status["terminal_error_code"] == "worker_lease_expired"
                assert status["run_id"] == "reserved-without-producer-proof"
                with psycopg.connect(demo_dsn(port)) as connection:
                    assert connection.execute(
                        "SELECT count(*) FROM runs WHERE run_id = %s",
                        ["reserved-without-producer-proof"],
                    ).fetchone() == (0,)
