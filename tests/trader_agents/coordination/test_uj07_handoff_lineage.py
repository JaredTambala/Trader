"""Specialist handoff lineage and digest admission for UJ-07.

Subject: Coordinator join and public checkpoint validation of two specialist branches.
Level: In-process contract and fresh-process recovery.
Collaborators: Real delegation, return, evidence, and checkpoint contracts; no model or MCP transport.
Guarantees: Run, role, branch, scope, exact revision, and return digest drift fail closed while duplicate delivery is idempotent.
Non-goals: Scientific quality, provider behavior, or live artifact-store availability.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from trader_agents import (
    CanonicalEvidenceRef,
    CoordinatorAgenda,
    CoordinatorDecision,
    ToolObservation,
    build_agent_checkpoint_state,
    validate_agent_checkpoint_state,
)
from trader_agents.coordination.coordinator import (
    _accept_specialist_returns,
    _merge_refs,
    _validate_coordinator_decision,
    _verified_canonical_read,
)
from trader_research.foundation import json_payload_hash
from tests.trader_agents.coordination.support.uj07_specialist_fixture import (
    SpecialistQualificationFixture,
    build_uj07_fixture,
)


def _joined_state(fixture: SpecialistQualificationFixture) -> dict[str, object]:
    """Construct the same public state shape retained after a hard join."""
    state: dict[str, object] = dict(
        build_agent_checkpoint_state(
            session_id=fixture.session_id,
            session_digest="a" * 64,
            branch_id="root",
            coordinator_program_id="research-coordinator-v6",
            model_profile_id="qualification-profile",
            tool_catalog_id="qualification-catalogue",
        )
    )
    state["branch_by_task"] = {
        branch.delegation.task.task_id: branch.branch_id
        for branch in fixture.branches
    }
    state["agenda"] = CoordinatorAgenda(
        objective_summary="Review both specialist branches.",
        tasks=[branch.delegation.task for branch in fixture.branches],
    ).model_dump(mode="json")
    state["delegations"] = [
        branch.delegation.model_dump(mode="json") for branch in fixture.branches
    ]
    state["specialist_returns"] = [
        branch.result.model_dump(mode="json") for branch in fixture.branches
    ]
    state["accepted_return_digests"] = {
        branch.result.delegation_id: json_payload_hash(
            branch.result.model_dump(mode="json")
        )
        for branch in fixture.branches
    }
    return state


def test_join_rejects_wrong_run_branch_role_and_scope() -> None:
    """An otherwise valid return cannot cross a delegation's ownership boundary."""
    fixture = build_uj07_fixture()
    data, strategy = fixture.branches
    state = _joined_state(fixture)
    state["accepted_return_digests"] = {}

    accepted, digests = _accept_specialist_returns(
        state,
        delegations=[data.delegation, strategy.delegation],
        results=[data.result, strategy.result],
    )
    assert len(accepted) == len(digests) == 2
    assert accepted[0].evidence_refs == data.result.evidence_refs
    assert accepted[0].evidence_refs[0].source_hash is not None

    for changed, message in (
        (data.result.model_copy(update={"session_id": "other-run"}), "session identity"),
        (data.result.model_copy(update={"branch_id": strategy.branch_id}), "branch identity"),
        (data.result.model_copy(update={"role": strategy.role}), "role does not match"),
    ):
        with pytest.raises(ValueError, match=message):
            _accept_specialist_returns(
                state,
                delegations=[data.delegation],
                results=[changed],
            )
    wrong_scope = {**state, "branch_by_task": {"data": strategy.branch_id}}
    with pytest.raises(ValueError, match="branch does not match task scope"):
        _accept_specialist_returns(
            wrong_scope,
            delegations=[data.delegation],
            results=[data.result],
        )
    changed_task = data.delegation.task.model_copy(
        update={"scope_item_ids": ["unapproved-scope"]}
    )
    with pytest.raises(ValueError, match="scope does not match agenda"):
        _accept_specialist_returns(
            state,
            delegations=[data.delegation.model_copy(update={"task": changed_task})],
            results=[data.result],
        )
    wrong_run = {**state, "session_id": "other-run"}
    with pytest.raises(ValueError, match="belongs to another run"):
        _accept_specialist_returns(
            wrong_run,
            delegations=[data.delegation],
            results=[data.result],
        )


def test_duplicate_delivery_is_idempotent_but_changed_revision_conflicts() -> None:
    """The same delegation is accepted once; a changed artifact revision is rejected."""
    fixture = build_uj07_fixture()
    data = fixture.branches[0]
    state = _joined_state(fixture)
    accepted, digests = _accept_specialist_returns(
        state,
        delegations=[data.delegation],
        results=[data.result],
    )
    assert accepted == []
    assert digests == state["accepted_return_digests"]

    changed_ref = data.result.evidence_refs[0].model_copy(update={"source_hash": "f" * 64})
    changed = data.result.model_copy(update={"evidence_refs": [changed_ref]})
    with pytest.raises(ValueError, match="conflicting content"):
        _accept_specialist_returns(
            state,
            delegations=[data.delegation],
            results=[changed],
        )
    with pytest.raises(ValueError, match="conflicting revision identity"):
        _merge_refs(data.result.evidence_refs, changed.evidence_refs)


def test_coordinator_decision_cannot_cite_a_different_artifact_revision() -> None:
    """A matching URI with a changed source digest is not verified evidence."""
    fixture = build_uj07_fixture()
    returns = [branch.result for branch in fixture.branches]
    reference = returns[0].evidence_refs[0]
    agenda = CoordinatorAgenda(
        objective_summary="Review both independent specialists.",
        tasks=[branch.delegation.task for branch in fixture.branches],
    )
    decision = CoordinatorDecision(
        action="conclude",
        summary="Both branches are ready.",
        reviewed_delegation_ids=[item.delegation_id for item in returns],
        cited_evidence_refs=[reference],
        criteria_applied=["exact canonical revision"],
    )
    arguments = {
        "agenda": agenda,
        "new_returns": returns,
        "all_returns": returns,
        "completed_task_ids": [task.task_id for task in agenda.tasks],
    }
    _validate_coordinator_decision(
        decision,
        verified_refs=[reference.model_dump(mode="json")],
        **arguments,
    )
    changed = reference.model_copy(update={"source_hash": "f" * 64})
    with pytest.raises(ValueError, match="not independently verified"):
        _validate_coordinator_decision(
            decision,
            verified_refs=[changed.model_dump(mode="json")],
            **arguments,
        )


def test_canonical_reread_rejects_owner_identity_and_digest_drift() -> None:
    """The trusted read must match the full specialist reference and record metadata."""
    reference = build_uj07_fixture().branches[0].result.evidence_refs[0]
    record = {
        "artifact_type": reference.artifact_type,
        "artifact_id": reference.artifact_id,
        "domain_owner": reference.domain_owner,
        "source_hash": reference.source_hash,
        "payload_hash": "b" * 64,
        "status": "passed",
        "producer_tool": "data_create_research_snapshot",
    }

    def observation(
        *,
        metadata: dict[str, str | None],
        refs: list[CanonicalEvidenceRef] | None = None,
    ) -> ToolObservation:
        return ToolObservation(
            call_id="canonical-read",
            tool_name="research_read_artifact",
            command="research_read_artifact",
            agent_owner="Research Coordinator",
            side_effect="read_only",
            ok=True,
            summary={"record": metadata},
            evidence_refs=[reference] if refs is None else refs,
        )

    verified = _verified_canonical_read(reference, observation(metadata=record))
    assert verified["reference"] == reference.model_dump(mode="json")
    assert verified["source_hash"] == reference.source_hash
    for changed, message in (
        ({**record, "artifact_id": "other-revision"}, "identity"),
        ({**record, "domain_owner": "other-owner"}, "owner"),
        ({**record, "source_hash": "f" * 64}, "digest"),
    ):
        with pytest.raises(RuntimeError, match=message):
            _verified_canonical_read(reference, observation(metadata=changed))
    changed_ref = reference.model_copy(update={"source_hash": "f" * 64})
    with pytest.raises(RuntimeError, match="revision"):
        _verified_canonical_read(
            reference,
            observation(metadata=record, refs=[changed_ref]),
        )


def test_fresh_process_reconstructs_and_checks_retained_lineage(tmp_path: Path) -> None:
    """A replacement process verifies branch ownership and return digests from public state."""
    fixture = build_uj07_fixture()
    state = _joined_state(fixture)
    validate_agent_checkpoint_state(state)
    script = """
import json
import sys
from trader_agents import validate_agent_checkpoint_state
from trader_research.foundation import json_payload_hash

state = json.loads(sys.stdin.read())
validate_agent_checkpoint_state(state)
print(json.dumps({"run_id": state["session_id"], "branches": sorted(state["branch_by_task"].values()), "digest": json_payload_hash(state)}, sort_keys=True))
"""
    repository_root = Path(__file__).resolve().parents[3]
    python_path = os.pathsep.join((str(repository_root), str(repository_root / "src")))
    result = subprocess.run(
        [sys.executable, "-c", script],
        input=json.dumps(state),
        capture_output=True,
        text=True,
        check=True,
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": python_path},
    )
    replay = json.loads(result.stdout)
    assert replay == {
        "run_id": fixture.session_id,
        "branches": sorted(branch.branch_id for branch in fixture.branches),
        "digest": json_payload_hash(state),
    }

    changed = json.loads(json.dumps(state))
    changed["specialist_returns"][0]["evidence_refs"][0]["source_hash"] = "f" * 64
    with pytest.raises(ValueError, match="return digest mismatch"):
        validate_agent_checkpoint_state(changed)
    changed = json.loads(json.dumps(state))
    changed["branch_by_task"]["data"] = fixture.branches[1].branch_id
    with pytest.raises(ValueError, match="branch does not match task scope"):
        validate_agent_checkpoint_state(changed)
    changed = json.loads(json.dumps(state))
    changed["delegations"][0]["task"]["scope_item_ids"] = ["unapproved-scope"]
    with pytest.raises(ValueError, match="scope does not match agenda"):
        validate_agent_checkpoint_state(changed)
