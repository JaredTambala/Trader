"""UJ-04 deterministic session qualification fixture tests.

Subject: The public lifecycle fixture used to qualify governed agent sessions.
Level: Deterministic local qualification and fresh-process retention.
Collaborators: Real public event/checkpoint validators and local JSON retention;
no model provider, MCP transport, Postgres, or hidden runtime state.
Guarantees: Stable session/branch/run/artifact identities, concurrent branch
attribution, complete/failed/cancelled terminal outcomes, redaction, and an
explicit missing-checkpoint verdict.
Non-goals: Model quality, Console rendering, canonical artifact persistence,
or third-party execution acceptance.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
from typing import cast

import pytest

from trader_agents import AgentEventName, verify_retained_trajectory
from tests.trader_agents.observability.support.session_qualification import (
    QUALIFICATION_OUTCOMES,
    SessionOutcome,
    build_session_qualification_fixture,
    qualification_identity,
)


@pytest.mark.parametrize("outcome", QUALIFICATION_OUTCOMES)
def test_terminal_cases_preserve_public_lineage_and_stable_identities(
    outcome: str,
) -> None:
    """Each terminal outcome is independently attributable and verifiable."""
    typed_outcome = cast(SessionOutcome, outcome)
    trajectory = build_session_qualification_fixture(outcome=typed_outcome)
    identity = qualification_identity(typed_outcome)

    verdicts = verify_retained_trajectory(
        trajectory,
        expected_branch_ids=(
            f"{identity.root_branch_id}:data",
            f"{identity.root_branch_id}:strategy",
        ),
    )

    assert all(verdicts.values())
    assert {event.correlation.session_id for event in trajectory.events} == {
        identity.session_id
    }
    assert {
        event.fields["run_id"] for event in trajectory.events
    } == {identity.run_id}
    assert {
        event.fields["artifact_id"] for event in trajectory.events
    } == {identity.artifact_id}
    assert sum(
        event.name is getattr(AgentEventName, f"SESSION_{outcome.upper()}")
        for event in trajectory.events
    ) == 1


def test_missing_checkpoint_is_reported_without_fabricating_recovery() -> None:
    """A terminal event cannot claim recovery or lineage without a checkpoint."""
    trajectory = build_session_qualification_fixture(
        outcome="completed",
        include_checkpoint=False,
    )

    verdicts = verify_retained_trajectory(
        trajectory,
        expected_branch_ids=("branch-completed-uj04:data", "branch-completed-uj04:strategy"),
    )

    assert verdicts["identity_consistent"] is True
    assert verdicts["concurrent_branch_attribution"] is True
    assert verdicts["redacted_public_projection"] is True
    assert verdicts["fresh_process_recovery"] is False
    assert verdicts["terminal_decision_lineage"] is False
    assert verdicts["checkpoint_projection_complete"] is False
    assert not trajectory.checkpoints
    assert any(
        event.name is AgentEventName.SESSION_COMPLETED
        for event in trajectory.events
    )


def test_stable_trajectory_replays_from_a_fresh_process(tmp_path: Path) -> None:
    """A new Python process reloads the same redacted public fixture."""
    storage_path = tmp_path / "uj04-trajectory.json"
    expected = build_session_qualification_fixture(
        outcome="failed",
        storage_path=storage_path,
    )
    script = """
import json
import sys
from trader_agents import RetainedTrajectorySink, verify_retained_trajectory
from tests.trader_agents.observability.support.session_qualification import qualification_identity
identity = qualification_identity("failed")
trajectory = RetainedTrajectorySink(storage_path=sys.argv[1]).snapshot()
print(json.dumps({
    "events": len(trajectory.events),
    "checkpoints": len(trajectory.checkpoints),
    "session_ids": sorted({event.correlation.session_id for event in trajectory.events}),
    "verdicts": verify_retained_trajectory(
        trajectory,
        expected_branch_ids=(identity.root_branch_id + ":data", identity.root_branch_id + ":strategy"),
    ),
}, sort_keys=True))
"""
    source_root = Path(__file__).resolve().parents[3] / "src"
    python_path = str(source_root)
    existing_python_path = os.environ.get("PYTHONPATH")
    if existing_python_path:
        python_path += os.pathsep + existing_python_path
    result = subprocess.run(
        [sys.executable, "-c", script, str(storage_path)],
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": python_path},
    )

    payload = json.loads(result.stdout)
    assert payload["events"] == len(expected.events)
    assert payload["checkpoints"] == len(expected.checkpoints)
    assert payload["session_ids"] == ["session-failed-uj04"]
    assert all(payload["verdicts"].values())
