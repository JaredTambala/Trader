"""Qualify governed execution through Console choice and fresh-process recovery.

Subject: The actual MCP producer, persisted evidence, Console review and human decision seam.
Level: Multi-process PostgreSQL and browser qualification.
Collaborators: Real MCP, BacktestRunner, PostgreSQL, API, Next.js and Chromium;
bounded deterministic input bars and a process-owned test authenticator.
Guarantees: Unavailable independent reviews remain blockers while exact human
reject/refine decisions persist, replay idempotently and reopen after restart.
Non-goals: Model quality, independent scientific judgment, deployment authentication,
broker actions or approval to advance a strategy.
"""

from __future__ import annotations

import asyncio
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

import httpx
import psycopg
import pytest

from trader_console_api.contracts import NextResearchDecisionRecord
from trader_research.foundation import json_payload_hash
from tests.cross_package.qualification.support.uj08_campaign import REPO_ROOT, checkout_commit
from tests.cross_package.qualification.support.uj09_campaign import execute, isolated_database
from tests.cross_package.qualification.support.uj09_process import source_modules
from tests.cross_package.workflows.console_stack import free_port, server


@pytest.fixture
def uj09_postgres_settings() -> dict[str, Any]:
    """Fail required runs instead of silently omitting database/browser assertions."""
    values = {key: os.environ.get(f"UJ09_PG_{name}", "") for key, name in (
        ("host", "HOST"), ("port", "PORT"), ("dbname", "DB"),
        ("user", "USER"), ("password", "PASSWORD"),
    )}
    if not all(values.values()):
        if os.environ.get("UJ09_REQUIRED") == "1":
            pytest.fail("UJ09_REQUIRED=1 requires every UJ09_PG_* setting")
        pytest.skip("UJ09_PG_* disposable database profile is not configured")
    if not values["dbname"].endswith(("_test", "_testing")):
        raise pytest.UsageError("UJ09_PG_DB must be an explicit disposable test database")
    settings = {**values, "port": int(values["port"])}
    with psycopg.connect(**settings) as connection:
        identity = connection.execute("SELECT current_database(), current_user, current_setting('TimeZone')").fetchone()
    assert identity[:2] == (settings["dbname"], settings["user"])
    assert identity[2].upper() in {"UTC", "ETC/UTC"}
    return settings


def _process_environment(dsn: str, api_port: int, *, principal: str = "operator:jared") -> dict[str, str]:
    """Configure one owned process without exposing credentials in test artifacts."""
    return {**os.environ, "UJ09_DSN": dsn, "UJ09_API_PORT": str(api_port), "UJ09_PRINCIPAL": principal,
            "PYTHONPATH": f"{REPO_ROOT / 'src'}{os.pathsep}{REPO_ROOT}"}


def _browser(environment: dict[str, str], phase: str) -> None:
    """Run the real browser assertions with no intercepted requests or responses."""
    subprocess.run(
        ["npm", "run", "test:e2e", "--", "tests/e2e/governed-review.spec.ts",
         "--output", f"test-results/governed-review-{phase}"],
        cwd=REPO_ROOT / "apps/trader-console",
        env={**environment, "UJ09_BROWSER_CAMPAIGN": "1", "UJ09_BROWSER_PHASE": phase},
        check=True, timeout=180,
    )


def _request_from_record(record: dict[str, Any]) -> dict[str, Any]:
    """Retain exactly the editable command fields when appending a revision."""
    fields = ("decision_id", "revision", "outcome", "rationale", "source_run_ref", "data_ref",
              "implementation_refs", "assumptions", "review_refs", "session_review", "blocked_evidence",
              "limitations", "next_experiment", "supersedes_artifact_id")
    return {key: record[key] for key in fields}


def _checkout_identity() -> dict[str, Any]:
    """Identify uncommitted tested sources as well as the eventual clean CI commit."""
    paths = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=REPO_ROOT, check=True, capture_output=True, text=True,
    ).stdout.split("\0")
    hashes = {path: hashlib.sha256((REPO_ROOT / path).read_bytes()).hexdigest()
              for path in sorted(set(paths)) if path and (REPO_ROOT / path).is_file()}
    status = subprocess.run(["git", "status", "--porcelain"], cwd=REPO_ROOT,
                            check=True, capture_output=True, text=True).stdout
    return {"commit": checkout_commit(), "dirty": bool(status),
            "source_tree_sha256": json_payload_hash(hashes), "source_file_sha256": hashes}


def _exercise_commands(client: httpx.Client, run_id: str, submitted: dict[str, Any]) -> list[dict[str, Any]]:
    """Prove replay and append semantics and explicit negative command cases."""
    endpoint = f"/api/runs/{run_id}/next-decisions"
    first = submitted["record"]
    replay = client.post(endpoint, json=submitted["request"])
    assert replay.status_code == 201, replay.text
    assert replay.json() == first
    assert client.get(endpoint).json()["page"]["total"] == 1

    request = _request_from_record(first)
    request.update(revision=2, outcome="refine", rationale="Retain the missing reviews and bound the next research attempt.",
                   supersedes_artifact_id=first["artifact_id"], next_experiment={
                       "question": "Can the same declared scope support independent review?",
                       "data_ref": first["data_ref"], "implementation_refs": first["implementation_refs"],
                       "assumptions": first["assumptions"], "evaluation_start": "2026-11-01T00:00:00Z",
                       "evaluation_end": "2026-11-02T00:00:00Z", "max_runs": 1,
                       "success_criteria": ["Independent reviews exist for the exact run."],
                   })
    appended = client.post(endpoint, json=request)
    assert appended.status_code == 201, appended.text
    second = appended.json()
    assert second["revision"] == 2 and second["blocked_evidence"] == first["blocked_evidence"]
    assert client.get(f"{endpoint}/{first['decision_id']}?revision=1").json() == first
    conflict = {**submitted["request"], "rationale": "Replace an immutable choice"}
    assert client.post(endpoint, json=conflict).status_code == 409

    for field in ("source_run_ref", "data_ref", "implementation_refs", "blocked_evidence"):
        changed = deepcopy(submitted["request"])
        changed["decision_id"] = f"negative-hash-{field}"
        reference = changed[field]
        if field == "implementation_refs":
            reference = reference[0]
        elif field == "blocked_evidence":
            reference = reference["outcome_ref"]
        reference["metadata"]["payload_sha256"] = "0" * 64
        rejected = client.post(endpoint, json=changed)
        assert rejected.status_code == 422, rejected.text
    changed = deepcopy(submitted["request"])
    changed["decision_id"] = "negative-version"
    changed["implementation_refs"][0]["artifact_id"] = "nonexistent-version"
    assert client.post(endpoint, json=changed).status_code == 422
    changed["implementation_refs"][0]["uri"] = "research://postgres/implementation_version/nonexistent-version"
    assert client.post(endpoint, json=changed).status_code == 422
    changed = deepcopy(submitted["request"])
    changed["decision_id"] = "negative-erased-blockers"
    changed["blocked_evidence"]["blockers"] = []
    assert client.post(endpoint, json=changed).status_code == 422
    assert client.get(endpoint).json()["page"]["total"] == 1
    return [first, second]


@pytest.mark.postgres
def test_governed_run_console_decision_and_restart_preserve_blocked_evidence(
    uj09_postgres_settings: dict[str, Any], tmp_path: Path,
) -> None:
    """Real browser writes and new processes retain the exact blocked evidence chain."""
    app = REPO_ROOT / "apps/trader-console"
    loaded_modules = source_modules()
    api_port, web_port, agent_port = free_port(), free_port(), free_port()
    api_origin, web_origin = f"http://127.0.0.1:{api_port}", f"http://127.0.0.1:{web_port}"
    receipt_path = tmp_path / "browser-receipt.json"
    web_environment = {**os.environ, "TRADER_CONSOLE_API_ORIGIN": api_origin,
                       "CONSOLE_TEST_WEB_ORIGIN": web_origin, "CONSOLE_TEST_STACK": "1",
                       "UJ09_BROWSER_RECEIPT": str(receipt_path)}
    subprocess.run(["npm", "run", "build"], cwd=app, env=web_environment, check=True, timeout=240)
    checkout = _checkout_identity()
    with isolated_database(uj09_postgres_settings) as (campaign, settings):
        code_identity = f"git:{checkout['commit']}:tree:{checkout['source_tree_sha256']}"
        chain = asyncio.run(execute(campaign, settings, code_identity=code_identity))
        run_id = chain["job"]["produced_artifact_refs"][0]["artifact_id"]
        web_environment["UJ09_RUN_ID"] = run_id
        command = [sys.executable, "-m", "tests.cross_package.qualification.support.uj09_process", "api"]
        environment = _process_environment(campaign.dsn, api_port)
        web_command = ["node", "node_modules/next/dist/bin/next", "start", "--hostname", "127.0.0.1", "--port", str(web_port)]
        with server(web_command, web_origin, environment=web_environment, cwd=app):
            with server(command, f"{api_origin}/health/ready", environment=environment):
                with httpx.Client(base_url=api_origin, timeout=30) as client:
                    response = client.get(f"/api/runs/{run_id}/decision-basis")
                    assert response.status_code == 200, response.text
                    basis = response.json()
                    assert basis["status"] == "available", basis
                    assert basis["permitted_outcomes"] == ["reject", "refine"]
                    assert basis["evidence"]["review_refs"] == []
                    assert basis["evidence"]["blocked_evidence"]["blockers"] == chain["terminal"]["blockers"]
                    _browser(web_environment, "create")
                    submitted = json.loads(receipt_path.read_text(encoding="utf-8"))
                    records = _exercise_commands(client, run_id, submitted)

            agent_environment = _process_environment(campaign.dsn, agent_port, principal="agent:research")
            with server(command, f"http://127.0.0.1:{agent_port}/health/ready", environment=agent_environment):
                denied = httpx.post(f"http://127.0.0.1:{agent_port}/api/runs/{run_id}/next-decisions", json=submitted["request"])
                assert denied.status_code == 403, denied.text

            reopened = subprocess.run(
                [sys.executable, "-m", "tests.cross_package.qualification.support.uj09_process", "verify"],
                cwd=REPO_ROOT, check=True, capture_output=True, text=True, timeout=60,
                env={**environment, "UJ09_JOB_ID": chain["job"]["job_id"],
                     "UJ09_OUTCOME_ID": chain["terminal"]["outcome_id"],
                     "UJ09_DECISION_IDS": json.dumps([record["artifact_id"] for record in records])},
            )
            recovery = json.loads(reopened.stdout)
            assert recovery["canonical_evidence"] == chain
            for canonical, record in zip(recovery["decisions"], records, strict=True):
                public = {key: value for key, value in canonical.items() if key not in {"metadata", "schema_version"}}
                assert NextResearchDecisionRecord.model_validate(public).model_dump(mode="json") == record
            with server(command, f"{api_origin}/health/ready", environment=environment):
                with httpx.Client(base_url=api_origin, timeout=30) as client:
                    for record in records:
                        exact = client.get(f"/api/runs/{run_id}/next-decisions/{record['decision_id']}?revision={record['revision']}")
                        assert exact.status_code == 200, exact.text
                        assert exact.json() == record
                _browser(web_environment, "reopen")

        with psycopg.connect(campaign.dsn) as connection:
            assert connection.execute("SELECT count(*) FROM research_next_decisions").fetchone()[0] == 2
            postgres_version = connection.execute("SHOW server_version").fetchone()[0]
        assert _checkout_identity()["source_tree_sha256"] == checkout["source_tree_sha256"], "Sources changed during qualification"
        report = {
            "fixture_id": "uj09-execution-console-decision-v1", "verifier_version": 1,
            "checkout": checkout, "contract": "BlockedEvidenceBasis/NextResearchDecision/DecisionBasisResponse",
            "contract_sha256": json_payload_hash(json.loads((REPO_ROOT / "contracts/trader-console/openapi.json").read_text())),
            "canonical_evidence": chain, "fresh_process_recovery": recovery,
            "loaded_modules": loaded_modules,
            "decision_revisions": [record["revision"] for record in records], "postgres_version": postgres_version,
            "python_version": sys.version,
            "node_version": subprocess.run(["node", "--version"], check=True, capture_output=True, text=True).stdout.strip(),
            "npm_version": subprocess.run(["npm", "--version"], check=True, capture_output=True, text=True).stdout.strip(),
            "browser_version": submitted["browser_version"],
            "database_identity": settings["dbname"],
            "session_lineage": "available" if basis["evidence"]["blocked_evidence"]["session_ref"] else "unavailable",
            "command": "UJ09_REQUIRED=1 uv run pytest tests/cross_package/qualification/test_uj09_postgres_browser_campaign.py -m postgres -q",
            "assertions": ["real_mcp_producer", "real_browser_submission", "exact_canonical_pins", "idempotent_replay",
                           "append_only_history", "agent_authority_rejected", "changed_hash_version_blockers_rejected",
                           "fresh_process_canonical_recovery", "api_restart_browser_reopen"],
            "limits": ["Deterministic fixture; no model-backed behavior qualified.",
                       "Independent scientific review producers remain unavailable.",
                       "Test authenticator; deployment authentication is not qualified.",
                       "No graph fabricated for the declared canonical session."],
        }
        evidence_path = Path(os.environ.get("UJ09_EVIDENCE_PATH", str(tmp_path / "uj09-verifier.json")))
        evidence_path.write_text(json.dumps(report, sort_keys=True, indent=2), encoding="utf-8")
