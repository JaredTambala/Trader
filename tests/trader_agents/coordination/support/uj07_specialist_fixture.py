"""Deterministic concurrent specialist fixture for UJ-07 qualification.

The fixture models the public join boundary only.  It does not run a model or
persist canonical research artifacts; those concerns belong to the production
specialist graphs and their MCP services.  Every branch retains the identities
needed to audit ownership, source and version lineage after a fresh-process
replay.
"""

from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from trader_agents import (
    BudgetUsage,
    CanonicalEvidenceRef,
    SpecialistConclusion,
    SpecialistReturn,
    SpecialistStatus,
    build_delegation,
    build_specialist_return,
)
from trader_research.governance import ResearchSession
from tests.trader_agents.support.runtime_contracts import _session, _task


SESSION_ID = "uj07-specialist-qualification"
DATA_BRANCH_ID = f"{SESSION_ID}/data"
STRATEGY_BRANCH_ID = f"{SESSION_ID}/strategy"

Outcome = Literal["complete", "partial", "failed", "blocked"]
Owner = Literal["Data Agent", "Strategy Engineering Agent"]
DATA_OWNER: Owner = "Data Agent"
STRATEGY_OWNER: Owner = "Strategy Engineering Agent"
DATA_SOURCE = "qualification-data-fixture"
STRATEGY_SOURCE = "qualification-strategy-fixture"
DATA_VERSION = "data-v1"
STRATEGY_VERSION = "strategy-v1"


class SpecialistBranchFixture(BaseModel):
    """Public, typed evidence for one isolated specialist branch."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    session_id: str = Field(min_length=1)
    branch_id: str = Field(min_length=1)
    role: Literal["data_research", "strategy_engineering"]
    owner: Owner
    source: str = Field(min_length=1)
    version: str = Field(min_length=1)
    status: SpecialistStatus
    terminal: Outcome
    result: SpecialistReturn

    @model_validator(mode="after")
    def validate_branch_contract(self) -> "SpecialistBranchFixture":
        """Keep branch metadata and the trusted specialist return aligned."""
        if self.result.session_id != self.session_id:
            raise ValueError("specialist result session identity mismatch")
        if self.result.branch_id != self.branch_id:
            raise ValueError("specialist result branch identity mismatch")
        if self.result.role != self.role:
            raise ValueError("specialist result role mismatch")
        expected_owner = (
            DATA_OWNER if self.role == "data_research" else STRATEGY_OWNER
        )
        if self.owner != expected_owner:
            raise ValueError("specialist owner does not match role")
        if self.result.status is not self.status:
            raise ValueError("specialist result status mismatch")
        expected_terminal = _terminal_for_status(self.status)
        if self.terminal != expected_terminal:
            raise ValueError("specialist terminal outcome contradicts status")
        return self


class SpecialistQualificationFixture(BaseModel):
    """Replayable two-branch public qualification result."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    session_id: str = Field(min_length=1)
    outcome: Outcome
    branches: tuple[SpecialistBranchFixture, SpecialistBranchFixture]

    @model_validator(mode="after")
    def validate_join_contract(self) -> "SpecialistQualificationFixture":
        """Require exactly one Data and one Strategy branch with a hard join."""
        expected = {DATA_BRANCH_ID, STRATEGY_BRANCH_ID}
        branch_ids = {branch.branch_id for branch in self.branches}
        if branch_ids != expected:
            raise ValueError("qualification fixture must contain both specialist branches")
        if len({branch.role for branch in self.branches}) != 2:
            raise ValueError("qualification fixture must contain distinct specialist roles")
        if any(branch.session_id != self.session_id for branch in self.branches):
            raise ValueError("all specialist branches must belong to the session")
        statuses = {branch.status for branch in self.branches}
        expected_outcome = _fixture_outcome(tuple(statuses))
        if self.outcome != expected_outcome:
            raise ValueError("qualification outcome contradicts specialist statuses")
        return self


def build_uj07_fixture(
    *,
    data_status: SpecialistStatus = SpecialistStatus.READY,
    strategy_status: SpecialistStatus = SpecialistStatus.READY,
) -> SpecialistQualificationFixture:
    """Build one deterministic concurrent Data/Strategy qualification result.

    Args:
        data_status: Terminal status for the Data branch.
        strategy_status: Terminal status for the Strategy branch.

    Returns:
        A strict two-branch fixture suitable for persistence and replay tests.

    Raises:
        ValueError: If a status outside the four qualification outcomes is used.
    """
    allowed = {
        SpecialistStatus.READY,
        SpecialistStatus.PARTIAL,
        SpecialistStatus.FAILED,
        SpecialistStatus.BLOCKED,
    }
    if data_status not in allowed or strategy_status not in allowed:
        raise ValueError("UJ-07 fixture supports ready, partial, failed, or blocked")
    session = _session(session_id=SESSION_ID)
    data = _build_branch(
        session=session,
        branch_id=DATA_BRANCH_ID,
        role="data_research",
        owner=DATA_OWNER,
        source=DATA_SOURCE,
        version=DATA_VERSION,
        status=data_status,
    )
    strategy = _build_branch(
        session=session,
        branch_id=STRATEGY_BRANCH_ID,
        role="strategy_engineering",
        owner=STRATEGY_OWNER,
        source=STRATEGY_SOURCE,
        version=STRATEGY_VERSION,
        status=strategy_status,
    )
    outcome = _fixture_outcome((data.status, strategy.status))
    return SpecialistQualificationFixture(
        session_id=SESSION_ID,
        outcome=outcome,
        branches=(data, strategy),
    )


def fixture_digest(fixture: SpecialistQualificationFixture) -> str:
    """Return a stable digest for exact fresh-process replay comparison."""
    payload = json.dumps(
        fixture.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _build_branch(
    *,
    session: ResearchSession,
    branch_id: str,
    role: Literal["data_research", "strategy_engineering"],
    owner: Owner,
    source: str,
    version: str,
    status: SpecialistStatus,
) -> SpecialistBranchFixture:
    """Build a branch through the same trusted delegation boundary as runtime."""
    task = _task(
        "data" if role == "data_research" else "strategy",
        role,
        mutation_requested=False,
    )
    delegation = build_delegation(
        session_id=session.session_id,
        branch_id=branch_id,
        task=task,
        required_input_refs=[],
        permitted_side_effects=["read_only"],
        reserved_model_calls=2,
        reserved_tool_calls=4,
        reserved_tokens=1_000,
        attempt=1,
    )
    artifact_type = "dataset_manifest" if role == "data_research" else "implementation_version"
    artifact_id = f"{source}-{version}"
    evidence = CanonicalEvidenceRef(
        artifact_type=artifact_type,
        artifact_id=artifact_id,
        domain_owner=owner,
        uri=f"research://postgres/{artifact_type}/{artifact_id}",
        source_hash=hashlib.sha256(source.encode("utf-8")).hexdigest(),
    )
    blockers = []
    if status in {SpecialistStatus.FAILED, SpecialistStatus.BLOCKED}:
        blockers = [
            {
                "code": f"{role}_fixture_{status.value}",
                "message": f"{owner} fixture ended {status.value}.",
            }
        ]
    conclusion = SpecialistConclusion(
        status=status,
        answered_questions=[f"{owner} branch identity is preserved."],
        unresolved_questions=[] if status is SpecialistStatus.READY else ["Further evidence is required."],
        findings=[f"{source} {version} is attributed to {owner}."],
        evidence_refs=[] if status in {SpecialistStatus.FAILED, SpecialistStatus.BLOCKED} else [evidence],
        blockers=blockers,
    )
    result = build_specialist_return(
        delegation=delegation,
        role=role,
        program_id=("data-research-v6" if role == "data_research" else "strategy-engineering-v6"),
        model_profile_id=session.model_profile_id,
        tool_catalog_id=session.tool_catalog_id,
        conclusion=conclusion,
        budget_used=BudgetUsage(model_calls=1, tool_calls=1, input_tokens=20, output_tokens=20),
        available_evidence_refs=[evidence],
    )
    return SpecialistBranchFixture(
        session_id=delegation.session_id,
        branch_id=branch_id,
        role=role,
        owner=owner,
        source=source,
        version=version,
        status=status,
        terminal=_terminal_for_status(status),
        result=result,
    )


def _terminal_for_status(status: SpecialistStatus) -> Outcome:
    """Map a specialist status to the qualification vocabulary."""
    if status is SpecialistStatus.READY:
        return "complete"
    if status is SpecialistStatus.PARTIAL:
        return "partial"
    if status is SpecialistStatus.FAILED:
        return "failed"
    if status is SpecialistStatus.BLOCKED:
        return "blocked"
    raise ValueError(f"unsupported UJ-07 specialist status: {status.value}")


def _fixture_outcome(statuses: tuple[SpecialistStatus, ...]) -> Outcome:
    """Return the fail-closed hard-join outcome for branch statuses."""
    if SpecialistStatus.BLOCKED in statuses:
        return "blocked"
    if SpecialistStatus.FAILED in statuses:
        return "failed"
    if SpecialistStatus.PARTIAL in statuses:
        return "partial"
    return "complete"
