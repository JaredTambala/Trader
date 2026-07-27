from __future__ import annotations

from pathlib import Path
import re

from trader_mcp.constants import REGISTERED_TOOL_NAMES
from trader_research.governance.ownership import AGENT_DEFINITIONS


REPO_ROOT = Path(__file__).resolve().parents[1]
DOC_ROOT = REPO_ROOT / "docs" / "research_agents"
PRODUCT_STATE_PATH = DOC_ROOT / "product_state.md"
ROADMAP_PATH = REPO_ROOT / "plans" / "research_capability_roadmap.md"
LEGACY_TRACKER_PATH = REPO_ROOT / "plans" / "mcp_trading_research_tools_plan.md"
CURRENT_DOCS = (
    "README.md",
    "product_state.md",
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
        path_target, _, _ = target.partition("#")
        assert (readme_path.parent / path_target).exists(), target


def test_product_state_and_roadmap_links_resolve() -> None:
    for source_path in (PRODUCT_STATE_PATH, ROADMAP_PATH, LEGACY_TRACKER_PATH):
        content = source_path.read_text(encoding="utf-8")
        for target in re.findall(r"\]\(([^)]+)\)", content):
            if target.startswith(("http://", "https://", "#")):
                continue
            path_target, _, _ = target.partition("#")
            assert (source_path.parent / path_target).exists(), (
                source_path.relative_to(REPO_ROOT),
                target,
            )


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
    product_state = PRODUCT_STATE_PATH.read_text(encoding="utf-8")
    semantic_doc = (DOC_ROOT / "semantic_extraction.md").read_text(encoding="utf-8")
    contracts = (DOC_ROOT / "tool_contracts.md").read_text(encoding="utf-8")
    workflows = (DOC_ROOT / "workflows.md").read_text(encoding="utf-8")
    roadmap = ROADMAP_PATH.read_text(encoding="utf-8")

    assert "| Methodology extraction and method cards | implemented | integration |" in product_state
    assert "The implemented subsystem is pinned at the 33AB baseline" in semantic_doc
    assert "execution begins with content-addressed implementation versions" in contracts
    assert "Handwritten code and AI-produced code" in workflows
    assert "| KNOW-1 | Composite methodology representation | deferred | BASE-KNOW |" in roadmap
    assert "| BASE-IMPL | Knowledge-independent implementation admission through 56A-D |" in roadmap
    assert "| BASE-EXP | Strategy, risk-stack and backtest specifications through 57A-C |" in roadmap
    assert "| BASE-OPT | Provider-neutral optimisation and independent review through 57D-H |" in roadmap
    assert "Knowledge provenance is optional" not in roadmap
    assert "KNOWLEDGE ── optional provenance" in roadmap


def test_docs_define_current_research_architecture_and_refactor_lineage() -> None:
    readme = (DOC_ROOT / "README.md").read_text(encoding="utf-8")
    architecture = (DOC_ROOT / "architecture.md").read_text(encoding="utf-8")
    product_state = PRODUCT_STATE_PATH.read_text(encoding="utf-8")
    roadmap = ROADMAP_PATH.read_text(encoding="utf-8")

    required_readme_phrases = (
        "## What Trader Research Does",
        "## Start Here",
        "## Topic Reading Paths",
        "## Document Roles",
        "Data Agent scope and quality evidence",
        "canonical Postgres backtest",
        "Adversarial",
    )
    for phrase in required_readme_phrases:
        assert phrase in readme

    required_architecture_phrases = (
        "## Bounded Context Architecture",
        "### Context Map",
        "### Public And Transport Boundaries",
        "Business operations return typed application results",
        "There are no old-to-new Python modules, aliases, dual writes",
        "one evidence-backed, citeable methodology record",
        "`trader_research.data` is the sole application facade",
        "Provider SDK code does not belong to the Data context",
        "`trader_research.experiments` is the single outer application facade",
        "Neither adapter is imported by",
        "Review imports only `trader_research.experiments.reads`",
        "It exposes no implementation",
        "`trader_mcp` composes every domain operation through the public",
        "forcibly rejects every `optuna` and `mlflow` import",
        "### Boundary Enforcement",
        "### Refactor Record",
        "`verification-57i-freeze-v6`",
    )
    for phrase in required_architecture_phrases:
        assert phrase in architecture

    historical_architecture_phrases = (
        "## `trader_research` Refactor Review And Plan",
        "### Review Scope And Baseline",
        "### Baseline Findings",
        "### Staged Hard Cutover",
        "Production refactoring starts at TRR-5 only",
        "The refactor will establish",
    )
    for phrase in historical_architecture_phrases:
        assert phrase not in architecture

    assert "| BASE-ARCH | `trader_research` bounded-context cutover through TRR-12 |" in roadmap
    assert "| 53-54 and TRR-1 through TRR-12 |" in roadmap
    assert "`verification-57i-freeze-v6`" in product_state
    assert "Current operational state" in product_state
    assert "Target state" in product_state


def test_active_docs_reference_current_research_source_paths() -> None:
    current_docs = "\n".join(
        path.read_text(encoding="utf-8") for path in _current_markdown_docs()
    )
    stale_paths = (
        "src/trader_research/agents.py",
        "src/trader_research/domain.py",
        "src/trader_research/artifact_store.py",
        "src/trader_research/postgres_artifact_store.py",
    )

    assert "src/trader_research/governance/ownership.py" in current_docs
    assert "src/trader_research/governance/artifacts.py" in current_docs
    for stale_path in stale_paths:
        assert stale_path not in current_docs


def test_docs_walk_supplied_implementations_to_bounded_evidence() -> None:
    workflows = (DOC_ROOT / "workflows.md").read_text(encoding="utf-8")
    required_tools = (
        "research_register_strategy_implementation",
        "research_validate_strategy_implementation",
        "research_create_strategy_specification",
        "research_create_risk_stack_specification",
        "research_create_backtest_specification",
        "research_run_backtest_specification",
        "research_get_backtest_results",
        "evaluation_generate_parameter_optimization_report",
        "adversarial_create_parameter_optimization_audit_plan",
        "adversarial_generate_parameter_optimization_audit",
    )

    assert "## Worked Implementation-To-Evidence Walkthrough" in workflows
    assert "A method card is not required" in workflows
    assert "What it does not prove" in workflows
    assert "No stage in this workflow places an order" in workflows
    assert "research://postgres/backtest_run/{run_id}" in workflows
    for tool_name in required_tools:
        assert tool_name in workflows


def test_active_operator_docs_do_not_advertise_retired_research_clis() -> None:
    active_paths = (REPO_ROOT / "README.md", *(REPO_ROOT / "docs" / "core").rglob("*.md"))
    retired_commands = (
        "run_compare_results.py",
        "run_prepare_paper_promotion.py",
        "run_research_discovery.py",
        "run_research_experiment.py",
        "run_research_recommendations.py",
    )

    for path in active_paths:
        content = path.read_text(encoding="utf-8")
        for command in retired_commands:
            assert command not in content, f"{command} found in {path.relative_to(REPO_ROOT)}"


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
    product_state = PRODUCT_STATE_PATH.read_text(encoding="utf-8")
    roadmap = ROADMAP_PATH.read_text(encoding="utf-8")

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
        "57O Restart, Resume, Fault, And Deadline Qualification",
        "57P Provider Independence Qualification",
        "57Q Policy, Security, And Resource Boundaries",
        "57R Projection, Operator, And Bounded-Scale Qualification",
        "57S Acceptance Record",
        "verification_control.acceptance_records",
        "not_qualified",
    )
    for phrase in required_phrases:
        assert phrase in normalized_operations

    assert "## Qualification Baselines" in product_state
    assert "`verification-57i-freeze-v6`" in product_state
    assert "`verification_control.acceptance_records`" in product_state
    assert "| 57I-S | Frozen Postgres/MCP qualification and acceptance |" in roadmap

    contracts = " ".join(
        (DOC_ROOT / "tool_contracts.md").read_text(encoding="utf-8").split()
    )
    for phrase in (
        "Dependency declarations are descriptive",
        "deadline-capable executor",
        "fresh child process",
        "not a claim that arbitrary Python is an operating-system security sandbox",
    ):
        assert phrase in contracts


def test_product_state_separates_implementation_qualification_and_availability() -> None:
    product_state = PRODUCT_STATE_PATH.read_text(encoding="utf-8")

    for heading in (
        "## How To Read Capability State",
        "## Executive State",
        "## Capability Matrix",
        "## Agent State",
        "## Target Orchestration Position",
        "## Qualification Baselines",
        "## Known Product Limits",
    ):
        assert heading in product_state

    for phrase in (
        "`absent`, `partial`, `implemented`",
        "`none`, `focused`, `integration`, `controlled`",
        "`unregistered`, `registered`, `gated`, `operator_only`, `deferred`",
        "`Implemented` does not mean autonomously orchestrated",
        "The principal product gap is orchestration",
        "commit `577c774`",
        "but they are not part of the",
    ):
        assert phrase in product_state


def test_docs_define_cross_cutting_target_artifact_orchestration() -> None:
    architecture = " ".join(
        (DOC_ROOT / "architecture.md").read_text(encoding="utf-8").split()
    )
    agents = (DOC_ROOT / "agents.md").read_text(encoding="utf-8")

    for phrase in (
        "Higher-Level Orchestration Architecture",
        "Orchestration is a cross-cutting control capability",
        "does not call the registered implementation",
        "`ResearchObjective`",
        "`CapabilityDefinition`",
        "`WorkflowPlan`",
        "`WorkflowStepResult`",
        "`WorkflowOutcome`",
        "Planning is target-artifact driven",
        "Operational graph state and product evidence have separate authority",
        "Trader should not build one graph containing every possible research activity",
        "does not require rewriting a universal state machine",
    ):
        assert phrase in architecture

    assert "Ownership definitions do not imply that every named agent has an operational graph" in agents
    assert "(product_state.md#agent-state)" in agents
    assert "(../../plans/research_capability_roadmap.md#target-agent-capability-map)" in agents


def test_docs_define_non_overlapping_experiment_research_decisions() -> None:
    product_state = PRODUCT_STATE_PATH.read_text(encoding="utf-8")
    architecture = (DOC_ROOT / "architecture.md").read_text(encoding="utf-8")
    agents = (DOC_ROOT / "agents.md").read_text(encoding="utf-8")
    catalog = (DOC_ROOT / "mcp_tools.md").read_text(encoding="utf-8")
    workflows = (DOC_ROOT / "workflows.md").read_text(encoding="utf-8")
    roadmap = ROADMAP_PATH.read_text(encoding="utf-8")
    combined = "\n".join((product_state, architecture, agents, workflows))

    for role in (
        "Research Coordinator",
        "Data Agent",
        "Experiment Design Agent",
        "Robustness Agent",
        "Evaluation Agent",
        "Quantitative Methods Agent",
        "ML Agent",
    ):
        assert role in combined

    for phrase in (
        "Agents own bounded decisions. Domain contexts own canonical artifacts.",
        "`ExperimentProtocol`",
        "The experiment protocol is a proposal until material assumptions are explicitly approved",
        "The workflow executor is not an agent",
        "Robustness findings feed Evaluation",
        "`domain_owner`",
        "`producer_tool`",
        "`requested_by`",
        "`actor`",
        "No Backtest Agent, Optimisation Agent, Strategy Agent or Risk Agent is required",
    ):
        assert phrase in combined

    assert "| ORCH-GOV | Decision authority and domain ownership redesign | complete |" in roadmap
    assert "| ORCH-1 | Capability and workflow contracts | complete | ORCH-GOV |" in roadmap
    assert "| ORCH-2 | Operational checkpoint and handoff model | complete | ORCH-1 |" in roadmap
    assert "| ORCH-3 | Deterministic implementation-to-evidence workflow | ready |" in roadmap
    assert "| AGENT-1 | Specialist graph contract and common policy shell | ready | ORCH-1 |" in roadmap
    assert "The workflow executor owns no research claim and is not an agent" in roadmap
    assert "Owner labels in this catalog describe executable tool allowlists/stewardship only" in catalog
    assert "## Target Orchestrated Supplied-Strategy Workflow" in workflows


def test_docs_define_orch_1_contract_scope_without_claiming_execution() -> None:
    product_state = PRODUCT_STATE_PATH.read_text(encoding="utf-8")
    architecture = (DOC_ROOT / "architecture.md").read_text(encoding="utf-8")
    contracts = (DOC_ROOT / "tool_contracts.md").read_text(encoding="utf-8")
    workflows = (DOC_ROOT / "workflows.md").read_text(encoding="utf-8")
    operations = (DOC_ROOT / "operations.md").read_text(encoding="utf-8")
    combined = "\n".join(
        (product_state, architecture, contracts, workflows, operations)
    )

    for phrase in (
        "`ResearchObjective`",
        "`ExperimentProtocol`",
        "`CapabilityDefinition`",
        "`Prerequisite`",
        "`ArtifactSlot`",
        "`WorkflowPlan`",
        "`WorkflowStepResult`",
        "`Approval`",
        "sealed holdout",
        "dependency cycles",
        "ORCH-1 adds no MCP tools",
        "contract-only release",
        "No current MCP command accepts a `WorkflowPlan`",
    ):
        assert phrase in combined


def test_docs_define_orch_2_resume_without_claiming_mcp_execution() -> None:
    product_state = PRODUCT_STATE_PATH.read_text(encoding="utf-8")
    architecture = (DOC_ROOT / "architecture.md").read_text(encoding="utf-8")
    contracts = (DOC_ROOT / "tool_contracts.md").read_text(encoding="utf-8")
    workflows = (DOC_ROOT / "workflows.md").read_text(encoding="utf-8")
    operations = (DOC_ROOT / "operations.md").read_text(encoding="utf-8")
    roadmap = ROADMAP_PATH.read_text(encoding="utf-8")
    combined = "\n".join(
        (
            product_state,
            architecture,
            contracts,
            workflows,
            operations,
            roadmap,
        )
    )

    for phrase in (
        "`TRADER_AGENTS_CHECKPOINT_DSN`",
        "maintained Postgres LangGraph saver",
        "replaceable operational state",
        "Exact duplicate",
        "plan drift",
        "does not call MCP",
        "ORCH-3",
    ):
        assert phrase in combined

    assert (
        "| ORCH-2 | Operational checkpoint and handoff model | complete |"
        in roadmap
    )


def test_active_roadmap_is_dependency_driven_and_legacy_tracker_is_deprecated() -> None:
    roadmap = ROADMAP_PATH.read_text(encoding="utf-8")
    legacy = LEGACY_TRACKER_PATH.read_text(encoding="utf-8")

    for heading in (
        "## Capability Dependency Graph",
        "## Accepted Baseline",
        "## Active Work Graph",
        "## Current Ready Queue",
        "## Target Agent Capability Map",
        "## Historical Lineage Index",
    ):
        assert heading in roadmap

    assert "This is a choice of parallel frontiers" in roadmap
    assert "Orchestration is a cross-cutting capability" in roadmap
    assert "Status: deprecated on 2026-07-25" in legacy
    assert "Do not add tasks" in legacy
    assert "git show 577c774:plans/mcp_trading_research_tools_plan.md" in legacy
    assert "## Incremental Build Slices" not in legacy
    assert len(legacy.splitlines()) < 60


def test_active_roadmap_dependencies_reference_known_nodes_and_are_acyclic() -> None:
    roadmap = ROADMAP_PATH.read_text(encoding="utf-8")
    node_pattern = re.compile(
        r"^(?:BASE|ORCH|ML|QUAL|ROB|REV|REC|WFO|AGENT|DATA|KNOW|RUNNER|PERF)-[A-Z0-9-]+$"
    )
    status_values = {"ready", "in_progress", "blocked", "deferred", "complete"}
    rows: list[list[str]] = []
    node_ids: set[str] = set()

    for line in roadmap.splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if cells and node_pattern.fullmatch(cells[0]):
            node_ids.add(cells[0])
            rows.append(cells)

    assert {
        "BASE-EXP",
        "BASE-OPT",
        "BASE-ML-RUNTIME",
        "ORCH-GOV",
        "ORCH-1",
        "ML-1",
        "ROB-1",
    } <= node_ids

    dependencies: dict[str, set[str]] = {node_id: set() for node_id in node_ids}
    for cells in rows:
        if len(cells) < 4 or cells[2] not in status_values:
            continue
        for dependency in cells[3].split(","):
            dependency_id = dependency.strip()
            if dependency_id == "None":
                continue
            assert node_pattern.fullmatch(dependency_id), (cells[0], dependency_id)
            assert dependency_id in node_ids, (cells[0], dependency_id)
            dependencies[cells[0]].add(dependency_id)

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node_id: str) -> None:
        if node_id in visited:
            return
        assert node_id not in visiting, f"roadmap dependency cycle at {node_id}"
        visiting.add(node_id)
        for dependency_id in dependencies[node_id]:
            visit(dependency_id)
        visiting.remove(node_id)
        visited.add(node_id)

    for node_id in sorted(node_ids):
        visit(node_id)


def test_docs_define_57j_isolated_postgres_runtime() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    operations = (DOC_ROOT / "operations.md").read_text(encoding="utf-8")
    product_state = PRODUCT_STATE_PATH.read_text(encoding="utf-8")
    combined = "\n".join((readme, operations, product_state))
    normalized_readme = " ".join(readme.split())

    required_phrases = (
        "PG_TEST_HOST",
        "PG_OPERATOR_HOST",
        "PG_OPTUNA_TEST_HOST",
        "PG_TEST_LOCALE",
        "verification_control.runtime_marker",
        "verification_control.operator_fingerprints",
        "tests.support.postgres_verification provision --reset",
        "immediately before each `TRUNCATE`",
        "byte-identical to `verification-57i-freeze-v6`",
        "isolation_status",
        "qualification_status",
        "--outcome passed",
    )
    for phrase in required_phrases:
        assert phrase in combined

    assert "They never read the legacy/operator `PG_HOST`" in normalized_readme
    assert "Product rows," in operations
    assert "passwords" in operations


def test_docs_define_57l_as_postgres_only_direct_service_qualification() -> None:
    operations = (DOC_ROOT / "operations.md").read_text(encoding="utf-8")
    product_state = PRODUCT_STATE_PATH.read_text(encoding="utf-8")
    combined = "\n".join((operations, product_state))

    required_phrases = (
        "57L Postgres-Only Fixture Qualification",
        "PostgresEventStore",
        "PostgresResearchArtifactStore",
        "does not use DuckDB",
        "48 hourly selection",
        "32 hourly holdout",
        "lookbacks 2, 3, 4, and 5",
        "source_filter=null",
        "tests/test_postgres_realistic_optimization_fixture.py",
        "57M separately proves MCP registration",
    )
    for phrase in required_phrases:
        assert phrase in combined

    assert "`verification-57i-freeze-v6`" in product_state


def test_docs_define_57m_as_retained_postgres_stdio_mcp_evidence() -> None:
    operations = (DOC_ROOT / "operations.md").read_text(encoding="utf-8")
    product_state = PRODUCT_STATE_PATH.read_text(encoding="utf-8")
    combined = "\n".join((operations, product_state))
    normalized = " ".join(combined.split())

    required_phrases = (
        "57M Stdio MCP Evidence Graph",
        "actual MCP `ClientSession` over stdio",
        "TRADER_VERIFICATION_RETAIN_PHASE=57M",
        "exactly `TRADER_MCP_ALLOW_BACKTESTS=true`",
        "research_parameter_optimization_trials",
        "service executes the declared seed variant",
        "tests/test_postgres_optimization_evidence_graph.py",
        "no canonical filesystem path may be present",
    )
    for phrase in required_phrases:
        assert phrase in normalized

    assert "`verification_control.acceptance_records`" in product_state


def test_docs_define_57n_determinism_integrity_and_leakage_controls() -> None:
    architecture = (DOC_ROOT / "architecture.md").read_text(encoding="utf-8")
    contracts = (DOC_ROOT / "tool_contracts.md").read_text(encoding="utf-8")
    operations = (DOC_ROOT / "operations.md").read_text(encoding="utf-8")
    product_state = PRODUCT_STATE_PATH.read_text(encoding="utf-8")
    combined = "\n".join((architecture, contracts, operations, product_state))
    normalized = " ".join(combined.split())

    required_phrases = (
        "57N Determinism, Integrity, And Holdout Leakage",
        "tests/test_postgres_optimization_determinism_integrity.py",
        "TRADER_VERIFICATION_RETAIN_PHASE=57N",
        "verification_control.determinism_snapshots",
        "verification_control.integrity_checks",
        "verification_control.data_access_log",
        "verification_control.selection_seals",
        "finished_at",
        "duration_seconds",
        "complete trial ledger",
        "Each public MCP consumer must fail closed",
    )
    for phrase in required_phrases:
        assert phrase in normalized

    assert "`verification-57i-freeze-v6`" in product_state


def test_docs_define_mlflow_lifecycle_and_implemented_runtime_boundary() -> None:
    architecture = (DOC_ROOT / "architecture.md").read_text(encoding="utf-8")
    agents = (DOC_ROOT / "agents.md").read_text(encoding="utf-8")
    catalog = (DOC_ROOT / "mcp_tools.md").read_text(encoding="utf-8")
    contracts = (DOC_ROOT / "tool_contracts.md").read_text(encoding="utf-8")
    workflows = (DOC_ROOT / "workflows.md").read_text(encoding="utf-8")
    product_state = PRODUCT_STATE_PATH.read_text(encoding="utf-8")
    roadmap = ROADMAP_PATH.read_text(encoding="utf-8")

    assert "## ML Lifecycle Architecture" in architecture
    assert "MLflow is authoritative for" in architecture
    assert "Random train/test splitting must not be the default" in architecture
    assert "must never change model behavior merely because an MLflow alias was reassigned" in architecture
    assert "The trading hot path must not call MCP" in architecture
    assert "### Implemented Runtime Slice" in architecture
    assert "## ML Lifecycle Decision Boundary" in agents
    assert "## ML Agent Tools" in catalog
    assert "## Remaining Planned MLflow Tool Universe" in catalog
    assert "`ml_create_deployment_manifest`" in catalog
    assert "`ml_validate_deployment`" in catalog
    assert "external_research_mutating" in contracts
    assert "### Runtime Prediction And Deployment Contracts" in contracts
    assert "## MLflow Model Lifecycle And Runtime Integration" in workflows
    assert "| ML-1 | MLflow runtime and mutation policy | ready | BASE-OPT |" in roadmap
    assert "| ML-7 | Prediction monitoring and drift | ready | BASE-ML-RUNTIME |" in roadmap
    assert "| ML Agent | Ownership and deployment MCP tools exist; no ML Agent graph exists." in product_state


def test_docs_defer_walk_forward_optimization_but_keep_validation_foundational() -> None:
    product_state = PRODUCT_STATE_PATH.read_text(encoding="utf-8")
    architecture = (DOC_ROOT / "architecture.md").read_text(encoding="utf-8")
    agents = (DOC_ROOT / "agents.md").read_text(encoding="utf-8")
    catalog = (DOC_ROOT / "mcp_tools.md").read_text(encoding="utf-8")
    contracts = (DOC_ROOT / "tool_contracts.md").read_text(encoding="utf-8")
    workflows = (DOC_ROOT / "workflows.md").read_text(encoding="utf-8")
    roadmap = ROADMAP_PATH.read_text(encoding="utf-8")

    assert "| Walk-forward optimisation | absent | none | deferred |" in product_state
    assert "## Walk-Forward Validation And Optimisation" in architecture
    assert "Chronological walk-forward validation is foundational model-fitting correctness" in architecture
    assert "## Optimisation And Walk-Forward Decisions" in agents
    assert "## Deferred Walk-Forward Tool Universe" in catalog
    assert "### Deferred Walk-Forward Contract Invariants" in contracts
    assert "## Deferred Walk-Forward Optimisation Workflow" in workflows
    assert "| WFO-1 | Strategy walk-forward core | blocked | BASE-OPT, ROB-1 |" in roadmap
    assert "| WFO-2 | Stitched OOS Evaluation and independent audit | blocked | WFO-1, ROB-2 |" in roadmap


def _current_markdown_docs() -> tuple[Path, ...]:
    return tuple(
        sorted(
            path
            for path in DOC_ROOT.glob("*.md")
            if "history" not in path.relative_to(DOC_ROOT).parts
        )
    )
