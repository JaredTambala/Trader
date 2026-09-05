"""Contracts for the admitted and maintained implementation catalogue.

Subject: Search, exact resolution, trust tiers, source disclosure, and comparison evidence.
Level: In-process application contract.
Collaborators: Maintained metadata, canonical implementation artifacts, and validation reports.
Guarantees: Unadmitted source stays bounded and comparisons inform without taking reuse authority.
Non-goals: Candidate authoring, strategy admission, experiment execution, Postgres, or agent decisions.
"""

from __future__ import annotations

from trader_research.experiments import (
    ImplementationComparisonRequest,
    ImplementationSearchRequest,
    build_implementation_version,
    compare_implementation,
    get_implementation,
    search_implementations,
)
from trader_research.foundation import InMemoryResearchArtifactStore
from trader_research.governance.artifacts import (
    DOMAIN_OWNER_BY_ARTIFACT_TYPE,
    IMPLEMENTATION_VALIDATION_REPORT,
    IMPLEMENTATION_VERSION,
)


def test_catalogue_separates_maintained_metadata_from_admitted_reuse() -> None:
    """Catalogue results distinguish neutral maintained metadata from validated reusable implementations."""
    store = InMemoryResearchArtifactStore()
    implementation = _save_implementation(store, admitted=True)

    result = search_implementations(
        store,
        ImplementationSearchRequest(
            query="multi asset trend",
            implementation_kinds=("strategy",),
            capabilities=("multi_asset",),
        ),
    )

    assert result.ok is True
    rows = result.data["implementations"]
    admitted = next(row for row in rows if row["catalogue_tier"] == "admitted")
    assert (
        admitted["implementation_version_id"]
        == implementation.implementation_version_id
    )
    assert admitted["direct_reuse_eligible"] is True
    assert "source_code" not in admitted
    assert all(
        row["direct_reuse_eligible"] is False
        for row in rows
        if row["catalogue_tier"] == "maintained_metadata"
    )


def test_catalogue_hides_unadmitted_versions_by_default() -> None:
    """Unadmitted implementation versions remain hidden unless explicitly requested as untrusted references."""
    store = InMemoryResearchArtifactStore()
    implementation = _save_implementation(store, admitted=False)

    hidden = search_implementations(
        store,
        ImplementationSearchRequest(
            query=implementation.name,
            implementation_kinds=("strategy",),
        ),
    )
    visible = search_implementations(
        store,
        ImplementationSearchRequest(
            query=implementation.name,
            implementation_kinds=("strategy",),
            include_unadmitted=True,
        ),
    )

    assert implementation.implementation_version_id not in {
        row["implementation_version_id"] for row in hidden.data["implementations"]
    }
    row = next(
        row
        for row in visible.data["implementations"]
        if row["implementation_version_id"] == implementation.implementation_version_id
    )
    assert row["trust_tier"] == "untrusted_reference"
    assert row["direct_reuse_eligible"] is False


def test_exact_resolution_reveals_source_only_when_requested() -> None:
    """Exact resolution discloses implementation source only through the explicit source option."""
    store = InMemoryResearchArtifactStore()
    implementation = _save_implementation(store, admitted=True)

    bounded = get_implementation(store, implementation.implementation_version_id)
    authorized = get_implementation(
        store,
        implementation.implementation_version_id,
        include_source=True,
    )

    assert bounded.ok is True
    assert "source_code" not in bounded.data["implementation"]
    assert (
        authorized.data["implementation"]["source_code"] == implementation.source_code
    )
    assert authorized.artifacts["implementation_version"]["uri"].endswith(
        implementation.implementation_version_id
    )


def test_comparison_supports_but_does_not_take_reuse_decision() -> None:
    """Comparison reports contract compatibility while preserving Strategy Engineering decision authority."""
    store = InMemoryResearchArtifactStore()
    implementation = _save_implementation(store, admitted=True)

    result = compare_implementation(
        store,
        ImplementationComparisonRequest(
            implementation_ref=implementation.implementation_version_id,
            build_contract={
                "implementation_kind": "strategy",
                "runtime_contract": "trader.strategies.Strategy",
                "portfolio_mode": "single_or_multi_asset",
                "required_capabilities": ["multi_asset", "trend"],
                "parameters": {"lookback": {"type": "integer"}},
            },
        ),
    )

    assert result.ok is True
    assert result.data["direct_reuse_eligible"] is True
    assert result.data["decision_authority"] == "strategy_engineering_agent"
    assert all(field["status"] == "match" for field in result.data["fields"])
    assert result.data["limitations"]


def _save_implementation(
    store: InMemoryResearchArtifactStore,
    *,
    admitted: bool,
):
    implementation = build_implementation_version(
        implementation_kind="strategy",
        name="Multi Asset Trend",
        version="1",
        source_code="def build_strategy(**kwargs):\n    return kwargs\n",
        class_name=None,
        factory_name="build_strategy",
        parameter_schema={"lookback": {"type": "integer", "default": 20, "minimum": 2}},
        dependencies=(),
        authoring_origin="operator_specified",
        capabilities=("multi_asset", "trend"),
        runtime_requirements={},
        resource_bounds={},
        provenance_refs=(),
        metadata={
            "description": "Multi asset trend strategy.",
            "portfolio_mode": "single_or_multi_asset",
        },
    )
    store.save_artifact(
        artifact_type=IMPLEMENTATION_VERSION,
        artifact_id=implementation.implementation_version_id,
        domain_owner=DOMAIN_OWNER_BY_ARTIFACT_TYPE[IMPLEMENTATION_VERSION],
        producer_tool="research_register_strategy_implementation",
        payload=implementation.to_dict(),
        status="registered",
        source_hash=implementation.source_hash,
    )
    if admitted:
        validation_id = "validation_demo"
        store.save_artifact(
            artifact_type=IMPLEMENTATION_VALIDATION_REPORT,
            artifact_id=validation_id,
            domain_owner=DOMAIN_OWNER_BY_ARTIFACT_TYPE[
                IMPLEMENTATION_VALIDATION_REPORT
            ],
            producer_tool="research_validate_strategy_implementation",
            payload={
                "artifact_type": IMPLEMENTATION_VALIDATION_REPORT,
                "validation_id": validation_id,
                "implementation_version_id": implementation.implementation_version_id,
                "implementation_kind": "strategy",
                "source_hash": implementation.source_hash,
                "status": "passed",
                "valid": True,
                "blockers": [],
            },
            status="passed",
            source_hash=implementation.source_hash,
        )
    return implementation
