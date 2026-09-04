"""Repository contracts for retired architecture and compatibility surfaces.

Subject: The absence of superseded package paths, imports, scripts, APIs, and delivery-code names.
Level: Cross-package architecture contract.
Collaborators: Real repository source paths plus AST import inspection; no product runtime or external service.
Guarantees: Removed architecture cannot silently return as a compatibility or import surface.
Non-goals: Current dependency direction, runtime behavior, and migration-history documentation.
"""

from pathlib import Path
import re

from tests.cross_package.boundaries.import_scanning import (
    imported_modules as _imported_modules,
)


THIS_MODULE = Path('tests/cross_package/boundaries/test_retired_architecture_surfaces.py')


REMOVED_COMPAT_SURFACES = {Path('src/trader/alpaca_market_data.py'), Path('src/trader/api.py'), Path('src/trader/data.py'), Path('src/trader/data_quality.py'), Path('src/trader/knowledge_store.py'), Path('src/trader/market_data_backfill.py'), Path('src/trader/market_data_queries.py'), Path('src/trader/market_data_replay.py'), Path('src/trader/market_data_stream.py'), Path('src/trader/metrics.py'), Path('src/trader/notifications.py'), Path('src/trader/order_recovery.py'), Path('src/trader/research.py'), Path('src/trader/runtime_status.py'), Path('src/trader/sample_data.py'), Path('src/trader/strategy.py'), Path('src/trader/tools'), Path('src/trader/trader_service.py')}


REMOVED_COMPAT_IMPORTS = {'trader.alpaca_market_data', 'trader.api', 'trader.data', 'trader.data_quality', 'trader.knowledge', 'trader.knowledge_store', 'trader.market_data_backfill', 'trader.market_data_queries', 'trader.market_data_replay', 'trader.market_data_stream', 'trader.metrics', 'trader.notifications', 'trader.order_recovery', 'trader.research', 'trader.runtime_status', 'trader.sample_data', 'trader.strategy', 'trader.tools', 'trader.trader_service'}


REMOVED_RESEARCH_FLAT_MODULES = {Path('src/trader_research/backtests.py'), Path('src/trader_research/cpp_kernel_artifacts.py'), Path('src/trader_research/data.py'), Path('src/trader_research/evaluation.py'), Path('src/trader_research/math_domain.py'), Path('src/trader_research/math_registry.py'), Path('src/trader_research/math_tools.py'), Path('src/trader_research/method_packages.py'), Path('src/trader_research/multiple_testing.py'), Path('src/trader_research/risk_managers.py'), Path('src/trader_research/signal_diagnostics.py'), Path('src/trader_research/strategies.py'), Path('src/trader_research/strategy_validation.py')}


REMOVED_RESEARCH_FLAT_IMPORTS = {'trader_research.cpp_kernel_artifacts', 'trader_research.math_domain', 'trader_research.math_registry', 'trader_research.math_tools', 'trader_research.method_packages', 'trader_research.multiple_testing', 'trader_research.signal_diagnostics', 'trader_research.strategies', 'trader_research.strategy_validation'}


RETIRED_CANDIDATE_SURFACES = {Path('src/trader_research/strategy_candidates'), Path('src/trader_research/risk_managers'), Path('src/trader_research/portfolio_stacks'), Path('src/trader_research/experiments/backtests/services.py'), Path('src/trader_research/review/evaluation/performance.py')}


RETIRED_CANDIDATE_IMPORTS = {'trader_research.strategy_candidates', 'trader_research.risk_managers', 'trader_research.portfolio_stacks', 'trader_research.experiments.backtests.services', 'trader_research.review.evaluation.performance'}


RETIRED_LEGACY_RESEARCH_SURFACES = {Path('src/trader_research/artifacts.py'), Path('src/trader_research/discovery.py'), Path('src/trader_research/promotion.py'), Path('src/trader_research/recommendations.py'), Path('src/trader_research/research.py'), Path('src/trader_research/suites.py'), Path('run_compare_results.py'), Path('run_prepare_paper_promotion.py'), Path('run_research_discovery.py'), Path('run_research_experiment.py'), Path('run_research_recommendations.py')}


RETIRED_LEGACY_RESEARCH_IMPORTS = {'trader_research.artifacts', 'trader_research.discovery', 'trader_research.promotion', 'trader_research.recommendations', 'trader_research.research', 'trader_research.suites'}


RETIRED_RESEARCH_HUBS = {Path('src/trader_research/agents.py'), Path('src/trader_research/artifact_store.py'), Path('src/trader_research/contracts.py'), Path('src/trader_research/domain.py'), Path('src/trader_research/postgres_artifact_store.py')}


RETIRED_RESEARCH_HUB_IMPORTS = {'trader_research.agents', 'trader_research.artifact_store', 'trader_research.contracts', 'trader_research.domain', 'trader_research.postgres_artifact_store'}


RETIRED_AGENT_ORCHESTRATION_SURFACES = {Path('src/trader_agents/catalogue.py'), Path('src/trader_agents/cli.py'), Path('src/trader_agents/contracts.py'), Path('src/trader_agents/coordinator.py'), Path('src/trader_agents/data_agent'), Path('src/trader_agents/data_research.py'), Path('src/trader_agents/experiment_design_agent'), Path('src/trader_agents/inputs.py'), Path('src/trader_agents/llm_client.py'), Path('src/trader_agents/mcp_runtime.py'), Path('src/trader_agents/observability.py'), Path('src/trader_agents/observability_console.py'), Path('src/trader_agents/observability_emit.py'), Path('src/trader_agents/observability_projections.py'), Path('src/trader_agents/orchestration'), Path('src/trader_agents/policy.py'), Path('src/trader_agents/profiles.py'), Path('src/trader_agents/programs.py'), Path('src/trader_agents/quant_research.py'), Path('src/trader_agents/research_composition'), Path('src/trader_agents/research_coordinator'), Path('src/trader_agents/runtime.py'), Path('src/trader_agents/scheduler.py'), Path('src/trader_agents/state.py'), Path('src/trader_agents/strategy_engineering.py'), Path('src/trader_agents/structured_model.py'), Path('src/trader_agents/tool_client.py'), Path('src/trader_agents/tracing.py')}


RETIRED_AGENT_ORCHESTRATION_IMPORTS = {'trader_agents.catalogue', 'trader_agents.cli', 'trader_agents.coordinator', 'trader_agents.data_agent', 'trader_agents.data_research', 'trader_agents.experiment_design_agent', 'trader_agents.inputs', 'trader_agents.llm_client', 'trader_agents.mcp_runtime', 'trader_agents.observability_console', 'trader_agents.observability_emit', 'trader_agents.observability_projections', 'trader_agents.orchestration', 'trader_agents.policy', 'trader_agents.profiles', 'trader_agents.programs', 'trader_agents.quant_research', 'trader_agents.research_composition', 'trader_agents.research_coordinator', 'trader_agents.runtime', 'trader_agents.scheduler', 'trader_agents.state', 'trader_agents.strategy_engineering', 'trader_agents.structured_model', 'trader_agents.tool_client', 'trader_agents.tracing'}


RETIRED_METHODOLOGY_SURFACES = {Path('src/trader_research/methods'), Path('src/trader_research/method_implementations'), Path('src/trader_research/knowledge/domain.py'), Path('src/trader_research/methodology/implementation/generation.py'), Path('src/trader_research/method_contracts_seed.json'), Path('src/trader_research/methodology/method_contracts_seed.json')}


RETIRED_METHODOLOGY_IMPORTS = {'trader_research.methods', 'trader_research.method_implementations', 'trader_research.methodology.implementation.generation'}


RETIRED_EXPERIMENT_SURFACES = {Path('src/trader_research/implementations'), Path('src/trader_research/specifications'), Path('src/trader_research/backtests'), Path('src/trader_research/optimization'), Path('src/trader_research/tracking')}


RETIRED_EXPERIMENT_IMPORTS = {'trader_research.implementations', 'trader_research.specifications', 'trader_research.backtests', 'trader_research.optimization', 'trader_research.tracking'}


RETIRED_REVIEW_SURFACES = {Path('src/trader_research/evaluation'), Path('src/trader_research/adversarial')}


RETIRED_REVIEW_IMPORTS = {'trader_research.evaluation', 'trader_research.adversarial'}


IMPLEMENTATION_CHECKPOINT_PATTERN = re.compile('\\b(?:ORCH-\\d+|AGENT-(?:\\d+|[A-Z][A-Z0-9-]*))\\b')


def test_runtime_architecture_does_not_use_implementation_checkpoint_names() -> None:
    """Keep roadmap checkpoint codes out of runtime architectural names."""
    offenders: list[str] = []
    for path in Path('src').rglob('*.py'):
        for line_number, line in enumerate(path.read_text().splitlines(), start=1):
            if IMPLEMENTATION_CHECKPOINT_PATTERN.search(line):
                offenders.append(f'{path}:{line_number}: {line.strip()}')
    assert offenders == []


def test_removed_trader_compatibility_surfaces_do_not_exist() -> None:
    """Prevent deleted Trader compatibility modules from becoming supported surfaces again."""
    offenders = [str(path) for path in sorted(REMOVED_COMPAT_SURFACES) if path.exists()]
    offenders.extend((str(path) for path in Path('src/trader/knowledge').rglob('*.py')))
    assert offenders == []


def test_retired_candidate_architecture_does_not_exist() -> None:
    """Keep the superseded candidate package topology absent from production source."""
    offenders = [str(path) for path in sorted(RETIRED_CANDIDATE_SURFACES) if path.exists()]
    assert offenders == []


def test_retired_legacy_research_surfaces_do_not_exist() -> None:
    """Keep retired research facades and scripts outside the active architecture."""
    offenders = [str(path) for path in sorted(RETIRED_LEGACY_RESEARCH_SURFACES) if path.exists()]
    assert offenders == []


def test_retired_research_dependency_hubs_do_not_exist() -> None:
    """Prevent broad research dependency hubs from returning to the package."""
    offenders = [str(path) for path in sorted(RETIRED_RESEARCH_HUBS) if path.exists()]
    assert offenders == []


def test_retired_methodology_surfaces_do_not_exist() -> None:
    """Keep superseded methodology packages and seed locations permanently absent."""
    offenders = [str(path) for path in sorted(RETIRED_METHODOLOGY_SURFACES) if path.exists()]
    assert offenders == []


def test_retired_top_level_experiment_packages_do_not_exist() -> None:
    """Keep Experiment capabilities inside their canonical bounded-context package."""
    offenders = [str(path) for path in sorted(RETIRED_EXPERIMENT_SURFACES) if path.exists()]
    assert offenders == []


def test_repo_code_does_not_import_retired_top_level_experiment_packages() -> None:
    """Reject imports that revive retired top-level Experiment package paths."""
    offenders: list[str] = []
    for root in (Path('src'), Path('tests'), Path('examples')):
        for path in root.rglob('*.py'):
            if path == THIS_MODULE:
                continue
            for imported in _imported_modules(path):
                if imported in RETIRED_EXPERIMENT_IMPORTS or any((imported.startswith(f'{module}.') for module in RETIRED_EXPERIMENT_IMPORTS)):
                    offenders.append(f'{path}: imports {imported}')
    assert offenders == []


def test_retired_top_level_review_packages_and_imports_do_not_exist() -> None:
    """Keep Review capabilities and imports at their canonical package paths."""
    assert [str(path) for path in sorted(RETIRED_REVIEW_SURFACES) if path.exists()] == []
    offenders: list[str] = []
    for root in (Path('src'), Path('tests'), Path('examples')):
        for path in root.rglob('*.py'):
            if path == THIS_MODULE:
                continue
            for imported in _imported_modules(path):
                if imported in RETIRED_REVIEW_IMPORTS or any((imported.startswith(f'{module}.') for module in RETIRED_REVIEW_IMPORTS)):
                    offenders.append(f'{path}: imports {imported}')
    assert offenders == []


def test_repo_code_does_not_import_retired_methodology_packages() -> None:
    """Reject imports that revive retired methodology package locations."""
    offenders: list[str] = []
    for root in (Path('src'), Path('tests'), Path('examples')):
        for path in root.rglob('*.py'):
            if path == THIS_MODULE:
                continue
            for imported in _imported_modules(path):
                if imported in RETIRED_METHODOLOGY_IMPORTS or any((imported.startswith(f'{module}.') for module in RETIRED_METHODOLOGY_IMPORTS)):
                    offenders.append(f'{path}: imports {imported}')
    assert offenders == []


def test_retired_method_card_symbols_are_absent_from_product_code() -> None:
    """Prevent retired method-card APIs from returning through product code."""
    retired_terms = ('RichMethodCard', 'RICH_METHOD_CARD_FORMAT', 'knowledge_create_rich_method_card_draft', 'create_rich_method_card_draft', 'save_method_contract', 'list_persisted_method_contracts')
    offenders: list[str] = []
    for path in Path('src/trader_research').rglob('*.py'):
        text = path.read_text(encoding='utf-8')
        for term in retired_terms:
            if term in text:
                offenders.append(f'{path}: contains {term}')
    for path in Path('src/trader_mcp').rglob('*.py'):
        text = path.read_text(encoding='utf-8')
        for term in retired_terms:
            if term in text:
                offenders.append(f'{path}: contains {term}')
    assert offenders == []


def test_repo_code_does_not_import_retired_research_dependency_hubs() -> None:
    """Reject imports that recreate broad retired research dependency hubs."""
    offenders: list[str] = []
    for root in (Path('src'), Path('tests'), Path('examples')):
        for path in root.rglob('*.py'):
            if path == THIS_MODULE:
                continue
            for imported in _imported_modules(path):
                if imported in RETIRED_RESEARCH_HUB_IMPORTS or any((imported.startswith(f'{module}.') for module in RETIRED_RESEARCH_HUB_IMPORTS)):
                    offenders.append(f'{path}: imports {imported}')
    assert offenders == []


def test_legacy_data_agent_graph_surfaces_are_removed() -> None:
    """Keep the retired deterministic Data-agent graph API permanently absent."""
    assert not Path('src/trader_agents/data_agent_policy.py').exists()
    package = Path('src/trader_agents/__init__.py').read_text(encoding='utf-8')
    for name in ('DataAgentState', 'build_data_agent_initial_state', 'build_data_agent_inventory_graph', 'build_data_agent_llm_policy_graph', 'build_data_agent_quality_graph', 'build_data_agent_workflow_graph', 'data_agent_handoffs_from_state'):
        assert name not in package


def test_retired_agent_orchestration_surfaces_and_imports_are_removed() -> None:
    """Prevent removed Agent orchestration modules and imports from returning."""
    assert [str(path) for path in sorted(RETIRED_AGENT_ORCHESTRATION_SURFACES) if path.exists()] == []
    offenders: list[str] = []
    for root in (Path('src'), Path('tests'), Path('examples')):
        for path in root.rglob('*.py'):
            if path == THIS_MODULE:
                continue
            for imported in _imported_modules(path):
                if imported in RETIRED_AGENT_ORCHESTRATION_IMPORTS or any((imported.startswith(f'{module}.') for module in RETIRED_AGENT_ORCHESTRATION_IMPORTS)):
                    offenders.append(f'{path}: imports {imported}')
    assert offenders == []


def test_repo_code_does_not_import_retired_legacy_research_surfaces() -> None:
    """Reject imports that revive retired legacy research service paths."""
    offenders: list[str] = []
    for root in (Path('src'), Path('tests'), Path('examples')):
        for path in root.rglob('*.py'):
            if path == THIS_MODULE:
                continue
            for imported in _imported_modules(path):
                if imported in RETIRED_LEGACY_RESEARCH_IMPORTS or any((imported.startswith(f'{module}.') for module in RETIRED_LEGACY_RESEARCH_IMPORTS)):
                    offenders.append(f'{path}: imports {imported}')
    assert offenders == []


def test_repo_code_does_not_import_retired_candidate_architecture() -> None:
    """Reject imports that revive superseded candidate architecture packages."""
    offenders: list[str] = []
    for root in (Path('src'), Path('tests'), Path('examples')):
        for path in root.rglob('*.py'):
            if path == THIS_MODULE:
                continue
            for imported in _imported_modules(path):
                if imported in RETIRED_CANDIDATE_IMPORTS or any((imported.startswith(f'{module}.') for module in RETIRED_CANDIDATE_IMPORTS)):
                    offenders.append(f'{path}: imports {imported}')
    assert offenders == []


def test_repo_code_does_not_import_removed_trader_compatibility_surfaces() -> None:
    """Reject imports that restore deleted Trader compatibility entry points."""
    offenders: list[str] = []
    for root in (Path('src'), Path('tests'), Path('examples')):
        for path in root.rglob('*.py'):
            if path == THIS_MODULE:
                continue
            for imported in _imported_modules(path):
                if imported in REMOVED_COMPAT_IMPORTS or any((imported.startswith(f'{module}.') for module in REMOVED_COMPAT_IMPORTS)):
                    offenders.append(f'{path}: imports {imported}')
    for path in Path('.').glob('run_*.py'):
        for imported in _imported_modules(path):
            if imported in REMOVED_COMPAT_IMPORTS or any((imported.startswith(f'{module}.') for module in REMOVED_COMPAT_IMPORTS)):
                offenders.append(f'{path}: imports {imported}')
    assert offenders == []


def test_removed_trader_research_flat_service_modules_do_not_exist() -> None:
    """Keep research services in canonical capability packages rather than flat modules."""
    offenders = [str(path) for path in sorted(REMOVED_RESEARCH_FLAT_MODULES) if path.exists()]
    assert offenders == []


def test_repo_code_uses_canonical_trader_research_capability_packages() -> None:
    """Require repository imports to use canonical research capability packages."""
    offenders: list[str] = []
    for root in (Path('src'), Path('tests'), Path('examples')):
        for path in root.rglob('*.py'):
            if path == THIS_MODULE:
                continue
            for imported in _imported_modules(path):
                if imported in REMOVED_RESEARCH_FLAT_IMPORTS or any((imported.startswith(f'{module}.') for module in REMOVED_RESEARCH_FLAT_IMPORTS)):
                    offenders.append(f'{path}: imports {imported}')
    assert offenders == []
