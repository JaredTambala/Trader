"""Contracts for active research capability documentation.

Subject: Canonical package, tool, data, methodology, experiment, MLflow, and product-state claims.
Level: Cross-package documentation contract.
Collaborators: Real package docs, registered tool/agent definitions, roadmap, and historical pages.
Guarantees: Active capability claims, paths, ownership, and lifecycle status remain accurate.
Non-goals: Executing tools, qualifying providers, or scoring prose style.
"""

import re

from trader_mcp.catalogue.definitions import REGISTERED_TOOL_NAMES
from trader_research.governance.ownership import AGENT_DEFINITIONS

from tests.cross_package.documentation.research_doc_support import (
    DOC_ROOT,
    LEGACY_TRACKER_PATH,
    PACKAGE_ROOTS,
    PRODUCT_STATE_PATH,
    REPO_ROOT,
    ROADMAP_PATH,
    STALE_CURRENT_CLAIMS,
    _current_markdown_docs,
    _read_doc,
)


def test_package_readmes_link_canonical_docs_and_history_is_retained() -> None:
    """Require package learning indexes while retaining historical research documentation."""
    for package_root in PACKAGE_ROOTS:
        readme = (package_root / 'README.md').read_text(encoding='utf-8')
        for filename in ('architecture.md', 'tutorial.md', 'usage.md'):
            assert (package_root / 'docs' / filename).exists()
            assert f'docs/{filename}' in readme
    assert (DOC_ROOT / 'history' / 'research_agents').is_dir()


def test_registered_mcp_tools_are_documented_once_in_canonical_catalog() -> None:
    """Keep every registered MCP tool documented once in its canonical catalogue."""
    catalog = _read_doc('mcp_tools.md')
    for tool_name in REGISTERED_TOOL_NAMES:
        assert catalog.count(f'`{tool_name}`') == 1, tool_name


def test_agent_identities_are_documented_in_canonical_agent_doc() -> None:
    """Keep every registered agent identity visible in canonical role documentation."""
    agents_doc = _read_doc('agents.md')
    for definition in AGENT_DEFINITIONS:
        assert definition.display_name in agents_doc


def test_current_research_agent_docs_do_not_carry_stale_tool_claims() -> None:
    """Reject stale capability claims from active research and Agent documentation."""
    for path in _current_markdown_docs():
        content = path.read_text(encoding='utf-8')
        for stale_claim in STALE_CURRENT_CLAIMS:
            assert stale_claim not in content, f'{stale_claim!r} found in {path.relative_to(REPO_ROOT)}'


def test_rich_methodology_operator_guide_covers_required_workflows() -> None:
    """Require methodology guidance for ingestion, evidence, validation, and publishing workflows."""
    workflows = _read_doc('workflows.md')
    operations = _read_doc('operations.md')
    contracts = _read_doc('tool_contracts.md')
    combined = '\n'.join((workflows, operations, contracts)).lower()
    required_phrases = ('registration and ingestion are deliberately separate', 'full-document ingestion', 'field-level source/chunk/claim-span refs', 'draft cards are still review artifacts', 'source suitability matters', 'pairs trading or cointegration', 'options straddle', 'technical indicator', 'commodity sentiment indicator', 'data agent scope')
    for phrase in required_phrases:
        assert phrase in combined


def test_research_package_readme_links_resolve() -> None:
    """Keep research package README links anchored to existing owned documents."""
    readme_path = REPO_ROOT / 'src' / 'trader_research' / 'README.md'
    readme = readme_path.read_text(encoding='utf-8')
    for target in re.findall('\\]\\(([^)]+)\\)', readme):
        if target.startswith(('http://', 'https://', '#')):
            continue
        path_target, _, _ = target.partition('#')
        assert (readme_path.parent / path_target).exists(), target


def test_product_state_and_roadmap_links_resolve() -> None:
    """Keep active product-state and roadmap links resolvable within the repository."""
    for source_path in (PRODUCT_STATE_PATH, ROADMAP_PATH, LEGACY_TRACKER_PATH):
        content = source_path.read_text(encoding='utf-8')
        for target in re.findall('\\]\\(([^)]+)\\)', content):
            if target.startswith(('http://', 'https://', '#')):
                continue
            path_target, _, _ = target.partition('#')
            assert (source_path.parent / path_target).exists(), (source_path.relative_to(REPO_ROOT), target)


def test_semantic_extraction_doc_is_canonical_and_preserves_overlap_invariant() -> None:
    """Preserve one canonical semantic-extraction guide and its overlap invariant."""
    semantic_doc = _read_doc('semantic_extraction.md')
    required_phrases = ('Evidence units are non-exclusive', 'addressable claim span', 'target-conditioned claim-span selection', 'bounded multi-span field synthesis', 'Another method appearing elsewhere in a cited evidence unit is not a blocker', 'no maintained method-target registry')
    for phrase in required_phrases:
        assert phrase in semantic_doc
    linked_docs = (REPO_ROOT / 'src' / 'trader_research' / 'README.md', ROADMAP_PATH, REPO_ROOT / 'src' / 'trader_mcp' / 'docs' / 'contracts.md', DOC_ROOT / 'workflows' / 'research.md')
    for path in linked_docs:
        content = path.read_text(encoding='utf-8')
        assert 'knowledge.md' in content


def test_docs_pin_knowledge_baseline_and_identify_next_delivery_focus() -> None:
    """Require documentation to distinguish the knowledge baseline from future work."""
    product_state = _read_doc('product_state.md')
    semantic_doc = _read_doc('semantic_extraction.md')
    contracts = _read_doc('tool_contracts.md')
    workflows = _read_doc('workflows.md')
    roadmap = ROADMAP_PATH.read_text(encoding='utf-8')
    assert '| Methodology extraction and method cards | implemented | integration |' in product_state
    assert 'The implemented bounded methodology subsystem supports' in semantic_doc
    assert 'execution begins with content-addressed implementation versions' in contracts
    assert 'Handwritten code and AI-produced code' in workflows
    assert '| KNOW-1 | Composite methodology representation | deferred | BASE-KNOW |' in roadmap
    assert '| BASE-IMPL | Knowledge-independent implementation admission through 56A-D |' in roadmap
    assert '| BASE-EXP | Strategy, risk-stack and backtest specifications through 57A-C |' in roadmap
    assert '| BASE-OPT | Provider-neutral optimisation and independent review through 57D-H |' in roadmap
    assert 'Knowledge provenance is optional' not in roadmap
    assert 'KNOWLEDGE ── optional provenance' in roadmap


def test_docs_define_current_research_architecture_and_refactor_lineage() -> None:
    """Keep current research topology and historical refactor lineage explicitly documented."""
    readme = _read_doc('README.md')
    architecture = _read_doc('architecture.md')
    product_state = _read_doc('product_state.md')
    roadmap = ROADMAP_PATH.read_text(encoding='utf-8')
    required_readme_phrases = ('deterministic research capability layer', '## Bounded contexts', '## Learning path', 'canonical', 'data readiness', 'experiment specifications and execution', 'adversarial review')
    for phrase in required_readme_phrases:
        assert phrase in readme
    required_architecture_phrases = ('# Research Capability Architecture', '## Context map', '## Application boundary', 'Public context functions return `ApplicationResult`', 'Contexts exchange stable artifact references', 'trader_mcp -> public context facades', 'Provider SDK payloads are normalized', 'Artifact domain ownership is distinct', 'append-only', 'Docker, provider network calls', 'Add capability to the owning context', 'do not import the new service from agent code')
    for phrase in required_architecture_phrases:
        assert phrase in architecture
    historical_architecture_phrases = ('## `trader_research` Refactor Review And Plan', '### Review Scope And Baseline', '### Baseline Findings', '### Staged Hard Cutover', 'Production refactoring starts at TRR-5 only', 'The refactor will establish')
    for phrase in historical_architecture_phrases:
        assert phrase not in architecture
    assert '| BASE-ARCH | `trader_research` bounded-context cutover through TRR-12 |' in roadmap
    assert '| 53-54 and TRR-1 through TRR-12 |' in roadmap
    assert '`verification-57i-freeze-v6`' in product_state
    assert 'Current operational state' in product_state
    assert 'Target state' in product_state


def test_active_docs_reference_current_research_source_paths() -> None:
    """Reject removed research source paths from every active documentation page."""
    current_docs = '\n'.join((path.read_text(encoding='utf-8') for path in _current_markdown_docs()))
    stale_paths = ('src/trader_research/agents.py', 'src/trader_research/domain.py', 'src/trader_research/artifact_store.py', 'src/trader_research/postgres_artifact_store.py')
    assert 'src/trader_research/governance/ownership.py' in current_docs
    assert 'src/trader_research/governance/artifacts.py' in current_docs
    for stale_path in stale_paths:
        assert stale_path not in current_docs


def test_docs_walk_supplied_implementations_to_bounded_evidence() -> None:
    """Require a documented path from supplied implementations to bounded evidence."""
    workflows = _read_doc('workflows.md')
    required_tools = ('research_register_strategy_implementation', 'research_validate_strategy_implementation', 'research_create_strategy_specification', 'research_create_risk_stack_specification', 'research_create_backtest_specification', 'research_run_backtest_specification', 'research_get_backtest_results', 'evaluation_generate_parameter_optimization_report', 'adversarial_create_parameter_optimization_audit_plan', 'adversarial_generate_parameter_optimization_audit')
    assert '## Worked Implementation-To-Evidence Walkthrough' in workflows
    assert 'A method card is not required' in workflows
    assert 'What it does not prove' in workflows
    assert 'No stage in this workflow places an order' in workflows
    assert 'research://postgres/backtest_run/{run_id}' in workflows
    for tool_name in required_tools:
        assert tool_name in workflows


def test_active_operator_docs_do_not_advertise_retired_research_clis() -> None:
    """Prevent active operator guidance from advertising retired research commands."""
    active_paths = (REPO_ROOT / 'README.md', *(REPO_ROOT / 'src' / 'trader' / 'docs').rglob('*.md'))
    retired_commands = ('run_compare_results.py', 'run_prepare_paper_promotion.py', 'run_research_discovery.py', 'run_research_experiment.py', 'run_research_recommendations.py')
    for path in active_paths:
        content = path.read_text(encoding='utf-8')
        for command in retired_commands:
            assert command not in content, f'{command} found in {path.relative_to(REPO_ROOT)}'


def test_docs_define_provider_neutral_optimization_and_independent_review() -> None:
    """Require provider-neutral optimization and independently owned review in documentation."""
    architecture = _read_doc('architecture.md')
    agents = _read_doc('agents.md')
    catalog = _read_doc('mcp_tools.md')
    contracts = _read_doc('tool_contracts.md')
    operations = _read_doc('operations.md')
    workflows = _read_doc('workflows.md')
    combined = '\n'.join((architecture, agents, catalog, contracts, operations, workflows))
    required_phrases = ('OptimizationEngine', 'OptimizationTrialExecutor', 'ExperimentTrackingSink', 'research_create_parameter_optimization_plan', 'research_project_experiment_tracking', 'TRADER_MCP_ALLOW_OPTIMIZATION', 'TRADER_MCP_ALLOW_OPTUNA_WRITES', 'dedicated non-`public` schema', 'non-authoritative', 'sealed holdout', 'Adversarial')
    for phrase in required_phrases:
        assert phrase in combined
    assert 'MLflow is authoritative for ML training telemetry' in architecture
    assert 'Trader never queries that' in architecture
    assert 'ml_list_experiments' not in combined
    assert 'ml_list_training_experiments' in combined


def test_product_state_separates_implementation_qualification_and_availability() -> None:
    """Keep implemented, qualified, and operator-available states distinct in product documentation."""
    product_state = _read_doc('product_state.md')
    for heading in ('## How To Read Capability State', '## Executive State', '## Capability Matrix', '## Agent State', '## Target Orchestration Position', '## Qualification Baselines', '## Known Product Limits'):
        assert heading in product_state
    for phrase in ('`absent`, `partial`, `implemented`', '`none`, `focused`, `integration`, `controlled`', '`unregistered`, `registered`, `gated`, `operator_only`, `deferred`', '`Implemented` does not mean autonomously orchestrated', 'implemented but unqualified first model-backed orchestration slice', 'commit `577c774`', 'but they are not part of the'):
        assert phrase in product_state


def test_docs_define_mlflow_lifecycle_and_implemented_runtime_boundary() -> None:
    """Document MLflow lifecycle ownership and the currently implemented runtime boundary."""
    architecture = _read_doc('architecture.md')
    agents = _read_doc('agents.md')
    catalog = _read_doc('mcp_tools.md')
    contracts = _read_doc('tool_contracts.md')
    workflows = _read_doc('workflows.md')
    product_state = _read_doc('product_state.md')
    roadmap = ROADMAP_PATH.read_text(encoding='utf-8')
    assert '## ML Lifecycle Architecture' in architecture
    assert 'MLflow is authoritative for' in architecture
    assert 'Random train/test splitting must not be the default' in architecture
    assert 'must never change model behavior merely because an MLflow alias was reassigned' in architecture
    assert 'The trading hot path must not call MCP' in architecture
    assert '### Implemented Runtime Slice' in architecture
    assert '## ML Lifecycle Decision Boundary' in agents
    assert '## ML Agent Tools' in catalog
    assert '## Remaining Planned MLflow Tool Universe' in catalog
    assert '`ml_create_deployment_manifest`' in catalog
    assert '`ml_validate_deployment`' in catalog
    assert 'external_research_mutating' in contracts
    assert '### Runtime Prediction And Deployment Contracts' in contracts
    assert '## MLflow Model Lifecycle And Runtime Integration' in workflows
    assert '| ML-1 | MLflow runtime and mutation policy | ready | BASE-OPT |' in roadmap
    assert '| ML-7 | Prediction monitoring and drift | ready | BASE-ML-RUNTIME |' in roadmap
    assert '| ML Agent | Ownership and deployment MCP tools exist; no ML Agent graph exists.' in product_state


def test_docs_defer_walk_forward_optimization_but_keep_validation_foundational() -> None:
    """Keep walk-forward work deferred while preserving its prerequisite validation contracts."""
    product_state = _read_doc('product_state.md')
    architecture = _read_doc('architecture.md')
    agents = _read_doc('agents.md')
    catalog = _read_doc('mcp_tools.md')
    contracts = _read_doc('tool_contracts.md')
    workflows = _read_doc('workflows.md')
    roadmap = ROADMAP_PATH.read_text(encoding='utf-8')
    assert '| Walk-forward optimisation | absent | none | deferred |' in product_state
    assert '## Walk-Forward Validation And Optimisation' in architecture
    assert 'Chronological walk-forward validation is foundational model-fitting correctness' in architecture
    assert '## Optimisation And Walk-Forward Decisions' in agents
    assert '## Deferred Walk-Forward Tool Universe' in catalog
    assert '### Deferred Walk-Forward Contract Invariants' in contracts
    assert '## Deferred Walk-Forward Optimisation Workflow' in workflows
    assert '| WFO-1 | Strategy walk-forward core | blocked | BASE-OPT, ROB-1 |' in roadmap
    assert '| WFO-2 | Stitched OOS Evaluation and independent audit | blocked | WFO-1, ROB-2 |' in roadmap
