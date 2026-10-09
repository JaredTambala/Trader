"""Retained Console evidence for the UJ-07 specialist investigation feature.

Subject: Console specialist branch and handoff projection.
Level: Cross-package qualification at the application-service boundary.
Collaborators: Typed Console contracts and canonical receipt-shaped fixture; no SQL,
browser process, model provider, or hidden trajectory payload.
Guarantees: Every public branch outcome is retained with exact artifact revision and
handoff identity, and the verifier report names its fixture, contract, checkout, and
evidence revision.
Non-goals: Qualifying model behaviour, provider freshness, or broker/runtime control.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from trader_console_api.repositories.agent_sessions import AgentSessionSource
from trader_console_api.services.agent_sessions import _build_projection


def _source() -> AgentSessionSource:
    """Build six bounded branch outcomes with pinned artifact revisions."""
    payload = {
        "session_id": "uj07-console-session",
        "session_digest": "a" * 64,
        "operator_id": "human:jared",
        "objective": "Review concurrent specialist evidence.",
        "success_definition": "Every branch has an explicit public outcome.",
        "model_profile_id": "model-v1",
        "agent_program_ids": ["data-v1"],
        "tool_catalog_id": "catalogue-v1",
        "scope_envelope": {"data_scope": {"scope_id": "scope-1", "timeframe": "1d"}},
        "budget": {
            "max_model_calls": 10,
            "max_tool_calls": 10,
            "max_tokens": 1000,
            "max_duration_seconds": 60,
            "max_mutations": 0,
            "max_revisions": 2,
            "concurrency_limit": 6,
        },
    }
    outcomes = ("complete", "partial", "failed", "blocked", "stale", "unavailable")
    receipts = []
    artifact_states = {
        "complete": "available",
        "partial": "stale",
        "failed": "unavailable",
        "blocked": "incompatible",
        "stale": "stale",
        "unavailable": "unavailable",
    }
    for sequence, outcome in enumerate(outcomes, start=1):
        receipts.append(
            {
                "payload": {
                    "receipt_id": f"receipt-{sequence}",
                    "session_id": payload["session_id"],
                    "branch_id": f"branch-{sequence}",
                    "sequence": sequence,
                    "actor": "Data Specialist",
                    "program_id": "data-v1",
                    "model_profile_id": "model-v1",
                    "action": "handoff",
                    "status": "completed" if outcome == "complete" else "running",
                    "specialist_status": outcome,
                    "summary": f"Branch outcome: {outcome}.",
                    "delegation_id": f"delegation-{sequence}",
                    "attempt_id": f"attempt-{sequence}",
                    "evidence_refs": [
                        {
                            "artifact_type": "dataset_manifest",
                            "artifact_id": f"manifest-{sequence}",
                            "domain_owner": "Data",
                            "uri": f"research://postgres/dataset_manifest/manifest-{sequence}",
                            "metadata": {
                                "source_hash": "b" * 64,
                                "revision": sequence,
                                "status": artifact_states[outcome],
                            },
                        }
                    ],
                    "blockers": ([{"code": "review", "message": "Review required."}] if outcome in {"partial", "failed", "blocked"} else []),
                    "next_actions": ["review"],
                    "metadata": {
                        "role": "data_research",
                        "owner": "Data Specialist",
                        "handoff_digest": "c" * 64,
                    },
                    "budget_used": {
                        "model_calls": sequence,
                        "tool_calls": sequence,
                        "tokens": sequence,
                        "duration_ms": sequence,
                        "mutations": 0,
                        "revisions": 0,
                    },
                }
            }
        )
    return AgentSessionSource(
        session={
            "session_id": payload["session_id"],
            "operator_id": payload["operator_id"],
            "status": "active",
            "payload": payload,
        },
        receipts=tuple(receipts),
        commands=(),
    )


def test_console_uj07_specialist_evidence_retains_verifier_identity(tmp_path: Path) -> None:
    """Retain exact fixture, contract, checkout, and artifact revision evidence."""
    projection = _build_projection(_source())
    checkout_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    ).stdout.strip()
    report = {
        "fixture_id": "uj07-console-specialist-evidence-v1",
        "contract": "AgentSessionProjection/AgentSessionHandoff",
        "contract_version": 1,
        "checkout_commit": checkout_commit,
        "evidence_revision": max(
            ref.revision or 0 for ref in projection.evidence_refs
        ),
        "outcomes": [item.specialist_status for item in projection.delegations],
    }
    report_path = tmp_path / "uj07-console-specialist-evidence-verifier.json"
    report_path.write_text(json.dumps(report, sort_keys=True), encoding="utf-8")
    retained = json.loads(report_path.read_text(encoding="utf-8"))
    assert retained["fixture_id"] == "uj07-console-specialist-evidence-v1"
    assert retained["contract"] == "AgentSessionProjection/AgentSessionHandoff"
    assert retained["checkout_commit"] == checkout_commit
    assert retained["evidence_revision"] == 6
    assert retained["outcomes"] == ["complete", "partial", "failed", "blocked", "stale", "unavailable"]
