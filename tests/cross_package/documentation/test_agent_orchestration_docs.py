"""Contracts for model-backed orchestration documentation.

Subject: Coordinator, specialist, approval, execution, checkpoint, and state-authority explanations.
Level: Cross-package documentation contract.
Collaborators: Canonical Agent, MCP, product-state, workflow, and roadmap documents.
Guarantees: Documentation matches implemented orchestration boundaries without overstating capability.
Non-goals: Running agents, judging model quality, or proving persistence recovery.
"""

from tests.cross_package.documentation.research_doc_support import (
    ROADMAP_PATH,
    _read_doc,
)


def test_docs_define_cross_cutting_agent_orchestration() -> None:
    """Require documentation to explain orchestration across bounded specialist contexts."""
    architecture = ' '.join(_read_doc('architecture.md').split())
    agents = _read_doc('agents.md')
    for phrase in ('# Multi-Agent Architecture', '## What constitutes an agent', '## Coordinator graph', '## Specialist graphs', '## Parallelism and joins', '## Trust transitions', '`AgentCheckpointState`', '`SpecialistCheckpointState`', 'The Coordinator remains the single writer', 'Models decide interpretations and next actions', 'An agent checkpoint is not research evidence'):
        assert phrase in architecture
    assert 'Ownership definitions do not imply that every named agent has an operational graph' in agents
    assert 'Product State' in agents
    assert 'Trader Development Roadmap' in agents
    assert 'https://app.notion.com/p/d1453b7a4da6468babead2a5cda7ef84' in agents


def test_docs_define_non_overlapping_experiment_research_decisions() -> None:
    """Keep Experiment, Robustness, Evaluation, and Coordinator decisions explicitly non-overlapping."""
    product_state = _read_doc('product_state.md')
    architecture = _read_doc('architecture.md')
    agents = _read_doc('agents.md')
    catalog = _read_doc('mcp_tools.md')
    workflows = _read_doc('workflows.md')
    roadmap = ROADMAP_PATH.read_text(encoding='utf-8')
    combined = '\n'.join((product_state, architecture, agents, workflows))
    for role in ('Research Coordinator', 'Data Agent', 'Experiment Design Agent', 'Robustness Agent', 'Evaluation Agent', 'Quantitative Methods Agent', 'ML Agent'):
        assert role in combined
    for phrase in ('Agents own bounded decisions. Domain contexts own canonical artifacts.', '`ExperimentProtocol`', 'The canonical proposal remains immutable while material assumptions are decided', 'A deterministic execution service is not an agent', 'Robustness findings feed Evaluation', '`domain_owner`', '`producer_tool`', '`requested_by`', '`actor`', 'Backtest execution, optimisation scheduling, and risk evaluation do not become agents'):
        assert phrase in combined
    assert '| ORCH-GOV | Decision authority and domain ownership redesign | complete |' in roadmap
    assert '| ORCH-1 | Capability and workflow contracts | complete | ORCH-GOV |' in roadmap
    assert '| ORCH-2 | Operational checkpoint and handoff model | complete | ORCH-1 |' in roadmap
    assert '| ORCH-3 | Deterministic implementation-to-evidence workflow | complete |' in roadmap
    assert '| AGENT-1 | Specialist graph contract and common policy shell | complete | ORCH-1 |' in roadmap
    assert 'The workflow executor owns no research claim and is not an agent' in roadmap
    assert 'Owner labels in this catalog describe executable tool allowlists/stewardship only' in catalog
    assert '## Target Orchestrated Supplied-Strategy Workflow' in workflows


def test_docs_define_shared_specialist_boundary_and_bounded_composition() -> None:
    """Require shared specialist contracts and bounded composition behavior in Agent documentation."""
    product_state = _read_doc('product_state.md')
    architecture = _read_doc('architecture.md')
    agents = _read_doc('agents.md')
    contracts = _read_doc('tool_contracts.md')
    workflows = _read_doc('workflows.md')
    roadmap = ROADMAP_PATH.read_text(encoding='utf-8')
    combined = '\n'.join((product_state, architecture, agents, contracts, workflows, roadmap))
    for phrase in ('`SpecialistTask`', '`SpecialistDecision`', '`SpecialistActionCatalog`', '`SpecialistActionOutcome`', '`SpecialistResult`', '`SpecialistRouteCatalog`', '`ResearchCompositionRequest`', '`AcceptedSpecialistResult`', 'canonical input URIs', 'registered action', 'permitted side effects', '`DataSpecialistRequest`', 'fresh-saver resumption without repeating accepted actions', 'Exact terminal replay'):
        assert phrase in combined
    assert '| AGENT-1 | Specialist graph contract and common policy shell | complete |' in roadmap
    assert '| AGENT-DATA | Integrate Data Agent as a resumable specialist | complete |' in roadmap
    assert '| ORCH-5 | Multi-specialist composition | complete |' in roadmap
    assert '| ORCH-6 | Controlled orchestration qualification | complete |' in roadmap
    assert '#### Implemented Research Composition' in roadmap
    assert '#### Controlled Orchestration Qualification Plan' in roadmap
    for phase in ('`ORCHESTRATION_RUNTIME`', '`ORCHESTRATION_CORE`', '`ORCHESTRATION_E2E`', '`ORCHESTRATION_RECOVERY`', '`ORCHESTRATION_POLICY`', '`ORCHESTRATION_SCALE`', '`ORCHESTRATION_ACCEPTANCE`'):
        assert phase in roadmap
    operations = _read_doc('operations.md')
    for phrase in ('### Controlled Orchestration Qualification', 'controlled_orchestration_v1', 'PG_CHECKPOINT_TEST_USER', 'verification_control.orchestration_call_ledger', 'verification_control.orchestration_acceptance_records'):
        assert phrase in operations
    assert '| AGENT-DESIGN | Experiment protocol proposal and specialist graph | complete |' in roadmap
    for phrase in ('#### Implemented Data Specialist Cutover', '#### Implemented Experiment Design Specialist', '`validate_market_data_scope`', '`ensure_market_data_available`', '`capture_market_data_evidence`', 'without compatibility aliases'):
        assert phrase in roadmap


def test_docs_explain_implemented_experiment_design_approval_boundary() -> None:
    """Document the implemented separation between protocol proposal and human approval."""
    combined = '\n'.join((_read_doc('product_state.md'), _read_doc('architecture.md'), _read_doc('agents.md'), _read_doc('mcp_tools.md'), _read_doc('tool_contracts.md'), _read_doc('workflows.md'), _read_doc('operations.md')))
    for phrase in ('`ExperimentDesignRequest`', '`ExperimentProtocolProposal`', '`research_create_experiment_protocol_proposal`', '`apply_experiment_protocol_approvals`', '`research_experiment_protocol_proposals`', 'Data and Experiment Design', 'immutable proposal', 'requested approvals', 'cannot approve'):
        assert phrase in combined


def test_docs_define_declaration_contract_scope_without_claiming_execution() -> None:
    """Keep declarative capability contracts distinct from executable runtime behavior."""
    product_state = _read_doc('product_state.md')
    architecture = _read_doc('architecture.md')
    contracts = _read_doc('tool_contracts.md')
    workflows = _read_doc('workflows.md')
    operations = _read_doc('operations.md')
    combined = '\n'.join((product_state, architecture, contracts, workflows, operations))
    for phrase in ('`ResearchObjective`', '`ExperimentProtocol`', '`CapabilityDefinition`', '`Prerequisite`', '`ArtifactSlot`', '`WorkflowPlan`', '`WorkflowStepResult`', '`Approval`', 'sealed holdout', 'dependency cycles', 'The declaration contracts are transport-neutral', 'declaration-contract delivery was contract-only'):
        assert phrase in combined


def test_docs_define_resume_shell_without_claiming_mcp_execution() -> None:
    """Document checkpoint resume semantics without attributing MCP execution to the shell."""
    product_state = _read_doc('product_state.md')
    architecture = _read_doc('architecture.md')
    agents = _read_doc('agents.md')
    contracts = _read_doc('tool_contracts.md')
    workflows = _read_doc('workflows.md')
    operations = _read_doc('operations.md')
    roadmap = ROADMAP_PATH.read_text(encoding='utf-8')
    combined = '\n'.join((product_state, architecture, agents, contracts, workflows, operations))
    for phrase in ('`TRADER_AGENTS_CHECKPOINT_DSN`', 'maintained Postgres LangGraph saver', 'replaceable operational state', 'Exact duplicate', 'plan drift', 'does not call MCP'):
        assert phrase in combined
    assert '| ORCH-2 | Operational checkpoint and handoff model | complete |' in roadmap


def test_docs_define_deterministic_execution_boundary() -> None:
    """Keep deterministic execution services distinct from model-backed Agent decisions."""
    product_state = _read_doc('product_state.md')
    architecture = _read_doc('architecture.md')
    agents = _read_doc('agents.md')
    catalog = _read_doc('mcp_tools.md')
    contracts = _read_doc('tool_contracts.md')
    workflows = _read_doc('workflows.md')
    operations = _read_doc('operations.md')
    roadmap = ROADMAP_PATH.read_text(encoding='utf-8')
    combined = '\n'.join((product_state, architecture, agents, catalog, contracts, workflows, operations, roadmap))
    for phrase in ('`supplied_implementation_to_evidence`', '`data_create_research_snapshot`', '`research_register_experiment_workflow`', '`research_record_workflow_outcome`', '`workflow_executor`', 'payload hash', 'without replaying accepted steps', 'not a generic high-level MCP', 'research_workflow_outcomes'):
        assert phrase in combined
    assert '| ORCH-3 | Deterministic implementation-to-evidence workflow | complete |' in roadmap
    assert '| ORCH-4 | Bounded Research Coordinator planning policy | complete |' in roadmap


def test_docs_explain_current_orchestration_call_and_storage_boundaries() -> None:
    """Require accurate call paths and state authorities for current orchestration."""
    readme = _read_doc('README.md')
    normalized_readme = ' '.join(readme.split())
    product_state = _read_doc('product_state.md')
    architecture = _read_doc('architecture.md')
    catalog = _read_doc('mcp_tools.md')
    contracts = _read_doc('tool_contracts.md')
    roadmap = ROADMAP_PATH.read_text(encoding='utf-8')
    for phrase in ('model-backed Coordinator agenda', 'structured specialist returns', 'canonical artifact reads and digest checks'):
        assert phrase in normalized_readme
    for phrase in ('## Implemented Orchestration At A Glance', 'The current first slice is a real model/tool control loop', 'append-only decision receipts', 'Checkpoints are operational and redacted'):
        assert phrase in product_state
    for phrase in ('The Research Coordinator is the only user-facing model', 'The Coordinator remains the single writer of shared graph state', 'PostgreSQL checkpoints contain bounded operational state only'):
        assert phrase in architecture
    assert 'Research Coordinator Evidence Tools' in catalog
    assert '`ToolEnvelope` | MCP adapter' in contracts
    assert '`AgentDecisionReceipt`' in contracts
    assert '| First agentic implementation slice | in_progress |' in roadmap


def test_docs_define_bounded_research_coordinator_policy() -> None:
    """Document Coordinator authority, evidence review, budgets, and fail-closed decisions."""
    product_state = _read_doc('product_state.md')
    architecture = _read_doc('architecture.md')
    agents = _read_doc('agents.md')
    workflows = _read_doc('workflows.md')
    operations = _read_doc('operations.md')
    roadmap = ROADMAP_PATH.read_text(encoding='utf-8')
    combined = '\n'.join((product_state, architecture, agents, workflows, operations, roadmap))
    for phrase in ('`CoordinatorAgenda`', '`SpecialistDelegation`', 'role-scoped MCP', 'append-only', 'single-writer', 'fail closed'):
        assert phrase in combined
    assert '`coordination/coordinator.py`' in architecture
    assert 'Every return rejoins the single-writer Coordinator' in agents
