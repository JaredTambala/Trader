"""Focused contracts for deterministic agentic qualification fixtures."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from tests.support.agentic_fixture import (
    build_qualification_strategy_validation_service,
    run_qualification_backfill,
    seed_implementation_catalogue,
    seed_initial_market_data,
)
from tests.support.agentic_scenarios import (
    build_agentic_scenario_sessions,
    load_agentic_scenario_inputs,
)
from tests.support.duckdb_store import DuckDBEventStore
from trader_agents.inputs import (
    composite_data_scope_from_session,
    strategy_build_contract_from_session,
)
from trader_research.data import (
    DataEnsureLoadedRequest,
    DataQualityRequest,
    data_summarize_quality,
)
from trader_research.experiments import (
    ImplementationComparisonRequest,
    ImplementationSearchRequest,
    compare_implementation,
    register_strategy_implementation,
    search_implementations,
)
from trader_research.foundation import (
    ContextualResearchArtifactStore,
    InMemoryResearchArtifactStore,
    stable_research_id,
)
from trader_research.governance import ResearchSession


_FREEZE = "a" * 40
_CANDIDATE_SOURCE = """
from trader.strategies import Strategy


class CandidateStrategy(Strategy):
    @property
    def strategy_id(self):
        return "qualification-candidate"

    def generate_orders(self, **kwargs):
        del kwargs
        return ()


def build_strategy(**kwargs):
    del kwargs
    return CandidateStrategy()
""".lstrip()


def test_complete_and_gap_fixtures_use_real_quality_evidence(tmp_path: Path) -> None:
    """Complete one exact gap without network access or favorable narrowing."""
    scenario = load_agentic_scenario_inputs()["bounded_backfill_and_adaptation"]
    sessions = build_agentic_scenario_sessions(
        scenario.scenario_id,
        repetition=1,
        freeze_revision=_FREEZE,
    )
    store = DuckDBEventStore(str(tmp_path / "bars.duckdb"))
    try:
        seed_initial_market_data(store, scenario, sessions)
        request = _data_request(sessions[0])
        before = _quality(store, request)

        result = run_qualification_backfill(
            request,
            store,
            scenario=scenario,
            sessions=sessions,
        )
        after = _quality(store, request)
    finally:
        store.close()

    assert before["complete"] is False
    assert result == {
        "rows_loaded": 1,
        "source": "qualification_fixture",
        "network_calls": 0,
        "fixture_state": "one_in_envelope_gap_then_complete",
    }
    assert after["complete"] is True


def test_unfit_fixture_remains_incomplete_after_permitted_loading(
    tmp_path: Path,
) -> None:
    """Preserve an exact negative result after the admitted local loading action."""
    scenario = load_agentic_scenario_inputs()["unfit_requested_scope"]
    sessions = build_agentic_scenario_sessions(
        scenario.scenario_id,
        repetition=1,
        freeze_revision=_FREEZE,
    )
    store = DuckDBEventStore(str(tmp_path / "unfit-bars.duckdb"))
    try:
        seed_initial_market_data(store, scenario, sessions)
        request = _data_request(sessions[0])
        result = run_qualification_backfill(
            request,
            store,
            scenario=scenario,
            sessions=sessions,
        )
        quality = _quality(store, request)
    finally:
        store.close()

    assert result["rows_loaded"] > 0
    assert quality["complete"] is False
    assert quality["missing_bar_count"] == 1


def test_exact_and_closest_catalogue_fixtures_use_real_admission() -> None:
    """Make exact reuse eligible while a closest candidate remains incompatible."""
    scenarios = load_agentic_scenario_inputs()
    exact_session = build_agentic_scenario_sessions(
        "exact_reuse",
        repetition=1,
        freeze_revision=_FREEZE,
    )[0]
    closest_session = build_agentic_scenario_sessions(
        "bounded_backfill_and_adaptation",
        repetition=1,
        freeze_revision=_FREEZE,
    )[0]
    store = InMemoryResearchArtifactStore()
    seed_implementation_catalogue(store, scenarios["exact_reuse"], (exact_session,))
    seed_implementation_catalogue(
        store,
        scenarios["bounded_backfill_and_adaptation"],
        (closest_session,),
    )

    exact = _catalogue_comparison(store, exact_session)
    closest = _catalogue_comparison(store, closest_session)

    assert exact["direct_reuse_eligible"] is True
    assert all(item["status"] == "match" for item in exact["fields"])
    assert closest["direct_reuse_eligible"] is False
    assert any(item["status"] == "different" for item in closest["fields"])


def test_admission_sequence_is_candidate_bound_restart_safe_and_real() -> None:
    """Preserve one failure across replay, then fully admit a new candidate."""
    scenario = load_agentic_scenario_inputs()["new_authorship_and_repair"]
    sessions = build_agentic_scenario_sessions(
        scenario.scenario_id,
        repetition=1,
        freeze_revision=_FREEZE,
    )
    underlying = InMemoryResearchArtifactStore()
    store = ContextualResearchArtifactStore(
        underlying,
        requested_by=sessions[0].session_id,
        actor="Strategy Engineering Agent",
    )
    service = build_qualification_strategy_validation_service(
        scenario,
        sessions,
    )
    first_id = _register_candidate(store, version="1", source=_CANDIDATE_SOURCE)

    first = service(
        implementation_version_id=first_id,
        fixture_parameters={},
        artifact_store=store,
    )
    replay = service(
        implementation_version_id=first_id,
        fixture_parameters={},
        artifact_store=store,
    )
    second_id = _register_candidate(
        store,
        version="2",
        source=f"{_CANDIDATE_SOURCE}\n# Evidence-led repair.\n",
    )
    repaired = service(
        implementation_version_id=second_id,
        fixture_parameters={},
        artifact_store=store,
    )

    assert first.ok is False
    assert replay.ok is False
    assert replay.artifacts == first.artifacts
    assert first.errors[0]["code"] == "implementation_validation_failed"
    first_report = first.data["implementation_validation_report"]
    assert first_report["blockers"] == [
        "unknown parameter: qualification_nonsemantic_admission_defect"
    ]
    assert repaired.ok is True
    assert (
        repaired.data["implementation_validation_report"]["fixture"]["status"]
        == "passed"
    )


def test_admission_sequence_rejects_unattributed_and_excess_candidates() -> None:
    """Fail closed when session lineage is absent or its sequence is exhausted."""
    scenario = load_agentic_scenario_inputs()["bounded_backfill_and_adaptation"]
    sessions = build_agentic_scenario_sessions(
        scenario.scenario_id,
        repetition=1,
        freeze_revision=_FREEZE,
    )
    underlying = InMemoryResearchArtifactStore()
    contextual = ContextualResearchArtifactStore(
        underlying,
        requested_by=sessions[0].session_id,
        actor="Strategy Engineering Agent",
    )
    service = build_qualification_strategy_validation_service(scenario, sessions)
    first_id = _register_candidate(
        contextual,
        version="1",
        source=_CANDIDATE_SOURCE,
    )
    second_id = _register_candidate(
        contextual,
        version="2",
        source=f"{_CANDIDATE_SOURCE}\n# Unauthorized extra candidate.\n",
    )

    missing_context = service(
        implementation_version_id=first_id,
        artifact_store=underlying,
    )
    exhausted = service(
        implementation_version_id=second_id,
        artifact_store=contextual,
    )

    assert missing_context.errors[0]["code"] == (
        "qualification_admission_fixture_error"
    )
    assert exhausted.errors[0]["code"] == "qualification_admission_fixture_error"
    assert "sequence is exhausted" in exhausted.errors[0]["message"]


def _data_request(session: ResearchSession) -> DataEnsureLoadedRequest:
    """Build the exact first Data-scope request from one fixture session."""
    scope = composite_data_scope_from_session(session)
    item = scope.items[0]
    return DataEnsureLoadedRequest(
        symbols=tuple(item.symbols),
        asset_class=item.asset_class,
        timeframe=item.timeframe,
        start=datetime.fromisoformat(item.start.replace("Z", "+00:00")),
        end=datetime.fromisoformat(item.end.replace("Z", "+00:00")),
        mode="backfill",
        provider="alpaca",
        instrument_type="crypto",
        bar_type="trade_bar",
        configured_provider="alpaca",
        configured_asset_class="crypto",
    )


def _quality(
    store: DuckDBEventStore,
    request: DataEnsureLoadedRequest,
) -> dict[str, object]:
    """Return real deterministic quality output for one fixture request."""
    result = data_summarize_quality(
        store,
        DataQualityRequest(
            symbols=request.symbols,
            asset_class=request.asset_class,
            timeframe=request.timeframe,
            start=request.start,
            end=request.end,
            provider=request.provider,
            instrument_type=request.instrument_type,
            bar_type=request.bar_type,
            configured_provider=request.configured_provider,
            configured_asset_class=request.configured_asset_class,
        ),
    )
    assert result.ok is True
    return dict(result.data["data_quality_report"])


def _catalogue_comparison(
    store: InMemoryResearchArtifactStore,
    session: ResearchSession,
) -> dict[str, Any]:
    """Search and compare the top admitted candidate to the exact contract."""
    branch_id = stable_research_id(
        "agent_branch",
        {"session_id": session.session_id, "task_id": "strategy"},
    )
    contract = strategy_build_contract_from_session(session, branch_id=branch_id)
    search = search_implementations(
        store,
        ImplementationSearchRequest(
            query=contract.name,
            implementation_kinds=(contract.implementation_kind,),
        ),
    )
    rows = [
        row
        for row in search.data["implementations"]
        if row.get("catalogue_tier") == "admitted"
        and str(row.get("name") or "").startswith(contract.name)
    ]
    assert rows
    comparison = compare_implementation(
        store,
        ImplementationComparisonRequest(
            implementation_ref=str(rows[0]["implementation_version_id"]),
            build_contract={
                "implementation_kind": contract.implementation_kind,
                "runtime_contract": contract.runtime_interface,
                "portfolio_mode": contract.portfolio_mode,
                "required_capabilities": list(contract.required_capabilities),
                "parameters": {
                    item.name: {"type": item.value_type} for item in contract.parameters
                },
            },
        ),
    )
    assert comparison.ok is True
    return dict(comparison.data)


def _register_candidate(
    store: ContextualResearchArtifactStore,
    *,
    version: str,
    source: str,
) -> str:
    """Register one valid session-attributed Strategy candidate and return its ID."""
    result = register_strategy_implementation(
        name="QualificationCandidate",
        version=version,
        source_code=source,
        factory_name="build_strategy",
        class_name="CandidateStrategy",
        parameter_schema={
            "type": "object",
            "properties": {},
            "required": [],
        },
        dependencies=(),
        authoring_origin="agent_authored",
        capabilities=("target_allocations",),
        artifact_store=store,
    )
    assert result.ok is True
    return str(result.data["implementation_version"]["implementation_version_id"])
