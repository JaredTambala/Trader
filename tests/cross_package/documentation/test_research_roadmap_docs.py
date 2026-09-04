"""Contracts for active research roadmap documentation.

Subject: Dependency integrity and durable architectural naming in the repository roadmap.
Level: Cross-package documentation contract.
Collaborators: Active Markdown pages, the roadmap, and its deprecated predecessor.
Guarantees: Roadmap nodes are known, acyclic, dependency-led, and absent from architecture names.
Non-goals: Notion delivery status, execution scheduling, or historical checkpoint prose.
"""

import re

from tests.cross_package.documentation.research_doc_support import (
    LEGACY_TRACKER_PATH,
    REPO_ROOT,
    ROADMAP_PATH,
    _current_markdown_docs,
)


def test_active_product_docs_do_not_name_architecture_with_roadmap_ids() -> None:
    """Reject delivery checkpoint codes from active product architecture language."""
    roadmap_id = re.compile('\\bORCH-(?:GOV|\\d+)\\b')
    roadmap = ROADMAP_PATH.read_text(encoding='utf-8')
    assert 'identifiers are roadmap work-item labels only' in roadmap
    assert 'never names components after delivery checkpoints' in roadmap
    for path in _current_markdown_docs():
        content = path.read_text(encoding='utf-8')
        assert roadmap_id.search(content) is None, path.relative_to(REPO_ROOT)


def test_active_roadmap_is_dependency_driven_and_legacy_tracker_is_deprecated() -> None:
    """Keep the roadmap dependency-driven and the legacy tracker explicitly deprecated."""
    roadmap = ROADMAP_PATH.read_text(encoding='utf-8')
    legacy = LEGACY_TRACKER_PATH.read_text(encoding='utf-8')
    for heading in ('## Capability Dependency Graph', '## Accepted Baseline', '## Active Work Graph', '## Current Ready Queue', '## Target Agent Capability Map', '## Historical Lineage Index'):
        assert heading in roadmap
    assert 'This is a choice of parallel frontiers' in roadmap
    assert 'Orchestration is a cross-cutting capability' in roadmap
    assert 'Status: deprecated on 2026-07-25' in legacy
    assert 'Do not add tasks' in legacy
    assert 'git show 577c774:plans/mcp_trading_research_tools_plan.md' in legacy
    assert '## Incremental Build Slices' not in legacy
    assert len(legacy.splitlines()) < 60


def test_active_roadmap_dependencies_reference_known_nodes_and_are_acyclic() -> None:
    """Require roadmap dependencies to reference known nodes without forming cycles."""
    roadmap = ROADMAP_PATH.read_text(encoding='utf-8')
    node_pattern = re.compile('^(?:BASE|ORCH|ML|QUAL|ROB|REV|REC|WFO|AGENT|DATA|KNOW|RUNNER|PERF)-[A-Z0-9-]+$')
    status_values = {'ready', 'in_progress', 'blocked', 'deferred', 'complete'}
    rows: list[list[str]] = []
    node_ids: set[str] = set()
    for line in roadmap.splitlines():
        if not line.startswith('|'):
            continue
        cells = [cell.strip() for cell in line.strip().strip('|').split('|')]
        if cells and node_pattern.fullmatch(cells[0]):
            node_ids.add(cells[0])
            rows.append(cells)
    assert {'BASE-EXP', 'BASE-OPT', 'BASE-ML-RUNTIME', 'ORCH-GOV', 'ORCH-1', 'ML-1', 'ROB-1'} <= node_ids
    dependencies: dict[str, set[str]] = {node_id: set() for node_id in node_ids}
    for cells in rows:
        if len(cells) < 4 or cells[2] not in status_values:
            continue
        for dependency in cells[3].split(','):
            dependency_id = dependency.strip()
            if dependency_id == 'None':
                continue
            assert node_pattern.fullmatch(dependency_id), (cells[0], dependency_id)
            assert dependency_id in node_ids, (cells[0], dependency_id)
            dependencies[cells[0]].add(dependency_id)
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node_id: str) -> None:
        if node_id in visited:
            return
        assert node_id not in visiting, f'roadmap dependency cycle at {node_id}'
        visiting.add(node_id)
        for dependency_id in dependencies[node_id]:
            visit(dependency_id)
        visiting.remove(node_id)
        visited.add(node_id)
    for node_id in sorted(node_ids):
        visit(node_id)
