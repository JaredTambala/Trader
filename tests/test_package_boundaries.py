from __future__ import annotations

import ast
from pathlib import Path


TRADER_COMPAT_SHIMS = {
    Path("src/trader/research.py"),
    Path("src/trader/tools/__init__.py"),
    Path("src/trader/tools/artifacts.py"),
    Path("src/trader/tools/contracts.py"),
    Path("src/trader/tools/discovery.py"),
    Path("src/trader/tools/promotion.py"),
    Path("src/trader/tools/recommendations.py"),
    Path("src/trader/tools/suites.py"),
}


def test_trader_package_does_not_depend_on_research_agent_packages_except_shims() -> None:
    offenders: list[str] = []
    for path in Path("src/trader").rglob("*.py"):
        if path in TRADER_COMPAT_SHIMS:
            continue
        for imported in _imported_modules(path):
            if imported in {"trader_research", "trader_mcp", "trader_agents"} or imported.startswith(
                ("trader_research.", "trader_mcp.", "trader_agents.")
            ):
                offenders.append(f"{path}: imports {imported}")

    assert offenders == []


def test_legacy_research_surfaces_are_thin_compatibility_shims() -> None:
    for path in sorted(TRADER_COMPAT_SHIMS):
        text = path.read_text(encoding="utf-8")
        if path.name == "__init__.py":
            continue
        assert "canonical implementations live in `trader_research" in text


def test_trader_research_does_not_import_mcp_or_langgraph_agent_packages() -> None:
    offenders: list[str] = []
    for path in Path("src/trader_research").rglob("*.py"):
        for imported in _imported_modules(path):
            if imported in {"trader_mcp", "trader_agents"} or imported.startswith(("trader_mcp.", "trader_agents.")):
                offenders.append(f"{path}: imports {imported}")

    assert offenders == []


def test_trader_agents_do_not_import_data_platform_or_mcp_server_boundaries() -> None:
    forbidden = {
        "trader.data",
        "trader.market_data_queries",
        "trader_research.data",
        "trader_mcp.server",
    }
    offenders: list[str] = []
    for path in Path("src/trader_agents").rglob("*.py"):
        for imported in _imported_modules(path):
            if imported in forbidden:
                offenders.append(f"{path}: imports {imported}")

    assert offenders == []


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    return imported
