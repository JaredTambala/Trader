"""Qualification tests for retained public agent trajectory evidence.

Subject: Retained public event and checkpoint trajectory verification owned by
``trader_agents.observability``.
Level: Deterministic qualification fixture with a fresh local Python process.
Collaborators: Real public event/checkpoint validators and a deterministic
retention sink; no model, MCP, Postgres, or canonical artifact store.
Guarantees: Identity pins, concurrent branch attribution, redaction, fresh
process recovery, terminal decision lineage, duplicate rejection, and sink
outage behavior are explicit.
Non-goals: Third-party model quality, durable database retention, Console
rendering, or canonical research evidence validity.
"""

from __future__ import annotations

from dataclasses import replace
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from trader_agents import (
    AgentEventName,
    RetainedTrajectorySink,
    RetainedTrajectoryUnavailable,
    verify_retained_trajectory,
)
from tests.trader_agents.observability.support.retained_trajectory import (
    DATA_BRANCH_ID,
    STRATEGY_BRANCH_ID,
    build_retained_trajectory_fixture,
)


def test_retained_fixture_proves_branch_identity_recovery_and_terminal_lineage() -> None:
    """A queryable fixture preserves identities across branches and restart."""
    trajectory = build_retained_trajectory_fixture()

    verdicts = verify_retained_trajectory(
        trajectory,
        expected_branch_ids=(DATA_BRANCH_ID, STRATEGY_BRANCH_ID),
    )

    assert verdicts == {
        "identity_consistent": True,
        "concurrent_branch_attribution": True,
        "redacted_public_projection": True,
        "fresh_process_recovery": True,
        "terminal_decision_lineage": True,
        "checkpoint_projection_complete": True,
    }
    assert {
        event.correlation.process_instance_id for event in trajectory.events
    } == {"process-start", "process-resume"}
    assert any(
        event.name is AgentEventName.CHECKPOINT_RECOVERED
        for event in trajectory.events
    )


def test_retained_fixture_survives_a_fresh_python_process(tmp_path: Path) -> None:
    """A second process reloads the retained public evidence from disk."""
    storage_path = tmp_path / "trajectory.json"
    expected = build_retained_trajectory_fixture(storage_path=storage_path)
    script = """
import json
import sys

from trader_agents import RetainedTrajectorySink, verify_retained_trajectory

trajectory = RetainedTrajectorySink(storage_path=sys.argv[1]).snapshot()
print(json.dumps({
    "events": len(trajectory.events),
    "checkpoints": len(trajectory.checkpoints),
    "verdicts": verify_retained_trajectory(
        trajectory,
        expected_branch_ids=("branch-data", "branch-strategy"),
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
    assert payload["verdicts"]["fresh_process_recovery"] is True


def test_retained_sink_rejects_duplicate_event_positions() -> None:
    """A replayed process sequence cannot silently duplicate public evidence."""
    trajectory = build_retained_trajectory_fixture()
    sink = RetainedTrajectorySink()
    event = trajectory.events[0]
    sink.emit(event)

    with pytest.raises(ValueError, match="already contains event stream position"):
        sink.emit(event)


def test_retained_sink_fails_closed_during_outage_without_partial_record() -> None:
    """A sink outage returns an explicit error and retains no event."""
    trajectory = build_retained_trajectory_fixture()
    sink = RetainedTrajectorySink(available=False)

    with pytest.raises(RetainedTrajectoryUnavailable):
        sink.emit(trajectory.events[0])

    assert sink.snapshot().events == ()
    assert sink.snapshot().checkpoints == ()


def test_retained_fixture_rejects_missing_branch_before_verification() -> None:
    """A qualification run cannot claim concurrent work without both branches."""
    trajectory = build_retained_trajectory_fixture()
    events = tuple(
        event
        for event in trajectory.events
        if event.correlation.branch_id != STRATEGY_BRANCH_ID
    )
    reduced = replace(trajectory, events=events)

    with pytest.raises(ValueError, match="missing expected branches"):
        verify_retained_trajectory(
            reduced,
            expected_branch_ids=(DATA_BRANCH_ID, STRATEGY_BRANCH_ID),
        )


def test_retained_fixture_marks_identity_drift_as_unqualified() -> None:
    """A changed program identity remains visible and fails the verdict."""
    trajectory = build_retained_trajectory_fixture()
    drifted_event = trajectory.events[0].model_copy(
        update={
            "correlation": trajectory.events[0].correlation.model_copy(
                update={"program_id": "other-program-v1"}
            )
        }
    )
    drifted = replace(
        trajectory,
        events=(drifted_event, *trajectory.events[1:]),
    )

    verdicts = verify_retained_trajectory(drifted)

    assert verdicts["identity_consistent"] is False
    assert verdicts["redacted_public_projection"] is True
