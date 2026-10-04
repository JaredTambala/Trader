"""Contract tests for immutable hypothesis and experiment briefs.

Subject: HypothesisBrief normalization, revision persistence, and downstream handoff.
Level: In-process governance domain and application service.
Collaborators: Real typed brief values and the in-memory canonical artifact store.
Guarantees: Required falsifiers and scope are validated; authorized revisions are
append-only and idempotent; downstream handoffs preserve identity and decisions.
Non-goals: Console transport, MCP registration, strategy admission, or experiment execution.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from trader_research.foundation import InMemoryResearchArtifactStore
from trader_research.governance import (
    HYPOTHESIS_AGENT_OWNER,
    HYPOTHESIS_CARD,
    HypothesisBrief,
    HypothesisBriefHandoff,
    HypothesisScope,
    persist_hypothesis_brief,
    resolve_hypothesis_brief_handoff,
)


def test_brief_round_trip_and_downstream_handoff_preserve_decision_rules() -> None:
    """A persisted brief exposes one canonical ref and retains outcome decisions for each consumer."""
    store = InMemoryResearchArtifactStore()
    brief = _brief()

    result = persist_hypothesis_brief(brief=brief, artifact_store=store)

    assert result.ok is True
    assert result.data["idempotent_replay"] is False
    restored = HypothesisBrief.from_dict(result.data["hypothesis_brief"])
    assert restored == brief
    handoff = HypothesisBriefHandoff.from_dict(result.data["downstream_handoff"])
    assert handoff.brief_ref.artifact_type == HYPOTHESIS_CARD
    assert handoff.brief_ref.artifact_id == brief.artifact_id
    assert handoff.decision_rules == brief.decision_rules
    assert "Data Agent" in handoff.target_roles


def test_exact_revision_replay_is_idempotent_but_changed_payload_conflicts() -> None:
    """Retries return the same revision while a changed payload cannot overwrite it."""
    store = InMemoryResearchArtifactStore()
    brief = _brief()
    first = persist_hypothesis_brief(brief=brief, artifact_store=store)
    replay = persist_hypothesis_brief(brief=brief, artifact_store=store)

    assert first.ok is True
    assert replay.ok is True
    assert replay.data["idempotent_replay"] is True
    changed = replace(brief, mechanism="A changed mechanism")
    conflict = persist_hypothesis_brief(brief=changed, artifact_store=store)
    assert conflict.ok is False
    assert "conflicts" in conflict.errors[0]["message"]


def test_successor_revision_requires_and_preserves_prior_lineage() -> None:
    """Revision two must name the immediately persisted revision one artifact."""
    store = InMemoryResearchArtifactStore()
    first = _brief()
    assert persist_hypothesis_brief(brief=first, artifact_store=store).ok is True

    second = replace(
        first,
        revision=2,
        supersedes_id=first.artifact_id,
        mechanism="A refined mechanism",
    )
    result = persist_hypothesis_brief(brief=second, artifact_store=store)
    assert result.ok is True
    assert result.data["hypothesis_brief"]["supersedes_id"] == first.artifact_id

    missing_prior = replace(
        first,
        brief_id="other",
        revision=2,
        supersedes_id="missing",
    )
    failed = persist_hypothesis_brief(brief=missing_prior, artifact_store=store)
    assert failed.ok is False
    assert "immediately preceding" in failed.errors[0]["message"]


def test_missing_falsifier_and_scope_contradiction_fail_closed() -> None:
    """A brief cannot proceed without a falsifier or with mutually exclusive scope claims."""
    with pytest.raises(ValueError, match="hypothesis falsifier is required"):
        replace(_brief(), falsifier="")

    with pytest.raises(ValueError, match="scope is contradictory"):
        HypothesisScope(
            universe="selected symbols",
            timeframe="1D",
            start="2024-01-01T00:00:00Z",
            end="2024-02-01T00:00:00Z",
            symbols=("AAPL",),
            excluded_symbols=("aapl",),
        )


def test_scope_window_and_decision_rules_are_required() -> None:
    """Invalid windows and empty outcome decisions are rejected before persistence."""
    with pytest.raises(ValueError, match="end must be after start"):
        HypothesisScope(
            universe="all equities",
            timeframe="1D",
            start="2024-02-01T00:00:00Z",
            end="2024-01-01T00:00:00Z",
        )
    with pytest.raises(ValueError, match="decision_rules are required"):
        replace(_brief(), decision_rules={})


def test_unauthorized_actor_and_agent_acceptance_are_rejected() -> None:
    """Only operators or the registered hypothesis/design roles can write a proposed brief."""
    with pytest.raises(ValueError, match="unauthorized"):
        replace(_brief(), actor="Strategy Engineering Agent")
    with pytest.raises(ValueError, match="only a human operator"):
        replace(_brief(), actor=HYPOTHESIS_AGENT_OWNER, status="accepted")


def test_attribution_arguments_must_match_brief_identity() -> None:
    """Service boundary attribution cannot silently replace the brief's requester or actor."""
    result = persist_hypothesis_brief(
        brief=_brief(),
        requested_by="operator:other",
        artifact_store=InMemoryResearchArtifactStore(),
    )
    assert result.ok is False
    assert "requested_by attribution drift" in result.errors[0]["message"]


def test_handoff_resolution_re_reads_digest_for_each_authorized_recipient() -> None:
    """Every downstream role resolves the same canonical revision before constructing work."""
    store = InMemoryResearchArtifactStore()
    result = persist_hypothesis_brief(brief=_brief(), artifact_store=store)
    handoff = HypothesisBriefHandoff.from_dict(result.data["downstream_handoff"])

    for recipient in handoff.target_roles:
        resolved = resolve_hypothesis_brief_handoff(
            handoff=handoff,
            recipient=recipient,
            artifact_store=store,
        )
        assert resolved.ok is True
        assert resolved.data["recipient"] == recipient
        assert resolved.data["hypothesis_brief"] == _brief().to_dict()


def test_handoff_resolution_rejects_unauthorized_recipient_and_digest_drift() -> None:
    """A non-target consumer or replaced canonical payload cannot use a stale handoff."""
    store = InMemoryResearchArtifactStore()
    brief = _brief()
    result = persist_hypothesis_brief(brief=brief, artifact_store=store)
    handoff = HypothesisBriefHandoff.from_dict(result.data["downstream_handoff"])

    unauthorized = resolve_hypothesis_brief_handoff(
        handoff=handoff,
        recipient="Broker Agent",
        artifact_store=store,
    )
    assert unauthorized.ok is False
    assert "not authorized" in unauthorized.errors[0]["message"]

    store.save_artifact(
        artifact_type=HYPOTHESIS_CARD,
        artifact_id=brief.artifact_id,
        domain_owner="Experiments",
        producer_tool="test_replace",
        payload={**brief.to_dict(), "mechanism": "replaced after handoff"},
        requested_by=brief.requested_by,
        actor=brief.actor,
        status=brief.status,
        metadata={"brief_id": brief.brief_id, "revision": brief.revision},
    )
    drifted = resolve_hypothesis_brief_handoff(
        handoff=handoff,
        recipient="Data Agent",
        artifact_store=store,
    )
    assert drifted.ok is False
    assert "payload digest" in drifted.errors[0]["message"]


def test_handoff_resolution_rejects_forged_decisions_and_unknown_roles() -> None:
    """A handoff cannot widen recipients or alter decision rules outside the canonical brief."""
    store = InMemoryResearchArtifactStore()
    brief = _brief()
    result = persist_hypothesis_brief(brief=brief, artifact_store=store)
    handoff_payload = result.data["downstream_handoff"]

    forged_decisions = {
        **handoff_payload,
        "decision_rules": {"supports": "Skip evaluation and deploy."},
    }
    forged = resolve_hypothesis_brief_handoff(
        handoff=forged_decisions,
        recipient="Data Agent",
        artifact_store=store,
    )
    assert forged.ok is False
    assert "decision rules drift" in forged.errors[0]["message"]

    forged_roles = {**handoff_payload, "target_roles": ["Broker Agent"]}
    rejected = resolve_hypothesis_brief_handoff(
        handoff=forged_roles,
        recipient="Broker Agent",
        artifact_store=store,
    )
    assert rejected.ok is False
    assert "unsupported roles" in rejected.errors[0]["message"]


def _brief() -> HypothesisBrief:
    """Build one complete instrument-agnostic brief for contract tests."""
    return HypothesisBrief(
        brief_id="brief_demo",
        revision=1,
        question="Does a bounded momentum signal persist after costs?",
        mechanism="Delayed reaction to information creates a measurable continuation effect.",
        falsifier="Reject if the pre-registered holdout effect is non-positive after costs.",
        scope=HypothesisScope(
            universe="instrument-agnostic liquid instruments",
            timeframe="1D",
            start="2024-01-01T00:00:00Z",
            end="2024-06-30T00:00:00Z",
            asset_class="equity",
            source_policy="approved_provider",
        ),
        expected_evidence=(
            "Out-of-sample return after declared costs",
            "Turnover and drawdown evidence",
        ),
        assumptions=(
            "Bars are point-in-time and complete for the declared scope",
            "Execution uses the declared fill model",
        ),
        decision_rules={
            "supports": "Advance to independent evaluation and robustness review.",
            "falsified": "Reject the hypothesis and record the limiting evidence.",
            "inconclusive": "Refine the scope or mechanism before another run.",
        },
        requested_by="operator:jared",
        actor=HYPOTHESIS_AGENT_OWNER,
    )
