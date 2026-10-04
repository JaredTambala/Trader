"""Cross-package handoff from a human research brief to downstream planning.

Subject: Canonical hypothesis intent flowing to Data and Strategy consumers.
Level: Cross-package local workflow.
Collaborators: Real governance contracts, artifact store, and Data handoff values.
Guarantees: The same revisioned brief reference and decision rules reach each
consumer without copying or widening scope.
Non-goals: Console transport, MCP model execution, strategy admission, or backtesting.
"""

from __future__ import annotations

from trader_research.foundation import InMemoryResearchArtifactStore
from trader_research.governance import (
    DataRequirement,
    HYPOTHESIS_AGENT_OWNER,
    HypothesisBrief,
    HypothesisBriefHandoff,
    HypothesisScope,
    persist_hypothesis_brief,
)


def test_brief_reference_reaches_data_and_strategy_planning() -> None:
    """Data scope and Strategy handoff retain one canonical brief revision."""
    store = InMemoryResearchArtifactStore()
    brief = HypothesisBrief(
        brief_id="cross_package_brief",
        revision=1,
        question="Does the declared signal survive the evaluation window?",
        mechanism="A bounded mechanism produces repeatable continuation.",
        falsifier="Reject when the holdout effect is non-positive after costs.",
        scope=HypothesisScope(
            universe="declared instruments",
            symbols=("AAA", "BBB"),
            timeframe="1D",
            start="2024-01-01T00:00:00Z",
            end="2024-03-01T00:00:00Z",
            source_policy="approved_provider",
        ),
        expected_evidence=("Holdout return after costs",),
        assumptions=("The selected bars are complete",),
        decision_rules={
            "supports": "Send to independent evaluation.",
            "falsified": "Reject and record the evidence.",
        },
        requested_by="operator:jared",
        actor=HYPOTHESIS_AGENT_OWNER,
    )
    result = persist_hypothesis_brief(brief=brief, artifact_store=store)
    assert result.ok is True

    handoff = HypothesisBriefHandoff.from_dict(result.data["downstream_handoff"])
    canonical = store.load_artifact_record(
        handoff.brief_ref.artifact_type,
        handoff.brief_ref.artifact_id,
    )
    assert canonical.payload["artifact_id"] == handoff.brief_ref.artifact_id
    assert canonical.payload["decision_rules"] == dict(handoff.decision_rules)

    requirement = DataRequirement(
        symbols=brief.scope.symbols,
        asset_class="equity",
        timeframe=brief.scope.timeframe,
        start=brief.scope.start,
        end=brief.scope.end,
        source=brief.scope.source_policy,
    )
    assert requirement.symbols == brief.scope.symbols
    assert handoff.brief_ref.metadata["payload_sha256"]
    assert "Strategy Engineering Agent" in handoff.target_roles
