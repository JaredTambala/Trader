"""Contract tests for the repository's permanent test-ownership architecture.

Subject: Cross-package rules governing where test modules live and how they explain their contracts.
Level: Repository architecture contract.
Collaborators: Real filesystem paths and Python's AST parser; no product runtime or external service.
Guarantees: Every test has one approved owner/context, root exceptions stay closed, and narratives remain useful.
Non-goals: Reconstructing migration history, judging prose style automatically, or proving product behavior.
"""

from __future__ import annotations

import ast
from pathlib import Path
import re


REPO_ROOT = Path(__file__).resolve().parents[3]
TEST_ROOT = REPO_ROOT / "tests"
PACKAGE_OWNERS = frozenset(
    {
        "trader",
        "trader_standard",
        "trader_research",
        "trader_mlflow",
        "trader_mcp",
        "trader_agents",
    }
)
CROSS_PACKAGE_CONTEXTS = frozenset(
    {"boundaries", "documentation", "workflows", "qualification"}
)
OWNER_CONTEXTS = {
    "trader": frozenset(
        {
            "backtest",
            "broker",
            "config",
            "cycle",
            "event_store",
            "identifiers",
            "market_data",
            "operator",
            "portfolio",
            "predictions",
            "runtime",
        }
    ),
    "trader_standard": frozenset({"predictions", "risk", "strategies"}),
    "trader_research": frozenset(
        {
            "coding",
            "data",
            "experiments",
            "foundation",
            "governance",
            "knowledge",
            "methodology",
            "ml",
        }
    ),
    "trader_mlflow": frozenset({"inference"}),
    "trader_mcp": frozenset(
        {
            "catalogue_policy",
            "observability",
            "protocol",
            "runtime",
            "tools/agents",
            "tools/coding",
            "tools/data",
            "tools/experiments",
            "tools/methodology",
            "tools/ml",
        }
    ),
    "trader_agents": frozenset(
        {
            "application_runtime",
            "checkpointing",
            "contracts_state",
            "coordination",
            "mcp",
            "model_runtime",
            "observability",
            "specialists",
        }
    ),
    "cross_package": CROSS_PACKAGE_CONTEXTS,
}
ALLOWED_ROOT_FILES = frozenset({"__init__.py", "conftest.py"})
ALLOWED_ROOT_DIRECTORIES = PACKAGE_OWNERS | {"cross_package", "support"}
ALLOWED_SHARED_SUPPORT_FILES = frozenset({"__init__.py", "duckdb_store.py"})
MODULE_NARRATIVE_FIELDS = (
    "Subject:",
    "Level:",
    "Collaborators:",
    "Guarantees:",
    "Non-goals:",
)
CHECKPOINT_CODE_PATTERN = re.compile(
    r"^(?:orch|agent|imp|trd)[_-](?:\d+(?:[_-].*)?|[a-z]+(?:[_-][a-z0-9]+)*)$",
    re.IGNORECASE,
)
COHESION_TEST_THRESHOLD = 20
COHESION_LINE_THRESHOLD = 800


def test_repository_root_contains_only_approved_shared_assets() -> None:
    """Reject flat tests, migration registers, and unowned root-level support."""
    files = {
        path.name
        for path in TEST_ROOT.iterdir()
        if path.is_file() and path.name != ".DS_Store"
    }
    directories = {
        path.name
        for path in TEST_ROOT.iterdir()
        if path.is_dir() and path.name != "__pycache__"
    }
    support_files = {
        path.name
        for path in (TEST_ROOT / "support").iterdir()
        if path.is_file()
    }

    assert files == ALLOWED_ROOT_FILES
    assert directories == ALLOWED_ROOT_DIRECTORIES
    assert support_files == ALLOWED_SHARED_SUPPORT_FILES


def test_test_modules_use_approved_owner_and_context_directories() -> None:
    """Require every collected module to have one unambiguous package/context owner."""
    failures: list[str] = []
    for path in _target_layout_modules():
        parts = path.relative_to(TEST_ROOT).parts
        owner = parts[0]
        if owner not in PACKAGE_OWNERS | {"cross_package"}:
            failures.append(
                f"{path.relative_to(REPO_ROOT)} has unknown owner {owner!r}"
            )
            continue
        if len(parts) < 3:
            failures.append(
                f"{path.relative_to(REPO_ROOT)} must include an owning context directory"
            )
            continue
        relative_parts = parts[1:-1]
        matching_contexts = tuple(
            context
            for context in OWNER_CONTEXTS[owner]
            if relative_parts[: len(Path(context).parts)] == Path(context).parts
        )
        if len(matching_contexts) != 1:
            failures.append(
                f"{path.relative_to(REPO_ROOT)} must match exactly one approved context; "
                f"matched {matching_contexts!r}"
            )
    assert not failures, "\n".join(failures)


def test_test_directories_use_responsibility_names_not_delivery_codes() -> None:
    """Reject delivery-code directories across source and test architecture."""
    failures: list[str] = []
    roots = (TEST_ROOT, *(REPO_ROOT / "src" / owner for owner in PACKAGE_OWNERS))
    for root in roots:
        for path in root.rglob("*"):
            if not path.is_dir() or "__pycache__" in path.parts:
                continue
            if CHECKPOINT_CODE_PATTERN.fullmatch(path.name):
                failures.append(
                    f"{path.relative_to(REPO_ROOT)} uses a delivery-code directory"
                )
    assert not failures, "\n".join(failures)


def test_test_modules_define_the_narrative_contract() -> None:
    """Require each module to identify its boundary and evidentiary limits."""
    failures: list[str] = []
    for path in _target_layout_modules():
        module = _parse_module(path)
        docstring = ast.get_docstring(module) or ""
        missing = [field for field in MODULE_NARRATIVE_FIELDS if field not in docstring]
        if missing:
            failures.append(
                f"{path.relative_to(REPO_ROOT)} is missing module narrative fields: "
                f"{', '.join(missing)}"
            )
    assert not failures, "\n".join(failures)


def test_tests_explain_the_contract_they_protect() -> None:
    """Require every test to state more intent than its function name alone."""
    failures: list[str] = []
    for path in _target_layout_modules():
        for node in _test_functions(_parse_module(path)):
            docstring = ast.get_docstring(node)
            if docstring is None or len(docstring.split()) < 8:
                failures.append(
                    f"{path.relative_to(REPO_ROOT)}::{node.name} needs a contract-focused docstring"
                )
    assert not failures, "\n".join(failures)


def test_large_test_modules_record_a_cohesion_rationale() -> None:
    """Require an explicit rationale when size makes a module's cohesion questionable."""
    failures: list[str] = []
    for path in _target_layout_modules():
        module = _parse_module(path)
        test_count = len(_test_functions(module))
        line_count = len(path.read_text(encoding="utf-8").splitlines())
        if (
            test_count <= COHESION_TEST_THRESHOLD
            and line_count <= COHESION_LINE_THRESHOLD
        ):
            continue
        if "Cohesion rationale:" not in (ast.get_docstring(module) or ""):
            failures.append(
                f"{path.relative_to(REPO_ROOT)} has {test_count} tests/{line_count} lines "
                "without a Cohesion rationale"
            )
    assert not failures, "\n".join(failures)


def test_coordinator_data_pilot_has_one_canonical_test_node() -> None:
    """Keep the completed pilot at its target path after the source split."""
    target = (
        TEST_ROOT / "trader_agents/coordination/test_coordinator_data_observability.py"
    )
    node_name = "test_runtime_data_handoff_emits_correlated_observability_trajectory"
    target_nodes = {node.name for node in _test_functions(_parse_module(target))}

    assert node_name in target_nodes
    assert not (TEST_ROOT / "test_agent_runtime_foundation.py").exists()
    assert "tests.trader_agents.support" in target.read_text()


def test_mcp_concrete_dependencies_are_isolated_to_composition() -> None:
    """Keep provider selection out of MCP protocol and capability adapters."""
    composition_root = REPO_ROOT / "src/trader_mcp/runtime/composition.py"
    forbidden_module_prefixes = (
        "trader_mlflow",
        "trader_standard",
        "trader_research.infrastructure",
    )
    forbidden_core_names = {
        "NoOpEventStore",
        "build_config",
        "build_event_store",
        "load_yaml_config",
    }
    failures: list[str] = []
    for path in (REPO_ROOT / "src/trader_mcp").rglob("*.py"):
        if path == composition_root:
            continue
        for node in ast.walk(_parse_module(path)):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith(forbidden_module_prefixes):
                        failures.append(
                            f"{path.relative_to(REPO_ROOT)} imports concrete module "
                            f"{alias.name}"
                        )
                continue
            if not isinstance(node, ast.ImportFrom) or node.module is None:
                continue
            if node.module.startswith(forbidden_module_prefixes):
                failures.append(
                    f"{path.relative_to(REPO_ROOT)} imports concrete module {node.module}"
                )
            imported_core_names = forbidden_core_names.intersection(
                alias.name for alias in node.names
            )
            if imported_core_names:
                failures.append(
                    f"{path.relative_to(REPO_ROOT)} imports concrete constructor(s) "
                    f"{', '.join(sorted(imported_core_names))}"
                )

    assert composition_root.is_file()
    assert not failures, "\n".join(failures)


def test_mcp_source_modules_follow_the_responsibility_taxonomy() -> None:
    """Keep MCP source grouped by durable responsibility without flat shims."""
    package_root = REPO_ROOT / "src/trader_mcp"
    allowed_areas = {"catalogue", "observability", "protocol", "runtime", "tools"}
    required_modules = {
        "catalogue/definitions.py",
        "catalogue/policy.py",
        "observability/console.py",
        "protocol/adapters.py",
        "protocol/contracts.py",
        "runtime/composition.py",
        "runtime/server.py",
        "tools/adversarial.py",
        "tools/coding.py",
        "tools/coordination.py",
        "tools/evaluation.py",
        "tools/experiment_design.py",
        "tools/experiments.py",
        "tools/methodology.py",
        "tools/ml.py",
    }
    source_modules = {
        str(path.relative_to(package_root))
        for path in package_root.rglob("*.py")
        if "__pycache__" not in path.parts
    }
    misplaced = {
        relative_path
        for relative_path in source_modules
        if relative_path != "__init__.py"
        and relative_path.split("/", maxsplit=1)[0] not in allowed_areas
    }
    delivery_named = {
        part
        for relative_path in source_modules
        for part in Path(relative_path).parts[:-1]
        if CHECKPOINT_CODE_PATTERN.fullmatch(part)
    }

    assert required_modules <= source_modules
    assert not misplaced
    assert not delivery_named


def test_agent_source_modules_follow_the_control_responsibility_taxonomy() -> None:
    """Keep Agent source grouped by control role without flat compatibility shims."""
    package_root = REPO_ROOT / "src/trader_agents"
    allowed_areas = {
        "application",
        "checkpointing",
        "contracts",
        "coordination",
        "mcp",
        "model_runtime",
        "observability",
        "specialists",
    }
    required_modules = {
        "application/__init__.py",
        "application/cli.py",
        "application/runtime.py",
        "checkpointing/__init__.py",
        "checkpointing/domain.py",
        "checkpointing/postgres.py",
        "checkpointing/specialist.py",
        "contracts/__init__.py",
        "contracts/domain.py",
        "contracts/inputs.py",
        "coordination/__init__.py",
        "coordination/coordinator.py",
        "coordination/scheduler.py",
        "mcp/__init__.py",
        "mcp/catalogue.py",
        "mcp/client.py",
        "mcp/policy.py",
        "mcp/runtime.py",
        "model_runtime/__init__.py",
        "model_runtime/client.py",
        "model_runtime/profiles.py",
        "model_runtime/programs.py",
        "model_runtime/structured.py",
        "observability/__init__.py",
        "observability/console.py",
        "observability/emitter.py",
        "observability/events.py",
        "observability/projections.py",
        "observability/tracing.py",
        "specialists/__init__.py",
        "specialists/data_research.py",
        "specialists/strategy_engineering.py",
    }
    source_modules = {
        str(path.relative_to(package_root))
        for path in package_root.rglob("*.py")
        if "__pycache__" not in path.parts
    }
    misplaced = {
        relative_path
        for relative_path in source_modules
        if relative_path != "__init__.py"
        and relative_path.split("/", maxsplit=1)[0] not in allowed_areas
    }
    source_areas = {
        path.name
        for path in package_root.iterdir()
        if path.is_dir() and path.name not in {"__pycache__", "docs"}
    }
    delivery_named = {
        part
        for relative_path in source_modules
        for part in Path(relative_path).parts[:-1]
        if CHECKPOINT_CODE_PATTERN.fullmatch(part)
    }

    assert required_modules <= source_modules
    assert source_areas == allowed_areas
    assert not misplaced
    assert not delivery_named


def _target_layout_modules() -> tuple[Path, ...]:
    """Return every test module below an approved ownership directory."""
    return tuple(
        sorted(
            path for path in TEST_ROOT.rglob("test_*.py") if path.parent != TEST_ROOT
        )
    )


def _parse_module(path: Path) -> ast.Module:
    """Parse one test module for structural contract checks."""
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _test_functions(
    module: ast.Module,
) -> tuple[ast.FunctionDef | ast.AsyncFunctionDef, ...]:
    """Return module-level pytest functions without collecting nested helpers."""
    return tuple(
        node
        for node in module.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
    )
