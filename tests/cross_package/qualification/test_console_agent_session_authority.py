"""UJ-04 Console and retained-trajectory identity qualification.

Subject: Public session identity, authority, and terminal evidence lineage.
Level: Deterministic cross-package contract qualification.
Collaborators: Real Console projection and retained agent verifier; no database,
browser, third-party model, hidden checkpoint, or network.
Guarantees: Both public surfaces identify the same session, runtime pins,
root branch, and terminal artifact, with only inspect available at termination.
Non-goals: Browser layout, worker persistence, and real-model acceptance.
"""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import subprocess

from trader_agents import AgentEventName, verify_retained_trajectory
from trader_console_api.repositories.agent_sessions import AgentSessionSource
from trader_console_api.services.agent_sessions import _build_projection
from tests.trader_agents.observability.support.session_qualification import (
    QUALIFICATION_MODEL_PROFILE_ID,
    QUALIFICATION_PROGRAM_ID,
    QUALIFICATION_TOOL_CATALOG_ID,
    build_session_qualification_fixture,
    qualification_identity,
)


def test_console_and_verifier_share_public_terminal_identity(tmp_path: Path) -> None:
    """Retain a verifier report joining exact public Console and agent identities."""
    identity = qualification_identity("completed")
    trajectory = build_session_qualification_fixture(outcome="completed")
    terminal_event = next(
        event
        for event in trajectory.events
        if event.name is AgentEventName.SESSION_COMPLETED
    )
    checkpoint = trajectory.checkpoints[-1].state
    digest = sha256(identity.session_id.encode("utf-8")).hexdigest()
    reference = checkpoint["decision_receipt_ref"]
    payload = {
        "session_id": identity.session_id,
        "session_digest": digest,
        "operator_id": "human:jared",
        "objective": "Qualify one governed session.",
        "success_definition": "Return an evidence-backed terminal decision.",
        "model_profile_id": QUALIFICATION_MODEL_PROFILE_ID,
        "agent_program_ids": [QUALIFICATION_PROGRAM_ID],
        "tool_catalog_id": QUALIFICATION_TOOL_CATALOG_ID,
        "scope_envelope": {"scope_id": "uj04-qualification"},
        "budget": {
            "max_model_calls": 4,
            "max_tool_calls": 8,
            "max_tokens": 1000,
            "max_duration_seconds": 60,
            "max_mutations": 0,
            "max_revisions": 1,
            "concurrency_limit": 2,
        },
    }
    receipt = {
        "receipt_id": identity.artifact_id,
        "session_id": identity.session_id,
        "branch_id": identity.root_branch_id,
        "sequence": checkpoint["next_sequence"] - 1,
        "actor": "Research Coordinator",
        "program_id": QUALIFICATION_PROGRAM_ID,
        "model_profile_id": QUALIFICATION_MODEL_PROFILE_ID,
        "action": "conclude",
        "status": "completed",
        "summary": "The bounded investigation completed.",
        "evidence_refs": [reference],
        "budget_used": {},
        "blockers": [],
        "next_actions": [],
        "metadata": {"role": "research_coordinator"},
    }
    source = AgentSessionSource(
        session={
            "session_id": identity.session_id,
            "operator_id": "human:jared",
            "status": "completed",
            "payload": payload,
        },
        receipts=({"payload": receipt},),
        commands=(),
        public_state={
            "session_id": identity.session_id,
            "session_digest": digest,
            "operator_id": "human:jared",
            "public_state": checkpoint,
        },
    )
    projection = _build_projection(source)
    verdicts = verify_retained_trajectory(
        trajectory,
        expected_branch_ids=(
            f"{identity.root_branch_id}:data",
            f"{identity.root_branch_id}:strategy",
        ),
    )
    assert all(verdicts.values())
    assert projection.session_id == terminal_event.correlation.session_id
    assert projection.session_digest == digest
    assert projection.model_profile_id == terminal_event.correlation.model_profile_id
    assert QUALIFICATION_PROGRAM_ID in projection.agent_program_ids
    assert projection.tool_catalog_id == terminal_event.correlation.tool_catalog_id
    assert projection.terminal_decision is not None
    assert (
        projection.terminal_decision.branch_id == terminal_event.correlation.branch_id
    )
    assert (
        projection.terminal_decision.evidence_refs[0].uri
        == terminal_event.fields["decision_receipt_ref"]
    )
    assert projection.available_commands == ("inspect",)

    checkout_root = Path(__file__).resolve().parents[3]
    checkout_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=checkout_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    report = {
        "fixture_id": "uj04-public-session-completed-v1",
        "contracts": {
            "console": "AgentSessionProjection",
            "agent": "RetainedTrajectory",
        },
        "contract_version": "1",
        "checkout_commit": checkout_commit,
        "evidence_revision": 1,
        "session_id": identity.session_id,
        "root_branch_id": identity.root_branch_id,
        "terminal_artifact_uri": identity.artifact_uri,
        "verdicts": verdicts,
    }
    path = tmp_path / "uj04-console-authority-verifier.json"
    path.write_text(
        json.dumps(report, sort_keys=True, separators=(",", ":")), encoding="utf-8"
    )
    retained = json.loads(path.read_text(encoding="utf-8"))
    assert retained["fixture_id"] == "uj04-public-session-completed-v1"
    assert retained["checkout_commit"] == checkout_commit
    assert retained["evidence_revision"] == 1
    assert retained["terminal_artifact_uri"] == identity.artifact_uri
