from __future__ import annotations

import ast
from pathlib import Path


REMOVED_COMPAT_SURFACES = {
    Path("src/trader/alpaca_market_data.py"),
    Path("src/trader/api.py"),
    Path("src/trader/data.py"),
    Path("src/trader/data_quality.py"),
    Path("src/trader/knowledge_store.py"),
    Path("src/trader/market_data_backfill.py"),
    Path("src/trader/market_data_queries.py"),
    Path("src/trader/market_data_replay.py"),
    Path("src/trader/market_data_stream.py"),
    Path("src/trader/metrics.py"),
    Path("src/trader/notifications.py"),
    Path("src/trader/order_recovery.py"),
    Path("src/trader/research.py"),
    Path("src/trader/runtime_status.py"),
    Path("src/trader/sample_data.py"),
    Path("src/trader/strategy.py"),
    Path("src/trader/tools"),
    Path("src/trader/trader_service.py"),
}


REMOVED_COMPAT_IMPORTS = {
    "trader.alpaca_market_data",
    "trader.api",
    "trader.data",
    "trader.data_quality",
    "trader.knowledge_store",
    "trader.market_data_backfill",
    "trader.market_data_queries",
    "trader.market_data_replay",
    "trader.market_data_stream",
    "trader.metrics",
    "trader.notifications",
    "trader.order_recovery",
    "trader.research",
    "trader.runtime_status",
    "trader.sample_data",
    "trader.strategy",
    "trader.tools",
    "trader.trader_service",
}

REMOVED_RESEARCH_FLAT_MODULES = {
    Path("src/trader_research/backtests.py"),
    Path("src/trader_research/cpp_kernel_artifacts.py"),
    Path("src/trader_research/data.py"),
    Path("src/trader_research/evaluation.py"),
    Path("src/trader_research/math_domain.py"),
    Path("src/trader_research/math_registry.py"),
    Path("src/trader_research/math_tools.py"),
    Path("src/trader_research/method_packages.py"),
    Path("src/trader_research/multiple_testing.py"),
    Path("src/trader_research/risk_managers.py"),
    Path("src/trader_research/signal_diagnostics.py"),
    Path("src/trader_research/strategies.py"),
    Path("src/trader_research/strategy_validation.py"),
}

REMOVED_RESEARCH_FLAT_IMPORTS = {
    "trader_research.cpp_kernel_artifacts",
    "trader_research.math_domain",
    "trader_research.math_registry",
    "trader_research.math_tools",
    "trader_research.method_packages",
    "trader_research.multiple_testing",
    "trader_research.signal_diagnostics",
    "trader_research.strategies",
    "trader_research.strategy_validation",
}


def test_removed_trader_compatibility_surfaces_do_not_exist() -> None:
    offenders = [str(path) for path in sorted(REMOVED_COMPAT_SURFACES) if path.exists()]
    assert offenders == []


def test_repo_code_does_not_import_removed_trader_compatibility_surfaces() -> None:
    offenders: list[str] = []
    for root in (Path("src"), Path("tests"), Path("examples")):
        for path in root.rglob("*.py"):
            if path == Path("tests/test_package_boundaries.py"):
                continue
            for imported in _imported_modules(path):
                if imported in REMOVED_COMPAT_IMPORTS or any(
                    imported.startswith(f"{module}.") for module in REMOVED_COMPAT_IMPORTS
                ):
                    offenders.append(f"{path}: imports {imported}")
    for path in Path(".").glob("run_*.py"):
        for imported in _imported_modules(path):
            if imported in REMOVED_COMPAT_IMPORTS or any(
                imported.startswith(f"{module}.") for module in REMOVED_COMPAT_IMPORTS
            ):
                offenders.append(f"{path}: imports {imported}")

    assert offenders == []


def test_removed_trader_research_flat_service_modules_do_not_exist() -> None:
    offenders = [str(path) for path in sorted(REMOVED_RESEARCH_FLAT_MODULES) if path.exists()]
    assert offenders == []


def test_repo_code_uses_canonical_trader_research_capability_packages() -> None:
    offenders: list[str] = []
    for root in (Path("src"), Path("tests"), Path("examples")):
        for path in root.rglob("*.py"):
            if path == Path("tests/test_package_boundaries.py"):
                continue
            for imported in _imported_modules(path):
                if imported in REMOVED_RESEARCH_FLAT_IMPORTS or any(
                    imported.startswith(f"{module}.") for module in REMOVED_RESEARCH_FLAT_IMPORTS
                ):
                    offenders.append(f"{path}: imports {imported}")

    assert offenders == []


def test_trader_package_does_not_depend_on_research_agent_packages() -> None:
    offenders: list[str] = []
    for path in Path("src/trader").rglob("*.py"):
        for imported in _imported_modules(path):
            if imported in {"trader_research", "trader_mcp", "trader_agents"} or imported.startswith(
                ("trader_research.", "trader_mcp.", "trader_agents.")
            ):
                offenders.append(f"{path}: imports {imported}")

    assert offenders == []


def test_trader_research_does_not_import_mcp_or_langgraph_agent_packages() -> None:
    offenders: list[str] = []
    for path in Path("src/trader_research").rglob("*.py"):
        for imported in _imported_modules(path):
            if imported in {"trader_mcp", "trader_agents"} or imported.startswith(("trader_mcp.", "trader_agents.")):
                offenders.append(f"{path}: imports {imported}")

    assert offenders == []


def test_canonical_experiment_packages_do_not_import_knowledge_or_candidate_domains() -> None:
    roots = (
        Path("src/trader_research/implementations"),
        Path("src/trader_research/specifications"),
        Path("src/trader_research/optimization"),
        Path("src/trader_research/tracking"),
        Path("src/trader_research/adversarial"),
    )
    files = [path for root in roots for path in root.rglob("*.py")]
    files.extend(
        (
            Path("src/trader_research/backtests/execution.py"),
            Path("src/trader_research/evaluation/optimization.py"),
        )
    )
    forbidden = (
        "trader_research.knowledge",
        "trader_research.strategy_candidates",
        "trader_research.risk_managers",
        "trader_research.portfolio_stacks",
        "trader_research.methods",
    )
    offenders: list[str] = []
    for path in files:
        for imported in _imported_modules(path):
            if imported.startswith(forbidden):
                offenders.append(f"{path}: imports {imported}")

    assert offenders == []


def test_trader_agents_do_not_import_data_platform_or_mcp_server_boundaries() -> None:
    forbidden = {
        "trader.event_store",
        "trader.market_data.queries",
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
