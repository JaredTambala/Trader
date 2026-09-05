"""Shared paths and readers for research documentation contracts.

Subject: Canonical active-document sets and bounded Markdown loading.
Level: Cross-package documentation contract.
Collaborators: Repository paths and UTF-8 Markdown files; no product runtime.
Guarantees: Documentation suites resolve the same active pages and canonical aliases.
Non-goals: Asserting documentation content or executing examples.
"""

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


DOC_ROOT = REPO_ROOT / 'docs'


PRODUCT_STATE_PATH = DOC_ROOT / 'product_state.md'


ROADMAP_PATH = REPO_ROOT / 'plans' / 'research_capability_roadmap.md'


LEGACY_TRACKER_PATH = REPO_ROOT / 'plans' / 'mcp_trading_research_tools_plan.md'


PACKAGE_ROOTS = tuple((REPO_ROOT / 'src' / package for package in ('trader', 'trader_standard', 'trader_research', 'trader_mcp', 'trader_agents', 'trader_mlflow')))


DOC_PATHS = {'README.md': (REPO_ROOT / 'src' / 'trader_research' / 'README.md', REPO_ROOT / 'src' / 'trader_mcp' / 'README.md', REPO_ROOT / 'src' / 'trader_agents' / 'README.md'), 'product_state.md': (PRODUCT_STATE_PATH,), 'architecture.md': (DOC_ROOT / 'system_architecture.md', REPO_ROOT / 'src' / 'trader_research' / 'docs' / 'architecture.md', REPO_ROOT / 'src' / 'trader_research' / 'docs' / 'experiments.md', REPO_ROOT / 'src' / 'trader_research' / 'docs' / 'ml.md', REPO_ROOT / 'src' / 'trader_agents' / 'docs' / 'architecture.md', REPO_ROOT / 'src' / 'trader_agents' / 'docs' / 'coordinator.md', REPO_ROOT / 'src' / 'trader_agents' / 'docs' / 'model_runtime.md', REPO_ROOT / 'src' / 'trader_mlflow' / 'docs' / 'architecture.md'), 'agents.md': (REPO_ROOT / 'src' / 'trader_agents' / 'docs' / 'roles_and_authority.md', REPO_ROOT / 'src' / 'trader_agents' / 'docs' / 'coordinator.md', REPO_ROOT / 'src' / 'trader_agents' / 'docs' / 'specialists.md'), 'mcp_tools.md': (REPO_ROOT / 'src' / 'trader_mcp' / 'docs' / 'tools.md',), 'workflows.md': (DOC_ROOT / 'workflows' / 'research.md',), 'operations.md': (DOC_ROOT / 'workflows' / 'research_operations.md', DOC_ROOT / 'history' / 'research_agents' / 'research_operations_before_package_ownership.md'), 'semantic_extraction.md': (REPO_ROOT / 'src' / 'trader_research' / 'docs' / 'knowledge.md',), 'tool_contracts.md': (REPO_ROOT / 'src' / 'trader_mcp' / 'docs' / 'contracts.md',)}


STALE_CURRENT_CLAIMS = ('backtest tools are not registered yet', 'No backtest tool is exposed', 'Planned:')


def _current_markdown_docs() -> tuple[Path, ...]:
    paths = [path for path in DOC_ROOT.rglob('*.md') if 'history' not in path.relative_to(DOC_ROOT).parts]
    for package_root in PACKAGE_ROOTS:
        paths.append(package_root / 'README.md')
        paths.extend((package_root / 'docs').glob('*.md'))
    return tuple(sorted(paths))


def _read_doc(name: str) -> str:
    """Read one logical research topic from its package-owned canonical pages."""
    return '\n'.join((path.read_text(encoding='utf-8') for path in DOC_PATHS[name]))
