"""Architecture contracts for distribution-level dependency direction.

Subject: Isolation of core, deterministic research, and optional MLflow runtime dependencies.
Level: Cross-package architecture contract.
Collaborators: Real package source paths plus AST import inspection; no imported product runtime.
Guarantees: Core remains inward, research remains deterministic, and MLflow stays optional.
Non-goals: Provider behavior, package installation, and inference-result parity.
"""

from pathlib import Path

from tests.cross_package.boundaries.import_scanning import (
    imported_modules as _imported_modules,
)


def test_trader_package_does_not_depend_on_research_agent_packages() -> None:
    """Keep core Trader independent of research, MCP, Agents, and MLflow."""
    offenders: list[str] = []
    for path in Path('src/trader').rglob('*.py'):
        for imported in _imported_modules(path):
            if imported in {'trader_research', 'trader_mcp', 'trader_agents', 'trader_mlflow'} or imported.startswith(('trader_research.', 'trader_mcp.', 'trader_agents.', 'trader_mlflow.')):
                offenders.append(f'{path}: imports {imported}')
    assert offenders == []


def test_mlflow_runtime_dependencies_stay_in_optional_adapter_package() -> None:
    """Confine MLflow runtime dependencies to the optional adapter boundary."""
    offenders: list[str] = []
    for root in (Path('src/trader'), Path('src/trader_standard')):
        for path in root.rglob('*.py'):
            for imported in _imported_modules(path):
                if imported in {'mlflow', 'pandas', 'trader_mlflow'} or imported.startswith(('mlflow.', 'pandas.', 'trader_mlflow.')):
                    offenders.append(f'{path}: imports {imported}')
    allowed_research_adapter = Path('src/trader_research/infrastructure/providers/mlflow.py')
    for path in Path('src/trader_research').rglob('*.py'):
        for imported in _imported_modules(path):
            if imported == 'trader_mlflow' or imported.startswith('trader_mlflow.'):
                offenders.append(f'{path}: imports {imported}')
            if path != allowed_research_adapter and (imported in {'mlflow', 'pandas'} or imported.startswith(('mlflow.', 'pandas.'))):
                offenders.append(f'{path}: imports {imported}')
    for path in Path('src/trader_mlflow').rglob('*.py'):
        for imported in _imported_modules(path):
            if imported == 'trader_research' or imported.startswith('trader_research.'):
                offenders.append(f'{path}: imports {imported}')
    research_ml_facade = Path('src/trader_research/ml/__init__.py').read_text(encoding='utf-8')
    if 'InferenceAdapterProfile' in research_ml_facade:
        offenders.append('src/trader_research/ml/__init__.py: re-exports core inference profile')
    assert offenders == []


def test_trader_research_does_not_import_mcp_or_langgraph_agent_packages() -> None:
    """Keep deterministic research independent of MCP and Agent orchestration."""
    offenders: list[str] = []
    for path in Path('src/trader_research').rglob('*.py'):
        for imported in _imported_modules(path):
            if imported in {'trader_mcp', 'trader_agents'} or imported.startswith(('trader_mcp.', 'trader_agents.')):
                offenders.append(f'{path}: imports {imported}')
    assert offenders == []
