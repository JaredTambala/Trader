from __future__ import annotations

from pathlib import Path
import re

from trader_mcp.constants import REGISTERED_TOOL_NAMES
from trader_research.agents import AGENT_DEFINITIONS


REPO_ROOT = Path(__file__).resolve().parents[1]
DOC_ROOT = REPO_ROOT / "docs" / "research_agents"
CURRENT_DOCS = (
    "README.md",
    "architecture.md",
    "agents.md",
    "mcp_tools.md",
    "workflows.md",
    "operations.md",
    "semantic_extraction.md",
    "tool_contracts.md",
)
STALE_CURRENT_CLAIMS = (
    "backtest tools are not registered yet",
    "No backtest tool is exposed",
    "Planned:",
)


def test_research_agent_readme_links_canonical_docs_and_history() -> None:
    readme = (DOC_ROOT / "README.md").read_text(encoding="utf-8")

    for filename in CURRENT_DOCS:
        assert (DOC_ROOT / filename).exists()
        if filename != "README.md":
            assert f"({filename})" in readme
    assert "(history/)" in readme
    assert (DOC_ROOT / "history").is_dir()


def test_registered_mcp_tools_are_documented_once_in_canonical_catalog() -> None:
    catalog = (DOC_ROOT / "mcp_tools.md").read_text(encoding="utf-8")

    for tool_name in REGISTERED_TOOL_NAMES:
        assert catalog.count(f"`{tool_name}`") == 1, tool_name


def test_agent_identities_are_documented_in_canonical_agent_doc() -> None:
    agents_doc = (DOC_ROOT / "agents.md").read_text(encoding="utf-8")

    for definition in AGENT_DEFINITIONS:
        assert definition.display_name in agents_doc


def test_current_research_agent_docs_do_not_carry_stale_tool_claims() -> None:
    for path in _current_markdown_docs():
        content = path.read_text(encoding="utf-8")
        for stale_claim in STALE_CURRENT_CLAIMS:
            assert stale_claim not in content, f"{stale_claim!r} found in {path.relative_to(REPO_ROOT)}"


def test_rich_methodology_operator_guide_covers_required_workflows() -> None:
    workflows = (DOC_ROOT / "workflows.md").read_text(encoding="utf-8")
    operations = (DOC_ROOT / "operations.md").read_text(encoding="utf-8")
    contracts = (DOC_ROOT / "tool_contracts.md").read_text(encoding="utf-8")
    combined = "\n".join((workflows, operations, contracts)).lower()

    required_phrases = (
        "registration and ingestion are deliberately separate",
        "full-document ingestion",
        "field-level source/chunk/claim-span refs",
        "draft cards are still review artifacts",
        "source suitability matters",
        "pairs trading or cointegration",
        "options straddle",
        "technical indicator",
        "commodity sentiment indicator",
        "data agent scope",
    )

    for phrase in required_phrases:
        assert phrase in combined


def test_canonical_readme_links_resolve() -> None:
    readme_path = DOC_ROOT / "README.md"
    readme = readme_path.read_text(encoding="utf-8")

    for target in re.findall(r"\]\(([^)]+)\)", readme):
        if target.startswith(("http://", "https://", "#")):
            continue
        assert (readme_path.parent / target).exists(), target


def test_semantic_extraction_doc_is_canonical_and_preserves_overlap_invariant() -> None:
    semantic_doc = (DOC_ROOT / "semantic_extraction.md").read_text(encoding="utf-8")
    required_phrases = (
        "Evidence units are non-exclusive",
        "addressable claim span",
        "target-conditioned claim-span selection",
        "bounded multi-span field synthesis",
        "Another method appearing elsewhere in a cited evidence unit is not a blocker",
        "no maintained method-target registry",
    )
    for phrase in required_phrases:
        assert phrase in semantic_doc

    for filename in ("README.md", "architecture.md", "workflows.md", "tool_contracts.md"):
        content = (DOC_ROOT / filename).read_text(encoding="utf-8")
        assert "(semantic_extraction.md)" in content


def test_docs_pin_knowledge_baseline_and_identify_next_delivery_focus() -> None:
    readme = (DOC_ROOT / "README.md").read_text(encoding="utf-8")
    semantic_doc = (DOC_ROOT / "semantic_extraction.md").read_text(encoding="utf-8")
    contracts = (DOC_ROOT / "tool_contracts.md").read_text(encoding="utf-8")
    workflows = (DOC_ROOT / "workflows.md").read_text(encoding="utf-8")
    tracker = (REPO_ROOT / "plans" / "mcp_trading_research_tools_plan.md").read_text(encoding="utf-8")

    assert "The knowledge-base and methodology work is now a maintained subsystem" in readme
    assert "The implemented subsystem is pinned at the 33AB baseline" in semantic_doc
    assert "execution begins with content-addressed implementation versions" in contracts
    assert "Handwritten code and AI-produced code" in workflows
    assert "| 33AC. Composite Methodology Architecture | Deferred |" in tracker
    assert "| 56. Implementation Registry And Method-Card Decoupling | Done |" in tracker
    assert "| 56A. Canonical Implementation-Version Domain | Done |" in tracker
    assert "| 56D. Remove Method-Card Execution Coupling | Done |" in tracker
    assert "| 57. Reproducible Strategy, Risk, Backtest, And Optimisation Specifications | In progress |" in tracker
    assert "| 57C. DB-First Specification Execution And Evaluation | Done |" in tracker
    assert "| 57D. Provider-Neutral Optimisation Ledger And Protocols | Done |" in tracker
    assert "| 57H. Provider-Neutral Experiment Tracking Projection | Done |" in tracker
    assert "research_register_strategy_implementation" in tracker
    assert "A strategy or risk implementation with no methodology" in tracker
    assert "There is no compatibility interval" in tracker
    assert "Durable filesystem bundle paths are neither required nor returned" in tracker


def test_docs_define_provider_neutral_optimization_and_independent_review() -> None:
    architecture = (DOC_ROOT / "architecture.md").read_text(encoding="utf-8")
    agents = (DOC_ROOT / "agents.md").read_text(encoding="utf-8")
    catalog = (DOC_ROOT / "mcp_tools.md").read_text(encoding="utf-8")
    contracts = (DOC_ROOT / "tool_contracts.md").read_text(encoding="utf-8")
    operations = (DOC_ROOT / "operations.md").read_text(encoding="utf-8")
    workflows = (DOC_ROOT / "workflows.md").read_text(encoding="utf-8")
    combined = "\n".join((architecture, agents, catalog, contracts, operations, workflows))

    required_phrases = (
        "OptimizationEngine",
        "OptimizationTrialExecutor",
        "ExperimentTrackingSink",
        "research_create_parameter_optimization_plan",
        "research_project_experiment_tracking",
        "TRADER_MCP_ALLOW_OPTIMIZATION",
        "TRADER_MCP_ALLOW_OPTUNA_WRITES",
        "dedicated non-`public` schema",
        "non-authoritative",
        "sealed holdout",
        "Adversarial",
    )
    for phrase in required_phrases:
        assert phrase in combined

    assert "MLflow is authoritative for ML lifecycle records only" in architecture
    assert "Trader never queries that" in architecture
    assert "ml_list_experiments" not in combined
    assert "ml_list_training_experiments" in combined


def test_docs_define_controlled_verification_profiles_and_stop_conditions() -> None:
    operations = (DOC_ROOT / "operations.md").read_text(encoding="utf-8")
    normalized_operations = " ".join(operations.split())
    tracker = (REPO_ROOT / "plans" / "mcp_trading_research_tools_plan.md").read_text(
        encoding="utf-8"
    )

    for task in (
        "57I. Freeze Revision And Build Acceptance Matrix",
        "57J. Provision Isolated Verification Runtime",
        "57K. Static, Contract, And Regression Gate",
        "57L. Realistic Deterministic Evidence Fixture",
        "57M. Postgres-Native MCP Evidence Graph",
        "57N. Determinism, Integrity, And Leakage Tests",
        "57O. Restart, Resume, And Fault-Injection Tests",
        "57P. Provider Independence And Adapter Qualification",
        "57Q. Policy, Security, And Resource-Boundary Tests",
        "57R. Projection, Operator, And Bounded-Scale Checks",
        "57S. Acceptance Record And Release Decision",
    ):
        assert task in tracker

    required_phrases = (
        "one frozen Git revision",
        "Core:",
        "Trader Postgres:",
        "Optuna:",
        "Tracking sink:",
        "fallback to `PG_DB`",
        "stop condition",
        "PostgresResearchArtifactStore",
        "risk approvals and rejections",
        "no canonical filesystem path",
    )
    for phrase in required_phrases:
        assert phrase in normalized_operations


def test_tracker_freezes_57i_surface_and_acceptance_matrix() -> None:
    tracker = (REPO_ROOT / "plans" / "mcp_trading_research_tools_plan.md").read_text(
        encoding="utf-8"
    )

    required_inventory = (
        "#### 57I Frozen Surface Inventory",
        "`verification-57i-freeze`",
        "`research_register_strategy_implementation`",
        "`research_register_optimization_objective`",
        "`research_run_backtest_specification`",
        "`research_run_parameter_optimization`",
        "`research_project_experiment_tracking`",
        "`evaluation_generate_parameter_optimization_report`",
        "`adversarial_generate_parameter_optimization_audit`",
        "`parameter_optimization_trial`",
        "`research_parameter_optimization_trials`",
        "`TRADER_MCP_ALLOW_BACKTESTS`",
        "`TRADER_MCP_ALLOW_OPTIMIZATION`",
        "`TRADER_MCP_ALLOW_OPTUNA_WRITES`",
        "`TRADER_MCP_ALLOW_EXPERIMENT_TRACKING_WRITES`",
        "`research_create_strategy_candidate`",
        "`research_run_portfolio_backtest`",
        "`research_evaluation_reports`",
        "#### 57I Acceptance Matrix",
    )
    for phrase in required_inventory:
        assert phrase in tracker

    for invariant in range(36, 62):
        assert f"| {invariant} |" in tracker

    assert "Current graph is one-symbol, twelve-bar, empty-strategy smoke coverage" in tracker
    assert "Planned / 57L fixture and 57M graph" in tracker
    assert "Planned / 57S" in tracker


def test_docs_define_57j_isolated_postgres_runtime() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    operations = (DOC_ROOT / "operations.md").read_text(encoding="utf-8")
    tracker = (REPO_ROOT / "plans" / "mcp_trading_research_tools_plan.md").read_text(encoding="utf-8")
    combined = "\n".join((readme, operations, tracker))
    normalized_readme = " ".join(readme.split())

    required_phrases = (
        "#### 57J Isolated Runtime Contract",
        "PG_TEST_HOST",
        "PG_OPERATOR_HOST",
        "PG_OPTUNA_TEST_HOST",
        "PG_TEST_LOCALE",
        "verification_control.runtime_marker",
        "verification_control.operator_fingerprints",
        "tests.support.postgres_verification provision --reset",
        "before every `TRUNCATE`",
        "byte-identical to `verification-57i-freeze`",
    )
    for phrase in required_phrases:
        assert phrase in combined

    assert "They never read the legacy/operator `PG_HOST`" in normalized_readme
    assert "Product rows," in operations
    assert "passwords" in operations


def test_docs_define_complete_planned_mlflow_lifecycle_and_runtime_boundary() -> None:
    architecture = (DOC_ROOT / "architecture.md").read_text(encoding="utf-8")
    agents = (DOC_ROOT / "agents.md").read_text(encoding="utf-8")
    catalog = (DOC_ROOT / "mcp_tools.md").read_text(encoding="utf-8")
    contracts = (DOC_ROOT / "tool_contracts.md").read_text(encoding="utf-8")
    workflows = (DOC_ROOT / "workflows.md").read_text(encoding="utf-8")
    tracker = (REPO_ROOT / "plans" / "mcp_trading_research_tools_plan.md").read_text(encoding="utf-8")

    assert "## ML Lifecycle Architecture" in architecture
    assert "MLflow is authoritative for" in architecture
    assert "Random train/test splitting must not be the default" in architecture
    assert "must never change model behavior merely because an MLflow alias was reassigned" in architecture
    assert "The trading hot path must not call MCP" in architecture
    assert "## ML Lifecycle Ownership" in agents
    assert "## Planned MLflow Tool Universe" in catalog
    assert "external_research_mutating" in contracts
    assert "## Planned MLflow Model Lifecycle" in workflows
    assert "| 39A. MLflow Runtime Adapter And Mutation Policy | Planned |" in tracker
    assert "| 39J. Prediction Monitoring And Drift | Planned |" in tracker
    assert "| 40. ML Agent Graph and Handoff | Deferred |" in tracker


def test_docs_defer_walk_forward_optimization_but_keep_validation_foundational() -> None:
    readme = (DOC_ROOT / "README.md").read_text(encoding="utf-8")
    architecture = (DOC_ROOT / "architecture.md").read_text(encoding="utf-8")
    agents = (DOC_ROOT / "agents.md").read_text(encoding="utf-8")
    catalog = (DOC_ROOT / "mcp_tools.md").read_text(encoding="utf-8")
    contracts = (DOC_ROOT / "tool_contracts.md").read_text(encoding="utf-8")
    workflows = (DOC_ROOT / "workflows.md").read_text(encoding="utf-8")
    tracker = (REPO_ROOT / "plans" / "mcp_trading_research_tools_plan.md").read_text(encoding="utf-8")

    assert "| Walk-forward optimisation |" in readme
    assert "## Walk-Forward Validation And Optimisation" in architecture
    assert "Chronological walk-forward validation is foundational model-fitting correctness" in architecture
    assert "## Walk-Forward Optimisation Ownership" in agents
    assert "## Deferred Walk-Forward Tool Universe" in catalog
    assert "### Deferred Walk-Forward Contract Invariants" in contracts
    assert "## Deferred Walk-Forward Optimisation Workflow" in workflows
    assert "| 58. Walk-Forward Optimisation Core | Deferred |" in tracker
    assert "| 59. Walk-Forward Evaluation And Adversarial Audit | Deferred |" in tracker


def _current_markdown_docs() -> tuple[Path, ...]:
    return tuple(
        sorted(
            path
            for path in DOC_ROOT.glob("*.md")
            if "history" not in path.relative_to(DOC_ROOT).parts
        )
    )
