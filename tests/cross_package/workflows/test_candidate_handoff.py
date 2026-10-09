"""Deterministic hypothesis-to-candidate handoff qualification.

Subject: Candidate construction from one revisioned hypothesis brief.
Level: Cross-package local workflow.
Collaborators: Governance brief, implementation catalogue, admission reports,
and immutable strategy/risk specifications.
Guarantees: A source-free candidate record preserves exact lineage and refuses
missing, blocked, or incompatible dependencies.
Non-goals: Third-party model qualification, Console/browser review, backtest
execution, or paper admission.
"""

from __future__ import annotations

from trader_research.experiments import (
    create_risk_stack_specification,
    create_strategy_candidate_handoff,
    create_strategy_specification,
    register_risk_manager_implementation,
    register_strategy_implementation,
    resolve_strategy_candidate_handoff,
    validate_risk_manager_implementation,
    validate_risk_stack_specification,
    validate_strategy_implementation,
    validate_strategy_specification,
)
from trader_research.foundation import InMemoryResearchArtifactStore
from trader_research.governance import (
    DataRequirement,
    HYPOTHESIS_AGENT_OWNER,
    HypothesisBrief,
    HypothesisBriefHandoff,
    HypothesisScope,
    persist_hypothesis_brief,
)


STRATEGY_SOURCE = """
from trader.strategies import Strategy

class CandidateStrategy(Strategy):
    @property
    def strategy_id(self):
        return "candidate:1"

    def generate_orders(self, **kwargs):
        return ()

def build_strategy(period=2, **kwargs):
    return CandidateStrategy()
"""

RISK_SOURCE = """
from trader.risk import RiskManager

class CandidateRisk(RiskManager):
    def validate(self, orders, context):
        return list(orders)

def build_risk_manager(max_orders=10):
    return CandidateRisk()
"""


def test_reconstructable_reuse_handoff_preserves_all_lineage() -> None:
    """A passed brief, comparison, admission, and specs produce one source-free record."""
    store = InMemoryResearchArtifactStore()
    brief_result = persist_hypothesis_brief(brief=_brief(), artifact_store=store)
    assert brief_result.ok
    handoff = HypothesisBriefHandoff.from_dict(brief_result.data["downstream_handoff"])

    strategy_validation = _validated_strategy(store)
    risk_validation = _validated_risk(store)
    comparison = {
        "comparison_id": "comparison:exact-reuse",
        "implementation_version_id": strategy_validation["implementation_version_id"],
        "validation_ref": strategy_validation["validation_id"],
        "direct_reuse_eligible": True,
        "decision_authority": "strategy_engineering_agent",
        "fields": [{"field": "runtime_contract", "status": "match"}],
    }
    result = create_strategy_candidate_handoff(
        brief_handoff=handoff,
        catalogue_comparison=comparison,
        construction_decision="exact_reuse",
        strategy_validation_ref=_validated_specifications(store, strategy_validation, risk_validation)[0],
        risk_validation_ref=_validated_specifications(store, strategy_validation, risk_validation)[1],
        next_decision="Submit the candidate for independent evaluation.",
        artifact_store=store,
    )
    assert result.ok, result.errors
    candidate = result.data["candidate"]
    assert candidate["brief_ref"]["revision"] == 1
    assert candidate["construction_decision"] == "exact_reuse"
    assert "source_code" not in str(candidate)

    resolved = resolve_strategy_candidate_handoff(
        candidate_ref=candidate["candidate_id"], artifact_store=store
    )
    assert resolved.ok, resolved.errors
    assert resolved.data["candidate"] == candidate


def test_handoff_fails_closed_for_blocked_validation_and_ineligible_reuse() -> None:
    """Blocked admission and incompatible catalogue decisions cannot create a candidate."""
    store = InMemoryResearchArtifactStore()
    brief_result = persist_hypothesis_brief(brief=_brief(), artifact_store=store)
    handoff = HypothesisBriefHandoff.from_dict(brief_result.data["downstream_handoff"])
    strategy_validation = _validated_strategy(store)
    risk_validation = _validated_risk(store)
    strategy_spec_ref, risk_spec_ref = _validated_specifications(store, strategy_validation, risk_validation)

    blocked = create_strategy_candidate_handoff(
        brief_handoff=handoff,
        catalogue_comparison={
            "comparison_id": "comparison:blocked",
            "direct_reuse_eligible": False,
            "decision_authority": "strategy_engineering_agent",
        },
        construction_decision="exact_reuse",
        strategy_validation_ref=strategy_spec_ref,
        risk_validation_ref=str(risk_spec_ref) + "-missing",
        next_decision="Repair the missing risk evidence.",
        artifact_store=store,
    )
    assert blocked.ok is False
    assert "directly reusable" in blocked.errors[0]["message"]

    missing_validation = create_strategy_candidate_handoff(
        brief_handoff=handoff,
        catalogue_comparison={
            "comparison_id": "comparison:missing-risk",
            "direct_reuse_eligible": True,
            "decision_authority": "strategy_engineering_agent",
        },
        construction_decision="exact_reuse",
        strategy_validation_ref=strategy_spec_ref,
        risk_validation_ref=str(risk_spec_ref) + "-missing",
        next_decision="Repair the missing risk evidence.",
        artifact_store=store,
    )
    assert missing_validation.ok is False
    assert "unknown research artifact" in missing_validation.errors[0]["message"]


def _validated_strategy(store: InMemoryResearchArtifactStore) -> dict[str, str]:
    registered = register_strategy_implementation(
        name="candidate_strategy", version="1", source_code=STRATEGY_SOURCE,
        factory_name="build_strategy", parameter_schema={"type": "object", "properties": {}, "required": []},
        artifact_store=store,
    )
    assert registered.ok
    result = validate_strategy_implementation(
        implementation_version_id=registered.data["implementation_version"]["implementation_version_id"],
        artifact_store=store,
    )
    assert result.ok
    return result.data["implementation_validation_report"]


def _validated_risk(store: InMemoryResearchArtifactStore) -> dict[str, str]:
    registered = register_risk_manager_implementation(
        name="candidate_risk", version="1", source_code=RISK_SOURCE,
        factory_name="build_risk_manager", parameter_schema={"type": "object", "properties": {}, "required": []},
        artifact_store=store,
    )
    assert registered.ok
    result = validate_risk_manager_implementation(
        implementation_version_id=registered.data["implementation_version"]["implementation_version_id"],
        artifact_store=store,
    )
    assert result.ok
    return result.data["implementation_validation_report"]


def _validated_specifications(store, strategy: dict[str, str], risk: dict[str, str]) -> tuple[str, str]:
    strategy_spec = create_strategy_specification(
        implementation_validation_ref=strategy["validation_id"], parameters={}, artifact_store=store
    )
    assert strategy_spec.ok
    strategy_report = validate_strategy_specification(
        strategy_specification_id=strategy_spec.data["strategy_specification"]["strategy_specification_id"],
        artifact_store=store,
    )
    assert strategy_report.ok
    risk_spec = create_risk_stack_specification(
        risk_managers=[{"implementation_validation_ref": risk["validation_id"], "parameters": {}}],
        artifact_store=store,
    )
    assert risk_spec.ok
    risk_report = validate_risk_stack_specification(
        risk_stack_specification_id=risk_spec.data["risk_stack_specification"]["risk_stack_specification_id"],
        artifact_store=store,
    )
    assert risk_report.ok
    return (
        str(strategy_report.data["strategy_specification_validation_report"]["validation_id"]),
        str(risk_report.data["risk_stack_specification_validation_report"]["validation_id"]),
    )


def _brief() -> HypothesisBrief:
    return HypothesisBrief(
        brief_id="candidate_handoff_brief", revision=1,
        question="Does the candidate survive the holdout?",
        mechanism="A bounded signal produces repeatable continuation.",
        falsifier="Reject when holdout return after costs is non-positive.",
        scope=HypothesisScope(universe="declared instruments", timeframe="1D", start="2025-01-01T00:00:00Z", end="2025-02-01T00:00:00Z", symbols=("AAA",), source_policy="approved_provider"),
        data_requirements=(DataRequirement(symbols=("AAA",), asset_class="equity", timeframe="1D", start="2025-01-01T00:00:00Z", end="2025-02-01T00:00:00Z", source="approved_provider"),),
        strategy_intent="Use the admitted candidate.", risk_intent="Bound exposure.", expected_evidence=("holdout return",), assumptions=("bars are complete",),
        decision_rules={"supports": "Submit for evaluation", "falsified": "Reject"}, requested_by="operator:jared", actor=HYPOTHESIS_AGENT_OWNER,
    )
