"""Concurrent specialist qualification fixture contracts for UJ-07.

Subject: The deterministic public join evidence for one Data and one Strategy
specialist branch.
Level: In-process contract plus fresh-process replay.
Collaborators: Real ``trader_agents`` delegation and evidence contracts; no
model, MCP transport, Postgres, or canonical research store.
Guarantees: Branch identity, owner/source/version lineage, terminal outcomes,
and exact replay remain inspectable for complete, partial, failed, and blocked
specialist results.
Non-goals: Specialist reasoning quality, provider behavior, or Console
rendering.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from trader_agents import SpecialistStatus
from tests.trader_agents.coordination.support.uj07_specialist_fixture import (
    DATA_BRANCH_ID,
    DATA_OWNER,
    DATA_SOURCE,
    DATA_VERSION,
    STRATEGY_BRANCH_ID,
    STRATEGY_OWNER,
    STRATEGY_SOURCE,
    STRATEGY_VERSION,
    build_uj07_fixture,
    fixture_digest,
)


def test_fixture_preserves_two_explicit_branch_identities_and_lineage() -> None:
    """The joined result keeps ownership and source/version fields per branch."""
    fixture = build_uj07_fixture()

    assert fixture.outcome == "complete"
    assert {branch.branch_id for branch in fixture.branches} == {
        DATA_BRANCH_ID,
        STRATEGY_BRANCH_ID,
    }
    by_branch = {branch.branch_id: branch for branch in fixture.branches}
    assert (
        by_branch[DATA_BRANCH_ID].owner,
        by_branch[DATA_BRANCH_ID].source,
        by_branch[DATA_BRANCH_ID].version,
    ) == (DATA_OWNER, DATA_SOURCE, DATA_VERSION)
    assert (
        by_branch[STRATEGY_BRANCH_ID].owner,
        by_branch[STRATEGY_BRANCH_ID].source,
        by_branch[STRATEGY_BRANCH_ID].version,
    ) == (STRATEGY_OWNER, STRATEGY_SOURCE, STRATEGY_VERSION)
    assert all(branch.result.branch_id == branch.branch_id for branch in fixture.branches)
    assert all(branch.terminal == "complete" for branch in fixture.branches)


@pytest.mark.parametrize(
    ("data_status", "strategy_status", "outcome"),
    [
        (SpecialistStatus.READY, SpecialistStatus.READY, "complete"),
        (SpecialistStatus.PARTIAL, SpecialistStatus.READY, "partial"),
        (SpecialistStatus.FAILED, SpecialistStatus.READY, "failed"),
        (SpecialistStatus.BLOCKED, SpecialistStatus.READY, "blocked"),
    ],
)
def test_fixture_retains_each_terminal_outcome(
    data_status: SpecialistStatus,
    strategy_status: SpecialistStatus,
    outcome: str,
) -> None:
    """Partial and negative branch results remain explicit at the hard join."""
    fixture = build_uj07_fixture(
        data_status=data_status,
        strategy_status=strategy_status,
    )

    assert fixture.outcome == outcome
    data_branch = next(branch for branch in fixture.branches if branch.role == "data_research")
    assert data_branch.status is data_status
    assert data_branch.terminal == outcome if data_status is not SpecialistStatus.READY else data_branch.terminal == "complete"


def test_fixture_replays_identically_in_a_fresh_python_process(tmp_path: Path) -> None:
    """A new process can validate the same typed branches without hidden state."""
    fixture = build_uj07_fixture(
        data_status=SpecialistStatus.PARTIAL,
        strategy_status=SpecialistStatus.READY,
    )
    payload = fixture.model_dump_json()
    script = """
import json
import sys

from tests.trader_agents.coordination.support.uj07_specialist_fixture import (
    SpecialistQualificationFixture,
    fixture_digest,
)

fixture = SpecialistQualificationFixture.model_validate_json(sys.stdin.read())
print(json.dumps({"digest": fixture_digest(fixture), "outcome": fixture.outcome}, sort_keys=True))
"""
    source_root = Path(__file__).resolve().parents[3] / "src"
    repository_root = Path(__file__).resolve().parents[3]
    python_path = os.pathsep.join((str(repository_root), str(source_root)))
    result = subprocess.run(
        [sys.executable, "-c", script],
        input=payload,
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, "PYTHONPATH": python_path},
        cwd=tmp_path,
    )

    replay = json.loads(result.stdout)
    assert replay == {"digest": fixture_digest(fixture), "outcome": "partial"}
