"""Contracts for frozen concrete first-slice qualification sessions."""

from __future__ import annotations

from datetime import datetime

import pytest

from tests.support.agentic_qualification import (
    agentic_evaluation_component_digests,
    agentic_evaluation_digest,
    load_agentic_evaluation_contract,
    load_agentic_session_input_contract,
)
from tests.support.agentic_scenarios import (
    build_agentic_scenario_sessions,
    load_agentic_scenario_inputs,
)
from trader_agents.inputs import (
    SessionInputError,
    strategy_build_contract_from_session,
)
from trader_research.foundation import stable_research_id


_FREEZE = "a" * 40


def test_concrete_inputs_cover_every_charter_scenario() -> None:
    """Require exact one-to-one coverage and an independently digested fixture."""
    charter = load_agentic_evaluation_contract()
    input_contract = load_agentic_session_input_contract()
    inputs = load_agentic_scenario_inputs()

    expected = {str(item["scenario_id"]) for item in charter["scenarios"]}
    assert set(inputs) == expected
    assert set(input_contract["scenarios"]) == expected
    assert input_contract["fixture_id"] == charter["input_fixture_id"]
    components = agentic_evaluation_component_digests()
    assert set(components) == {"charter_sha256", "session_inputs_sha256"}
    assert all(len(value) == 64 for value in components.values())
    assert len(agentic_evaluation_digest()) == 64


def test_every_scenario_builds_strict_pinned_sessions() -> None:
    """Build all thirteen concrete variants with exact runtime identities."""
    inputs = load_agentic_scenario_inputs()
    sessions = {
        scenario_id: build_agentic_scenario_sessions(
            scenario_id,
            repetition=1,
            freeze_revision=_FREEZE,
        )
        for scenario_id in inputs
    }

    assert sum(len(value) for value in sessions.values()) == 13
    assert len(sessions["distinct_briefs"]) == 2
    assert all(
        session.metadata["freeze_revision"] == _FREEZE
        for variants in sessions.values()
        for session in variants
    )
    assert all(
        session.implementation_specification is not None
        and session.implementation_specification["repository_revision"] == _FREEZE
        for variants in sessions.values()
        for session in variants
    )
    first, second = sessions["distinct_briefs"]
    assert first.approval_policy == second.approval_policy
    assert first.objective != second.objective
    assert first.scope_envelope != second.scope_envelope


def test_material_ambiguity_removes_the_field_without_mutating_template() -> None:
    """Use merge-patch deletion to preserve a genuinely incomplete brief."""
    session = build_agentic_scenario_sessions(
        "material_ambiguity",
        repetition=1,
        freeze_revision=_FREEZE,
    )[0]
    assert session.implementation_specification is not None
    assert "failure_behavior" not in session.implementation_specification
    template = load_agentic_session_input_contract()["session_template"]
    assert template["implementation_specification"]["failure_behavior"]

    branch_id = stable_research_id(
        "agent_branch",
        {"session_id": session.session_id, "task_id": "strategy"},
    )
    with pytest.raises(SessionInputError, match="failure_behavior"):
        strategy_build_contract_from_session(session, branch_id=branch_id)


def test_session_identity_changes_by_repetition_and_freeze() -> None:
    """Prevent results from different repetitions or freezes sharing state."""
    first = build_agentic_scenario_sessions(
        "exact_reuse",
        repetition=1,
        freeze_revision=_FREEZE,
    )[0]
    repeated = build_agentic_scenario_sessions(
        "exact_reuse",
        repetition=2,
        freeze_revision=_FREEZE,
    )[0]
    refrozen = build_agentic_scenario_sessions(
        "exact_reuse",
        repetition=1,
        freeze_revision="b" * 40,
    )[0]

    assert len({first.session_id, repeated.session_id, refrozen.session_id}) == 3
    assert (
        len({first.session_digest, repeated.session_digest, refrozen.session_digest})
        == 3
    )


def test_phase_execution_namespaces_isolate_session_and_mutable_fixture() -> None:
    """Keep development phases disjoint from all 36 campaign sessions."""
    campaign = build_agentic_scenario_sessions(
        "exact_reuse",
        repetition=1,
        freeze_revision=_FREEZE,
    )[0]
    e2e = build_agentic_scenario_sessions(
        "exact_reuse",
        repetition=1,
        freeze_revision=_FREEZE,
        execution_namespace="postgres_e2e",
    )[0]

    assert campaign.session_id != e2e.session_id
    assert campaign.scope_envelope != e2e.scope_envelope
    assert campaign.implementation_specification != e2e.implementation_specification
    assert e2e.metadata["qualification_execution_namespace"] == "postgres_e2e"
    with pytest.raises(ValueError, match="execution_namespace"):
        build_agentic_scenario_sessions(
            "exact_reuse",
            repetition=1,
            freeze_revision=_FREEZE,
            execution_namespace="unreviewed_phase",
        )


def test_campaign_sessions_have_disjoint_mutable_fixture_partitions() -> None:
    """Prevent prior repetitions contaminating Data or catalogue starting state."""
    inputs = load_agentic_scenario_inputs()
    assert sorted(item.isolation_ordinal for item in inputs.values()) == list(
        range(len(inputs))
    )
    sessions = [
        session
        for repetition in range(1, 4)
        for scenario_id in inputs
        for session in build_agentic_scenario_sessions(
            scenario_id,
            repetition=repetition,
            freeze_revision=_FREEZE,
        )
    ]
    implementation_names = {
        str(session.implementation_specification["name"])
        for session in sessions
        if session.implementation_specification is not None
    }
    assert len(implementation_names) == len(sessions)

    windows_by_stream: dict[tuple[str, str], list[tuple[datetime, datetime]]] = {}
    for session in sessions:
        data_scope = session.scope_envelope["data_scope"]
        for item in data_scope["items"]:
            start = datetime.fromisoformat(str(item["start"]).replace("Z", "+00:00"))
            end = datetime.fromisoformat(str(item["end"]).replace("Z", "+00:00"))
            for symbol in item["symbols"]:
                windows_by_stream.setdefault(
                    (str(symbol), str(item["timeframe"])),
                    [],
                ).append((start, end))
    for windows in windows_by_stream.values():
        ordered = sorted(windows)
        assert all(
            previous_end < next_start
            for (_, previous_end), (next_start, _) in zip(
                ordered,
                ordered[1:],
                strict=False,
            )
        )


@pytest.mark.parametrize(
    ("scenario_id", "repetition", "freeze_revision", "message"),
    [
        ("unknown", 1, _FREEZE, "unknown agentic scenario"),
        ("exact_reuse", 0, _FREEZE, "repetition must be between"),
        ("exact_reuse", 4, _FREEZE, "repetition must be between"),
        ("exact_reuse", 1, "short", "full lowercase Git revision"),
    ],
)
def test_session_builder_fails_closed_for_invalid_campaign_identity(
    scenario_id: str,
    repetition: int,
    freeze_revision: str,
    message: str,
) -> None:
    """Reject inputs that could alias or escape the frozen campaign."""
    with pytest.raises(ValueError, match=message):
        build_agentic_scenario_sessions(
            scenario_id,
            repetition=repetition,
            freeze_revision=freeze_revision,
        )
