"""Architecture contracts for research bounded-context dependencies.

Subject: Allowed imports among research contexts and their public consumption by outer layers.
Level: Cross-package architecture contract.
Collaborators: Real repository source paths plus AST import inspection; no service execution.
Guarantees: Research contexts remain acyclic, authority-safe, and accessible through public facades.
Non-goals: Scientific correctness, persistence behavior, and agent decision quality.
"""

import ast
from pathlib import Path

from tests.cross_package.boundaries.import_scanning import (
    imported_modules as _imported_modules,
)


def test_experiment_core_does_not_import_optional_or_unrelated_contexts() -> None:
    """Keep deterministic Experiment core independent of optional and unrelated contexts."""
    forbidden = ('alpaca', 'mlflow', 'optuna', 'trader_mcp', 'trader_agents', 'trader_research.infrastructure', 'trader_research.knowledge', 'trader_research.methodology', 'trader_research.review')
    offenders: list[str] = []
    for path in Path('src/trader_research/experiments').rglob('*.py'):
        for imported in _imported_modules(path):
            if imported.startswith(forbidden):
                offenders.append(f'{path}: imports {imported}')
    assert offenders == []


def test_composition_layers_use_only_the_public_experiments_facade() -> None:
    """Require outer composition layers to consume the public Experiments facade."""
    roots = (Path('src/trader_mcp'), Path('src/trader_agents'))
    offenders: list[str] = []
    for root in roots:
        for path in root.rglob('*.py'):
            for imported in _imported_modules(path):
                if imported.startswith('trader_research.experiments.'):
                    offenders.append(f'{path}: imports {imported}')
    assert offenders == []


def test_mcp_and_agents_use_public_bounded_context_facades() -> None:
    """Require MCP and Agents to consume public research context facades."""
    public_contexts = ('trader_research.foundation', 'trader_research.governance', 'trader_research.data', 'trader_research.knowledge', 'trader_research.methodology', 'trader_research.experiments', 'trader_research.review')
    offenders: list[str] = []
    for root in (Path('src/trader_mcp'), Path('src/trader_agents')):
        for path in root.rglob('*.py'):
            for imported in _imported_modules(path):
                for public_context in public_contexts:
                    if imported.startswith(f'{public_context}.'):
                        offenders.append(f'{path}: imports {imported}')
    assert offenders == []


def test_research_bounded_context_import_graph_is_directional_and_acyclic() -> None:
    """Enforce the approved acyclic dependency direction among research contexts."""
    context_paths = {'foundation': Path('src/trader_research/foundation'), 'governance': Path('src/trader_research/governance'), 'data': Path('src/trader_research/data'), 'knowledge': Path('src/trader_research/knowledge'), 'methodology': Path('src/trader_research/methodology'), 'experiments': Path('src/trader_research/experiments'), 'review': Path('src/trader_research/review'), 'infrastructure': Path('src/trader_research/infrastructure')}
    allowed_edges = {('governance', 'foundation'), ('data', 'foundation'), ('knowledge', 'foundation'), ('knowledge', 'governance'), ('methodology', 'foundation'), ('methodology', 'governance'), ('methodology', 'knowledge'), ('experiments', 'foundation'), ('experiments', 'governance'), ('review', 'foundation'), ('review', 'governance'), ('review', 'experiments'), ('infrastructure', 'foundation'), ('infrastructure', 'governance'), ('infrastructure', 'knowledge'), ('infrastructure', 'data'), ('infrastructure', 'experiments')}
    edges: set[tuple[str, str]] = set()
    for owner, root in context_paths.items():
        for path in root.rglob('*.py'):
            for imported in _imported_modules(path):
                prefix = 'trader_research.'
                if not imported.startswith(prefix):
                    continue
                target = imported.removeprefix(prefix).split('.', 1)[0]
                if target in context_paths and target != owner:
                    edges.add((owner, target))
    assert sorted(edges.difference(allowed_edges)) == []
    adjacency = {context: {target for owner, target in edges if owner == context} for context in context_paths}

    def reaches_origin(origin: str, current: str, visited: set[str]) -> bool:
        for target in adjacency[current]:
            if target == origin:
                return True
            if target not in visited and reaches_origin(origin, target, {*visited, target}):
                return True
        return False
    cycles = [context for context in context_paths if reaches_origin(context, context, {context})]
    assert cycles == []


def test_review_imports_only_the_immutable_experiment_read_port() -> None:
    """Limit Review to the immutable public Experiment read port."""
    allowed = 'trader_research.experiments.reads'
    offenders: list[str] = []
    for path in Path('src/trader_research/review').rglob('*.py'):
        for imported in _imported_modules(path):
            if imported.startswith('trader_research.experiments') and imported != allowed:
                offenders.append(f'{path}: imports {imported}')
    assert offenders == []


def test_review_never_persists_experiment_owned_artifact_types() -> None:
    """Prevent Review code from writing artifacts owned by Experiments."""
    forbidden_artifact_names = {'IMPLEMENTATION_VERSION', 'IMPLEMENTATION_VALIDATION_REPORT', 'STRATEGY_SPECIFICATION', 'STRATEGY_SPECIFICATION_VALIDATION_REPORT', 'RISK_STACK_SPECIFICATION', 'RISK_STACK_SPECIFICATION_VALIDATION_REPORT', 'BACKTEST_SPECIFICATION', 'BACKTEST_SPECIFICATION_VALIDATION_REPORT', 'BACKTEST_RUN', 'PARAMETER_OPTIMIZATION_PLAN', 'PARAMETER_OPTIMIZATION_RUN', 'PARAMETER_OPTIMIZATION_TRIAL', 'EXPERIMENT_TRACKING_PROJECTION_REPORT'}
    offenders: list[str] = []
    for path in Path('src/trader_research/review').rglob('*.py'):
        tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr != 'save_artifact':
                continue
            artifact_keyword = next((item for item in node.keywords if item.arg == 'artifact_type'), None)
            if artifact_keyword is not None and isinstance(artifact_keyword.value, ast.Name) and (artifact_keyword.value.id in forbidden_artifact_names):
                offenders.append(f'{path}: persists {artifact_keyword.value.id}')
    assert offenders == []


def test_methodology_depends_only_on_public_approved_card_knowledge_port() -> None:
    """Limit Methodology knowledge access to the approved-card public port."""
    offenders: list[str] = []
    allowed = 'trader_research.knowledge.approved_cards'
    for path in Path('src/trader_research/methodology').rglob('*.py'):
        for imported in _imported_modules(path):
            if imported.startswith('trader_research.knowledge') and imported != allowed:
                offenders.append(f'{path}: imports {imported}')
    assert offenders == []


def test_foundation_depends_only_on_python_standard_library() -> None:
    """Keep research foundation values independent of every Trader package."""
    offenders: list[str] = []
    for path in Path('src/trader_research/foundation').rglob('*.py'):
        for imported in _imported_modules(path):
            if imported.startswith(('trader', 'trader_research', 'trader_mcp', 'trader_agents')):
                offenders.append(f'{path}: imports {imported}')
    assert offenders == []


def test_orchestration_contracts_do_not_import_service_implementations() -> None:
    """Keep orchestration contracts independent of services, transports, and adapters."""
    forbidden = ('trader', 'trader_agents', 'trader_mcp', 'trader_research.data', 'trader_research.experiments', 'trader_research.infrastructure', 'trader_research.knowledge', 'trader_research.methodology', 'trader_research.ml', 'trader_research.review')
    offenders: list[str] = []
    for path in Path('src/trader_research/governance/orchestration').glob('*.py'):
        for imported in sorted(_imported_modules(path)):
            if imported in forbidden or imported.startswith(tuple((f'{prefix}.' for prefix in forbidden))):
                offenders.append(f'{path}: imports {imported}')
    assert offenders == []


def test_canonical_experiment_packages_do_not_import_knowledge_or_candidate_domains() -> None:
    """Keep canonical Experiment and Review code independent of authoring domains."""
    roots = (Path('src/trader_research/experiments'), Path('src/trader_research/review'))
    files = [path for root in roots for path in root.rglob('*.py')]
    forbidden = ('trader_research.knowledge', 'trader_research.strategy_candidates', 'trader_research.risk_managers', 'trader_research.portfolio_stacks', 'trader_research.methodology')
    offenders: list[str] = []
    for path in files:
        for imported in _imported_modules(path):
            if imported.startswith(forbidden):
                offenders.append(f'{path}: imports {imported}')
    assert offenders == []


def test_data_context_has_one_public_facade_and_no_retired_provider_package() -> None:
    """Keep research Data behind one facade without its retired provider package."""
    retired_paths = (Path('src/trader_research/data/services.py'), Path('src/trader_research/providers'))
    assert [str(path) for path in retired_paths if path.exists()] == []
    forbidden_data_imports = ('alpaca', 'trader_mcp', 'trader_agents', 'trader_research.knowledge', 'trader_research.methodology', 'trader_research.experiments', 'trader_research.review')
    offenders: list[str] = []
    for path in Path('src/trader_research/data').rglob('*.py'):
        for imported in _imported_modules(path):
            if imported.startswith(forbidden_data_imports):
                offenders.append(f'{path}: imports {imported}')
    assert offenders == []


def test_outer_layers_import_data_only_through_its_public_facade() -> None:
    """Require MCP and Agents to consume Data only through its facade."""
    roots = (Path('src/trader_mcp'), Path('src/trader_agents'))
    offenders: list[str] = []
    for root in roots:
        for path in root.rglob('*.py'):
            for imported in _imported_modules(path):
                if imported.startswith('trader_research.data.'):
                    offenders.append(f'{path}: imports {imported}')
    assert offenders == []
