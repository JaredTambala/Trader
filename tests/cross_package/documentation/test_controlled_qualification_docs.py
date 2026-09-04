"""Contracts for controlled research qualification documentation.

Subject: Verification profiles, stop conditions, and retained controlled-run evidence.
Level: Cross-package documentation contract.
Collaborators: Canonical product/workflow docs, roadmap, and historical qualification records.
Guarantees: Qualification claims retain their exact environment and evidence boundaries.
Non-goals: Running Postgres, MCP subprocesses, optimizers, or acceptance campaigns.
"""

from tests.cross_package.documentation.research_doc_support import (
    DOC_ROOT,
    REPO_ROOT,
    ROADMAP_PATH,
    _read_doc,
)


def test_docs_define_controlled_verification_profiles_and_stop_conditions() -> None:
    """Require controlled verification profiles, evidence, and stop conditions in documentation."""
    operations = _read_doc('operations.md')
    normalized_operations = ' '.join(operations.split())
    product_state = _read_doc('product_state.md')
    roadmap = ROADMAP_PATH.read_text(encoding='utf-8')
    required_phrases = ('one frozen Git revision', 'Core:', 'Trader Postgres:', 'Optuna:', 'Tracking sink:', 'fallback to `PG_DB`', 'stop condition', 'PostgresResearchArtifactStore', 'risk approvals and rejections', 'no canonical filesystem path', '57O Restart, Resume, Fault, And Deadline Qualification', '57P Provider Independence Qualification', '57Q Policy, Security, And Resource Boundaries', '57R Projection, Operator, And Bounded-Scale Qualification', '57S Acceptance Record', 'verification_control.acceptance_records', 'not_qualified')
    for phrase in required_phrases:
        assert phrase in normalized_operations
    assert '## Qualification Baselines' in product_state
    assert '`verification-57i-freeze-v6`' in product_state
    assert '`verification_control.acceptance_records`' in product_state
    assert '| 57I-S | Frozen Postgres/MCP qualification and acceptance |' in roadmap
    contracts = ' '.join(_read_doc('tool_contracts.md').split())
    for phrase in ('Dependency declarations are descriptive', 'deadline-capable executor', 'fresh child process', 'not a claim that arbitrary Python is an operating-system security sandbox'):
        assert phrase in contracts


def test_docs_define_57j_isolated_postgres_runtime() -> None:
    """Preserve the isolated Postgres runtime qualification contract in historical evidence."""
    readme = (REPO_ROOT / 'README.md').read_text(encoding='utf-8')
    environment = (DOC_ROOT / 'environment.md').read_text(encoding='utf-8')
    operations = _read_doc('operations.md')
    product_state = _read_doc('product_state.md')
    combined = '\n'.join((readme, environment, operations, product_state))
    normalized_environment = ' '.join(environment.split())
    required_phrases = ('PG_TEST_HOST', 'PG_OPERATOR_HOST', 'PG_OPTUNA_TEST_HOST', 'PG_TEST_LOCALE', 'verification_control.runtime_marker', 'verification_control.operator_fingerprints', 'tests.cross_package.qualification.support.postgres_verification provision --reset', 'immediately before each `TRUNCATE`', 'byte-identical to `verification-57i-freeze-v6`', 'isolation_status', 'qualification_status', '--outcome passed')
    for phrase in required_phrases:
        assert phrase in combined
    assert 'never read the legacy/operator `PG_HOST`' in normalized_environment
    assert 'Product rows,' in operations
    assert 'passwords' in operations


def test_docs_define_57l_as_postgres_only_direct_service_qualification() -> None:
    """Keep direct-service qualification explicitly scoped to its Postgres boundary."""
    operations = _read_doc('operations.md')
    product_state = _read_doc('product_state.md')
    combined = '\n'.join((operations, product_state))
    required_phrases = ('57L Postgres-Only Fixture Qualification', 'PostgresEventStore', 'PostgresResearchArtifactStore', 'does not use DuckDB', '48 hourly selection', '32 hourly holdout', 'lookbacks 2, 3, 4, and 5', 'source_filter=null', 'tests/cross_package/qualification/test_postgres_realistic_optimization_fixture.py', '57M separately proves MCP registration')
    for phrase in required_phrases:
        assert phrase in combined
    assert '`verification-57i-freeze-v6`' in product_state


def test_docs_define_57m_as_retained_postgres_stdio_mcp_evidence() -> None:
    """Keep retained MCP stdio evidence and Postgres requirements explicitly documented."""
    operations = _read_doc('operations.md')
    product_state = _read_doc('product_state.md')
    combined = '\n'.join((operations, product_state))
    normalized = ' '.join(combined.split())
    required_phrases = ('57M Stdio MCP Evidence Graph', 'actual MCP `ClientSession` over stdio', 'TRADER_VERIFICATION_RETAIN_PHASE=57M', 'exactly `TRADER_MCP_ALLOW_BACKTESTS=true`', 'research_parameter_optimization_trials', 'service executes the declared seed variant', 'tests/cross_package/qualification/test_postgres_optimization_evidence_graph.py', 'no canonical filesystem path may be present')
    for phrase in required_phrases:
        assert phrase in normalized
    assert '`verification_control.acceptance_records`' in product_state


def test_docs_define_57n_determinism_integrity_and_leakage_controls() -> None:
    """Require determinism, integrity, and leakage controls in qualification documentation."""
    architecture = _read_doc('architecture.md')
    contracts = _read_doc('tool_contracts.md')
    operations = _read_doc('operations.md')
    product_state = _read_doc('product_state.md')
    combined = '\n'.join((architecture, contracts, operations, product_state))
    normalized = ' '.join(combined.split())
    required_phrases = ('57N Determinism, Integrity, And Holdout Leakage', 'tests/cross_package/qualification/test_postgres_optimization_determinism_integrity.py', 'TRADER_VERIFICATION_RETAIN_PHASE=57N', 'verification_control.determinism_snapshots', 'verification_control.integrity_checks', 'verification_control.data_access_log', 'verification_control.selection_seals', 'finished_at', 'duration_seconds', 'complete trial ledger', 'Each public MCP consumer must fail closed')
    for phrase in required_phrases:
        assert phrase in normalized
    assert '`verification-57i-freeze-v6`' in product_state
