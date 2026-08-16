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

RETIRED_CANDIDATE_SURFACES = {
    Path("src/trader_research/strategy_candidates"),
    Path("src/trader_research/risk_managers"),
    Path("src/trader_research/portfolio_stacks"),
    Path("src/trader_research/experiments/backtests/services.py"),
    Path("src/trader_research/review/evaluation/performance.py"),
}

RETIRED_CANDIDATE_IMPORTS = {
    "trader_research.strategy_candidates",
    "trader_research.risk_managers",
    "trader_research.portfolio_stacks",
    "trader_research.experiments.backtests.services",
    "trader_research.review.evaluation.performance",
}

RETIRED_LEGACY_RESEARCH_SURFACES = {
    Path("src/trader_research/artifacts.py"),
    Path("src/trader_research/discovery.py"),
    Path("src/trader_research/promotion.py"),
    Path("src/trader_research/recommendations.py"),
    Path("src/trader_research/research.py"),
    Path("src/trader_research/suites.py"),
    Path("run_compare_results.py"),
    Path("run_prepare_paper_promotion.py"),
    Path("run_research_discovery.py"),
    Path("run_research_experiment.py"),
    Path("run_research_recommendations.py"),
}

RETIRED_LEGACY_RESEARCH_IMPORTS = {
    "trader_research.artifacts",
    "trader_research.discovery",
    "trader_research.promotion",
    "trader_research.recommendations",
    "trader_research.research",
    "trader_research.suites",
}

RETIRED_RESEARCH_HUBS = {
    Path("src/trader_research/agents.py"),
    Path("src/trader_research/artifact_store.py"),
    Path("src/trader_research/contracts.py"),
    Path("src/trader_research/domain.py"),
    Path("src/trader_research/postgres_artifact_store.py"),
}

RETIRED_RESEARCH_HUB_IMPORTS = {
    "trader_research.agents",
    "trader_research.artifact_store",
    "trader_research.contracts",
    "trader_research.domain",
    "trader_research.postgres_artifact_store",
}

RETIRED_METHODOLOGY_SURFACES = {
    Path("src/trader_research/methods"),
    Path("src/trader_research/method_implementations"),
    Path("src/trader_research/knowledge/domain.py"),
    Path("src/trader_research/method_contracts_seed.json"),
    Path("src/trader_research/methodology/method_contracts_seed.json"),
}

RETIRED_METHODOLOGY_IMPORTS = {
    "trader_research.methods",
    "trader_research.method_implementations",
}

RETIRED_EXPERIMENT_SURFACES = {
    Path("src/trader_research/implementations"),
    Path("src/trader_research/specifications"),
    Path("src/trader_research/backtests"),
    Path("src/trader_research/optimization"),
    Path("src/trader_research/tracking"),
}

RETIRED_EXPERIMENT_IMPORTS = {
    "trader_research.implementations",
    "trader_research.specifications",
    "trader_research.backtests",
    "trader_research.optimization",
    "trader_research.tracking",
}

RETIRED_REVIEW_SURFACES = {
    Path("src/trader_research/evaluation"),
    Path("src/trader_research/adversarial"),
}

RETIRED_REVIEW_IMPORTS = {
    "trader_research.evaluation",
    "trader_research.adversarial",
}


def test_removed_trader_compatibility_surfaces_do_not_exist() -> None:
    offenders = [str(path) for path in sorted(REMOVED_COMPAT_SURFACES) if path.exists()]
    assert offenders == []


def test_retired_candidate_architecture_does_not_exist() -> None:
    offenders = [
        str(path) for path in sorted(RETIRED_CANDIDATE_SURFACES) if path.exists()
    ]
    assert offenders == []


def test_retired_legacy_research_surfaces_do_not_exist() -> None:
    offenders = [
        str(path) for path in sorted(RETIRED_LEGACY_RESEARCH_SURFACES) if path.exists()
    ]
    assert offenders == []


def test_retired_research_dependency_hubs_do_not_exist() -> None:
    offenders = [str(path) for path in sorted(RETIRED_RESEARCH_HUBS) if path.exists()]
    assert offenders == []


def test_retired_methodology_surfaces_do_not_exist() -> None:
    offenders = [str(path) for path in sorted(RETIRED_METHODOLOGY_SURFACES) if path.exists()]
    assert offenders == []


def test_retired_top_level_experiment_packages_do_not_exist() -> None:
    offenders = [
        str(path) for path in sorted(RETIRED_EXPERIMENT_SURFACES) if path.exists()
    ]
    assert offenders == []


def test_repo_code_does_not_import_retired_top_level_experiment_packages() -> None:
    offenders: list[str] = []
    for root in (Path("src"), Path("tests"), Path("examples")):
        for path in root.rglob("*.py"):
            if path == Path("tests/test_package_boundaries.py"):
                continue
            for imported in _imported_modules(path):
                if imported in RETIRED_EXPERIMENT_IMPORTS or any(
                    imported.startswith(f"{module}.")
                    for module in RETIRED_EXPERIMENT_IMPORTS
                ):
                    offenders.append(f"{path}: imports {imported}")
    assert offenders == []


def test_retired_top_level_review_packages_and_imports_do_not_exist() -> None:
    assert [
        str(path) for path in sorted(RETIRED_REVIEW_SURFACES) if path.exists()
    ] == []
    offenders: list[str] = []
    for root in (Path("src"), Path("tests"), Path("examples")):
        for path in root.rglob("*.py"):
            if path == Path("tests/test_package_boundaries.py"):
                continue
            for imported in _imported_modules(path):
                if imported in RETIRED_REVIEW_IMPORTS or any(
                    imported.startswith(f"{module}.")
                    for module in RETIRED_REVIEW_IMPORTS
                ):
                    offenders.append(f"{path}: imports {imported}")
    assert offenders == []


def test_experiment_core_does_not_import_optional_or_unrelated_contexts() -> None:
    forbidden = (
        "alpaca",
        "mlflow",
        "optuna",
        "trader_mcp",
        "trader_agents",
        "trader_research.infrastructure",
        "trader_research.knowledge",
        "trader_research.methodology",
        "trader_research.review",
    )
    offenders: list[str] = []
    for path in Path("src/trader_research/experiments").rglob("*.py"):
        for imported in _imported_modules(path):
            if imported.startswith(forbidden):
                offenders.append(f"{path}: imports {imported}")
    assert offenders == []


def test_composition_layers_use_only_the_public_experiments_facade() -> None:
    roots = (Path("src/trader_mcp"), Path("src/trader_agents"))
    offenders: list[str] = []
    for root in roots:
        for path in root.rglob("*.py"):
            for imported in _imported_modules(path):
                if imported.startswith("trader_research.experiments."):
                    offenders.append(f"{path}: imports {imported}")
    assert offenders == []


def test_mcp_and_agents_use_public_bounded_context_facades() -> None:
    public_contexts = (
        "trader_research.foundation",
        "trader_research.governance",
        "trader_research.data",
        "trader_research.knowledge",
        "trader_research.methodology",
        "trader_research.experiments",
        "trader_research.review",
    )
    offenders: list[str] = []
    for root in (Path("src/trader_mcp"), Path("src/trader_agents")):
        for path in root.rglob("*.py"):
            for imported in _imported_modules(path):
                for public_context in public_contexts:
                    if imported.startswith(f"{public_context}."):
                        offenders.append(f"{path}: imports {imported}")
    assert offenders == []


def test_research_bounded_context_import_graph_is_directional_and_acyclic() -> None:
    context_paths = {
        "foundation": Path("src/trader_research/foundation"),
        "governance": Path("src/trader_research/governance"),
        "data": Path("src/trader_research/data"),
        "knowledge": Path("src/trader_research/knowledge"),
        "methodology": Path("src/trader_research/methodology"),
        "experiments": Path("src/trader_research/experiments"),
        "review": Path("src/trader_research/review"),
        "infrastructure": Path("src/trader_research/infrastructure"),
    }
    allowed_edges = {
        ("governance", "foundation"),
        ("data", "foundation"),
        ("knowledge", "foundation"),
        ("knowledge", "governance"),
        ("methodology", "foundation"),
        ("methodology", "governance"),
        ("methodology", "knowledge"),
        ("experiments", "foundation"),
        ("experiments", "governance"),
        ("review", "foundation"),
        ("review", "governance"),
        ("review", "experiments"),
        ("infrastructure", "foundation"),
        ("infrastructure", "governance"),
        ("infrastructure", "data"),
        ("infrastructure", "experiments"),
    }
    edges: set[tuple[str, str]] = set()
    for owner, root in context_paths.items():
        for path in root.rglob("*.py"):
            for imported in _imported_modules(path):
                prefix = "trader_research."
                if not imported.startswith(prefix):
                    continue
                target = imported.removeprefix(prefix).split(".", 1)[0]
                if target in context_paths and target != owner:
                    edges.add((owner, target))

    assert sorted(edges.difference(allowed_edges)) == []

    adjacency = {
        context: {target for owner, target in edges if owner == context}
        for context in context_paths
    }

    def reaches_origin(origin: str, current: str, visited: set[str]) -> bool:
        for target in adjacency[current]:
            if target == origin:
                return True
            if target not in visited and reaches_origin(
                origin, target, {*visited, target}
            ):
                return True
        return False

    cycles = [
        context
        for context in context_paths
        if reaches_origin(context, context, {context})
    ]
    assert cycles == []


def test_review_imports_only_the_immutable_experiment_read_port() -> None:
    allowed = "trader_research.experiments.reads"
    offenders: list[str] = []
    for path in Path("src/trader_research/review").rglob("*.py"):
        for imported in _imported_modules(path):
            if imported.startswith("trader_research.experiments") and imported != allowed:
                offenders.append(f"{path}: imports {imported}")
    assert offenders == []


def test_review_never_persists_experiment_owned_artifact_types() -> None:
    forbidden_artifact_names = {
        "IMPLEMENTATION_VERSION",
        "IMPLEMENTATION_VALIDATION_REPORT",
        "STRATEGY_SPECIFICATION",
        "STRATEGY_SPECIFICATION_VALIDATION_REPORT",
        "RISK_STACK_SPECIFICATION",
        "RISK_STACK_SPECIFICATION_VALIDATION_REPORT",
        "BACKTEST_SPECIFICATION",
        "BACKTEST_SPECIFICATION_VALIDATION_REPORT",
        "BACKTEST_RUN",
        "PARAMETER_OPTIMIZATION_PLAN",
        "PARAMETER_OPTIMIZATION_RUN",
        "PARAMETER_OPTIMIZATION_TRIAL",
        "EXPERIMENT_TRACKING_PROJECTION_REPORT",
    }
    offenders: list[str] = []
    for path in Path("src/trader_research/review").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr != "save_artifact":
                continue
            artifact_keyword = next(
                (item for item in node.keywords if item.arg == "artifact_type"), None
            )
            if (
                artifact_keyword is not None
                and isinstance(artifact_keyword.value, ast.Name)
                and artifact_keyword.value.id in forbidden_artifact_names
            ):
                offenders.append(
                    f"{path}: persists {artifact_keyword.value.id}"
                )
    assert offenders == []


def test_repo_code_does_not_import_retired_methodology_packages() -> None:
    offenders: list[str] = []
    for root in (Path("src"), Path("tests"), Path("examples")):
        for path in root.rglob("*.py"):
            if path == Path("tests/test_package_boundaries.py"):
                continue
            for imported in _imported_modules(path):
                if imported in RETIRED_METHODOLOGY_IMPORTS or any(
                    imported.startswith(f"{module}.") for module in RETIRED_METHODOLOGY_IMPORTS
                ):
                    offenders.append(f"{path}: imports {imported}")
    assert offenders == []


def test_methodology_depends_only_on_public_approved_card_knowledge_port() -> None:
    offenders: list[str] = []
    allowed = "trader_research.knowledge.approved_cards"
    for path in Path("src/trader_research/methodology").rglob("*.py"):
        for imported in _imported_modules(path):
            if imported.startswith("trader_research.knowledge") and imported != allowed:
                offenders.append(f"{path}: imports {imported}")
    assert offenders == []


def test_retired_method_card_symbols_are_absent_from_product_code() -> None:
    retired_terms = (
        "RichMethodCard",
        "RICH_METHOD_CARD_FORMAT",
        "knowledge_create_rich_method_card_draft",
        "create_rich_method_card_draft",
        "save_method_contract",
        "list_persisted_method_contracts",
    )
    offenders: list[str] = []
    for path in Path("src/trader_research").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for term in retired_terms:
            if term in text:
                offenders.append(f"{path}: contains {term}")
    for path in Path("src/trader_mcp").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for term in retired_terms:
            if term in text:
                offenders.append(f"{path}: contains {term}")
    assert offenders == []


def test_repo_code_does_not_import_retired_research_dependency_hubs() -> None:
    offenders: list[str] = []
    for root in (Path("src"), Path("tests"), Path("examples")):
        for path in root.rglob("*.py"):
            if path == Path("tests/test_package_boundaries.py"):
                continue
            for imported in _imported_modules(path):
                if imported in RETIRED_RESEARCH_HUB_IMPORTS or any(
                    imported.startswith(f"{module}.")
                    for module in RETIRED_RESEARCH_HUB_IMPORTS
                ):
                    offenders.append(f"{path}: imports {imported}")
    assert offenders == []


def test_foundation_depends_only_on_python_standard_library() -> None:
    offenders: list[str] = []
    for path in Path("src/trader_research/foundation").rglob("*.py"):
        for imported in _imported_modules(path):
            if imported.startswith(
                ("trader", "trader_research", "trader_mcp", "trader_agents")
            ):
                offenders.append(f"{path}: imports {imported}")
    assert offenders == []


def test_orchestration_contracts_do_not_import_service_implementations() -> None:
    forbidden = (
        "trader",
        "trader_agents",
        "trader_mcp",
        "trader_research.data",
        "trader_research.experiments",
        "trader_research.infrastructure",
        "trader_research.knowledge",
        "trader_research.methodology",
        "trader_research.ml",
        "trader_research.review",
    )
    offenders: list[str] = []
    for path in Path("src/trader_research/governance/orchestration").glob("*.py"):
        for imported in sorted(_imported_modules(path)):
            if imported in forbidden or imported.startswith(
                tuple(f"{prefix}." for prefix in forbidden)
            ):
                offenders.append(f"{path}: imports {imported}")

    assert offenders == []


def test_repo_code_does_not_import_retired_legacy_research_surfaces() -> None:
    offenders: list[str] = []
    for root in (Path("src"), Path("tests"), Path("examples")):
        for path in root.rglob("*.py"):
            if path == Path("tests/test_package_boundaries.py"):
                continue
            for imported in _imported_modules(path):
                if imported in RETIRED_LEGACY_RESEARCH_IMPORTS or any(
                    imported.startswith(f"{module}.")
                    for module in RETIRED_LEGACY_RESEARCH_IMPORTS
                ):
                    offenders.append(f"{path}: imports {imported}")
    assert offenders == []


def test_repo_code_does_not_import_retired_candidate_architecture() -> None:
    offenders: list[str] = []
    for root in (Path("src"), Path("tests"), Path("examples")):
        for path in root.rglob("*.py"):
            if path == Path("tests/test_package_boundaries.py"):
                continue
            for imported in _imported_modules(path):
                if imported in RETIRED_CANDIDATE_IMPORTS or any(
                    imported.startswith(f"{module}.")
                    for module in RETIRED_CANDIDATE_IMPORTS
                ):
                    offenders.append(f"{path}: imports {imported}")
    assert offenders == []


def test_repo_code_does_not_import_removed_trader_compatibility_surfaces() -> None:
    offenders: list[str] = []
    for root in (Path("src"), Path("tests"), Path("examples")):
        for path in root.rglob("*.py"):
            if path == Path("tests/test_package_boundaries.py"):
                continue
            for imported in _imported_modules(path):
                if imported in REMOVED_COMPAT_IMPORTS or any(
                    imported.startswith(f"{module}.")
                    for module in REMOVED_COMPAT_IMPORTS
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
    offenders = [
        str(path) for path in sorted(REMOVED_RESEARCH_FLAT_MODULES) if path.exists()
    ]
    assert offenders == []


def test_repo_code_uses_canonical_trader_research_capability_packages() -> None:
    offenders: list[str] = []
    for root in (Path("src"), Path("tests"), Path("examples")):
        for path in root.rglob("*.py"):
            if path == Path("tests/test_package_boundaries.py"):
                continue
            for imported in _imported_modules(path):
                if imported in REMOVED_RESEARCH_FLAT_IMPORTS or any(
                    imported.startswith(f"{module}.")
                    for module in REMOVED_RESEARCH_FLAT_IMPORTS
                ):
                    offenders.append(f"{path}: imports {imported}")

    assert offenders == []


def test_trader_package_does_not_depend_on_research_agent_packages() -> None:
    offenders: list[str] = []
    for path in Path("src/trader").rglob("*.py"):
        for imported in _imported_modules(path):
            if imported in {
                "trader_research",
                "trader_mcp",
                "trader_agents",
                "trader_mlflow",
            } or imported.startswith(
                (
                    "trader_research.",
                    "trader_mcp.",
                    "trader_agents.",
                    "trader_mlflow.",
                )
            ):
                offenders.append(f"{path}: imports {imported}")

    assert offenders == []


def test_mlflow_runtime_dependencies_stay_in_optional_adapter_package() -> None:
    offenders: list[str] = []
    for root in (Path("src/trader"), Path("src/trader_standard")):
        for path in root.rglob("*.py"):
            for imported in _imported_modules(path):
                if imported in {"mlflow", "pandas", "trader_mlflow"} or imported.startswith(
                    ("mlflow.", "pandas.", "trader_mlflow.")
                ):
                    offenders.append(f"{path}: imports {imported}")
    allowed_research_adapter = Path(
        "src/trader_research/infrastructure/providers/mlflow.py"
    )
    for path in Path("src/trader_research").rglob("*.py"):
        for imported in _imported_modules(path):
            if imported == "trader_mlflow" or imported.startswith("trader_mlflow."):
                offenders.append(f"{path}: imports {imported}")
            if path != allowed_research_adapter and (
                imported in {"mlflow", "pandas"}
                or imported.startswith(("mlflow.", "pandas."))
            ):
                offenders.append(f"{path}: imports {imported}")

    assert offenders == []


def test_trader_research_does_not_import_mcp_or_langgraph_agent_packages() -> None:
    offenders: list[str] = []
    for path in Path("src/trader_research").rglob("*.py"):
        for imported in _imported_modules(path):
            if imported in {"trader_mcp", "trader_agents"} or imported.startswith(
                ("trader_mcp.", "trader_agents.")
            ):
                offenders.append(f"{path}: imports {imported}")

    assert offenders == []


def test_canonical_experiment_packages_do_not_import_knowledge_or_candidate_domains() -> (
    None
):
    roots = (
        Path("src/trader_research/experiments"),
        Path("src/trader_research/review"),
    )
    files = [path for root in roots for path in root.rglob("*.py")]
    forbidden = (
        "trader_research.knowledge",
        "trader_research.strategy_candidates",
        "trader_research.risk_managers",
        "trader_research.portfolio_stacks",
        "trader_research.methodology",
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


def test_workflow_checkpointing_depends_only_on_governance_contracts() -> None:
    allowed_research_imports = {
        "trader_research.foundation",
        "trader_research.governance",
        "trader_research.governance.handoffs",
    }
    offenders: list[str] = []
    for path in Path("src/trader_agents/checkpointing").rglob("*.py"):
        for imported in _imported_modules(path):
            if imported in {"trader", "trader_mcp"} or imported.startswith(
                ("trader.", "trader_mcp.")
            ):
                offenders.append(f"{path}: imports {imported}")
            if (
                imported.startswith("trader_research.")
                and imported not in allowed_research_imports
            ):
                offenders.append(f"{path}: imports {imported}")

    assert offenders == []


def test_workflow_compiler_and_executor_do_not_import_domain_services() -> None:
    forbidden = (
        "trader",
        "trader_mcp.server",
        "trader_research.data",
        "trader_research.experiments",
        "trader_research.infrastructure",
        "trader_research.knowledge",
        "trader_research.methodology",
        "trader_research.ml",
        "trader_research.review",
    )
    offenders: list[str] = []
    for path in Path("src/trader_agents/orchestration").rglob("*.py"):
        for imported in _imported_modules(path):
            if imported in forbidden or imported.startswith(
                tuple(f"{prefix}." for prefix in forbidden)
            ):
                offenders.append(f"{path}: imports {imported}")

    assert offenders == []


def test_data_context_has_one_public_facade_and_no_retired_provider_package() -> None:
    retired_paths = (
        Path("src/trader_research/data/services.py"),
        Path("src/trader_research/providers"),
    )
    assert [str(path) for path in retired_paths if path.exists()] == []

    forbidden_data_imports = (
        "alpaca",
        "trader_mcp",
        "trader_agents",
        "trader_research.knowledge",
        "trader_research.methodology",
        "trader_research.experiments",
        "trader_research.review",
    )
    offenders: list[str] = []
    for path in Path("src/trader_research/data").rglob("*.py"):
        for imported in _imported_modules(path):
            if imported.startswith(forbidden_data_imports):
                offenders.append(f"{path}: imports {imported}")

    assert offenders == []


def test_outer_layers_import_data_only_through_its_public_facade() -> None:
    roots = (Path("src/trader_mcp"), Path("src/trader_agents"))
    offenders: list[str] = []
    for root in roots:
        for path in root.rglob("*.py"):
            for imported in _imported_modules(path):
                if imported.startswith("trader_research.data."):
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
