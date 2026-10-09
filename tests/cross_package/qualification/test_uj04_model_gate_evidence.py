"""UJ-04 model-gate evidence qualification.

Subject: Revisioned evidence joining deterministic lifecycle and model-gate results.
Level: Deterministic cross-package contract qualification.
Collaborators: Existing retained trajectory fixture and admitted runtime catalogues.
Guarantees: Evidence records exact identity, command, environment, gate outcomes,
and immutable rerun revisions without claiming controlled model acceptance.
Non-goals: Running a third-party model, choosing a provider, or promoting UJ-04.
"""

from __future__ import annotations

from pathlib import Path
import sys
import subprocess

import pytest

from trader_agents import AgentEventName, verify_retained_trajectory
from tests.cross_package.qualification.support.uj04_model_gate import (
    UJ04_EVIDENCE_CONTRACT,
    UJ04_EVIDENCE_FIXTURE_ID,
    UJ04_FIXTURE_VERSION,
    UJ04_VERIFIER_VERSION,
    build_uj04_model_gate_evidence,
    read_uj04_evidence,
    write_uj04_evidence,
)
from tests.trader_agents.observability.support.session_qualification import (
    qualification_identity,
    build_session_qualification_fixture,
)


def test_uj04_records_model_gate_boundary_and_immutable_revisions(tmp_path: Path) -> None:
    """Retain deterministic evidence while making unavailable model acceptance explicit."""
    trajectory = build_session_qualification_fixture(outcome="completed")
    identity = qualification_identity("completed")
    verdicts = verify_retained_trajectory(
        trajectory,
        expected_branch_ids=(
            f"{identity.root_branch_id}:data",
            f"{identity.root_branch_id}:strategy",
        ),
    )
    terminal = next(
        event for event in trajectory.events if event.name is AgentEventName.SESSION_COMPLETED
    )
    assert terminal.correlation.session_id == identity.session_id
    assert all(verdicts.values())

    checkout_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=Path(__file__).resolve().parents[3],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    first = build_uj04_model_gate_evidence(
        checkout_commit=checkout_commit,
        evidence_revision=1,
    )
    first_path = tmp_path / "uj04-model-gate-evidence-v1.json"
    write_uj04_evidence(first_path, first)
    retained_first = read_uj04_evidence(first_path)
    assert retained_first.fixture_id == UJ04_EVIDENCE_FIXTURE_ID
    assert retained_first.fixture_version == UJ04_FIXTURE_VERSION
    assert retained_first.verifier_version == UJ04_VERIFIER_VERSION
    assert retained_first.contracts["evidence"] == UJ04_EVIDENCE_CONTRACT
    assert retained_first.deterministic_gate.status == "passed"
    assert retained_first.model_gate.status == "failed"
    assert retained_first.repeated_real_model_gate.status == "not_run"
    assert retained_first.controlled_acceptance == "not_claimed"
    assert retained_first.environment["model_profile_id"]
    assert retained_first.qualification_command.startswith("uv run pytest")

    original_bytes = first_path.read_bytes()
    second = build_uj04_model_gate_evidence(
        checkout_commit=checkout_commit,
        evidence_revision=2,
    )
    second_path = tmp_path / "uj04-model-gate-evidence-v2.json"
    write_uj04_evidence(second_path, second)
    assert read_uj04_evidence(second_path).evidence_revision == 2
    assert first_path.read_bytes() == original_bytes
    with pytest.raises(FileExistsError):
        write_uj04_evidence(first_path, second)

    subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from pathlib import Path; "
                "from tests.cross_package.qualification.support.uj04_model_gate "
                "import read_uj04_evidence; "
                f"record = read_uj04_evidence(Path({str(second_path)!r})); "
                "assert record.evidence_revision == 2; "
                "assert record.model_gate.status == 'failed'"
            ),
        ],
        cwd=Path(__file__).resolve().parents[3],
        check=True,
    )


def test_uj04_evidence_rejects_controlled_acceptance() -> None:
    """The evidence contract cannot be used to claim an unrun controlled gate."""
    evidence = build_uj04_model_gate_evidence(checkout_commit="abc123", evidence_revision=1)
    payload = evidence.to_dict()
    payload["controlled_acceptance"] = "passed"
    with pytest.raises(ValueError, match="controlled acceptance"):
        type(evidence).from_dict(payload)
