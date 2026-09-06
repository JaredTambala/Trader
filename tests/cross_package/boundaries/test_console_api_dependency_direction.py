"""Architecture contracts for the independent Console API package.

Subject: Dependency direction and current scaffold isolation of the outward-facing Console API.
Level: Cross-package repository architecture contract.
Collaborators: Real Console source parsed with Python AST and inspected as text; no imported application runtime.
Guarantees: Current health and compatibility paths remain independent while the package keeps explicit internal layers.
Non-goals: HTTP behavior, SQL result correctness, PostgreSQL authorization, and frontend contract generation.
"""

from __future__ import annotations

import ast
from pathlib import Path

from tests.cross_package.boundaries.import_scanning import imported_modules


PACKAGE_ROOT = Path("src/trader_console_api")
CURRENT_STARTUP_AND_HEALTH_PATHS = (
    PACKAGE_ROOT / "application.py",
    PACKAGE_ROOT / "configuration.py",
    PACKAGE_ROOT / "contracts.py",
    PACKAGE_ROOT / "routers" / "health.py",
    PACKAGE_ROOT / "services" / "health.py",
    PACKAGE_ROOT / "repositories" / "database.py",
    PACKAGE_ROOT / "repositories" / "schema_compatibility.py",
)
FORBIDDEN_IMPORT_ROOTS = (
    "trader",
    "trader_standard",
    "trader_research",
    "trader_mcp",
    "trader_agents",
    "trader_mlflow",
    "alpaca",
    "langgraph",
    "mcp",
    "mlflow",
)
FORBIDDEN_EFFECT_TEXT = (
    "PostgresEventStore",
    "build_event_store",
    "TraderService",
    "CREATE ",
    "ALTER ",
    "DROP ",
    "INSERT ",
    "UPDATE ",
    "DELETE ",
)


def test_current_startup_and_health_paths_import_no_execution_package() -> None:
    """Keep the current health slice independent without constraining future API features."""
    offenders: list[str] = []
    for path in CURRENT_STARTUP_AND_HEALTH_PATHS:
        for imported in imported_modules(path):
            if imported in FORBIDDEN_IMPORT_ROOTS or imported.startswith(
                tuple(f"{root}." for root in FORBIDDEN_IMPORT_ROOTS)
            ):
                offenders.append(f"{path}: imports {imported}")

    assert offenders == []


def test_current_startup_and_health_paths_contain_no_mutation_or_runtime_construction() -> None:
    """Keep the implemented health slice side-effect free without banning future commands."""
    offenders: list[str] = []
    for path in CURRENT_STARTUP_AND_HEALTH_PATHS:
        content = path.read_text(encoding="utf-8")
        for forbidden in FORBIDDEN_EFFECT_TEXT:
            if forbidden in content:
                offenders.append(f"{path}: contains {forbidden!r}")

    assert offenders == []


def test_console_api_internal_layers_follow_router_service_repository_direction() -> None:
    """Keep transport above orchestration and database access at the repository edge."""
    forbidden_relative_imports = {
        "routers": {"application", "configuration", "repositories"},
        "services": {"application", "routers"},
        "repositories": {"application", "routers", "services"},
    }
    forbidden_absolute_imports = {
        "routers": {"psycopg", "psycopg_pool"},
        "services": {"fastapi", "psycopg", "psycopg_pool"},
        "repositories": {"fastapi"},
    }
    offenders: list[str] = []
    for layer in ("routers", "services", "repositories"):
        for path in (PACKAGE_ROOT / layer).rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.level:
                    root = (node.module or "").split(".", maxsplit=1)[0]
                    if root in forbidden_relative_imports[layer]:
                        offenders.append(f"{path}: imports inward layer {root}")
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        root = alias.name.split(".", maxsplit=1)[0]
                        if root in forbidden_absolute_imports[layer]:
                            offenders.append(f"{path}: imports {root}")
                elif isinstance(node, ast.ImportFrom) and node.module:
                    root = node.module.split(".", maxsplit=1)[0]
                    if root in forbidden_absolute_imports[layer]:
                        offenders.append(f"{path}: imports {root}")

    assert offenders == []


def test_application_composes_router_without_declaring_http_handlers() -> None:
    """Keep the process entry point focused on wiring and lifespan ownership."""
    application = (PACKAGE_ROOT / "application.py").read_text(encoding="utf-8")

    assert "include_router(health_router)" in application
    assert "@app." not in application
