"""Bounded runtime helpers for validated DB-backed implementations."""

from __future__ import annotations

import ast
import builtins
from datetime import datetime, timezone
import inspect
import json
import math
import types
from typing import Any, Mapping

from trader.risk import RiskContext, RiskManager
from trader.strategies import Strategy
from trader_research.artifact_store import load_module_from_source

from .domain import ImplementationVersion


_ALLOWED_IMPORT_ROOTS = frozenset(
    {
        "collections",
        "dataclasses",
        "datetime",
        "decimal",
        "enum",
        "functools",
        "itertools",
        "math",
        "statistics",
        "trader",
        "trader_standard",
        "typing",
    }
)
_FORBIDDEN_CALLS = frozenset({"compile", "eval", "exec", "open", "__import__"})
_FORBIDDEN_ATTRIBUTES = frozenset({"popen", "remove", "rmdir", "system", "unlink"})
_FORBIDDEN_OBJECTIVE_NAMES = _FORBIDDEN_CALLS | frozenset(
    {"__builtins__", "breakpoint", "dir", "help", "memoryview"}
)
_OBJECTIVE_IMPORT_ROOTS = frozenset({"math", "statistics", "typing"})
_OBJECTIVE_BUILTINS = {
    name: getattr(builtins, name)
    for name in (
        "abs",
        "all",
        "any",
        "bool",
        "dict",
        "enumerate",
        "Exception",
        "float",
        "int",
        "isinstance",
        "len",
        "list",
        "map",
        "max",
        "min",
        "range",
        "reversed",
        "round",
        "set",
        "sorted",
        "str",
        "sum",
        "tuple",
        "ValueError",
        "zip",
    )
}


def source_safety_blockers(implementation: ImplementationVersion) -> tuple[str, ...]:
    """Return static blockers for imports and direct unsafe operations."""
    blockers: list[str] = []
    try:
        tree = ast.parse(implementation.source_code)
    except SyntaxError as exc:
        return (f"source code does not compile: {exc}",)
    dependency_roots = {
        value.split("[", 1)[0].split("=", 1)[0].split(">", 1)[0].split("<", 1)[0].replace("-", "_")
        for value in implementation.dependencies
    }
    allowed_roots = _ALLOWED_IMPORT_ROOTS | dependency_roots
    if implementation.implementation_kind == "optimization_objective":
        allowed_roots = _OBJECTIVE_IMPORT_ROOTS
        blockers.extend(_objective_module_blockers(tree))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots = [alias.name.split(".", 1)[0] for alias in node.names]
            blockers.extend(f"import is not allowed: {root}" for root in roots if root not in allowed_roots)
        elif isinstance(node, ast.ImportFrom):
            root = str(node.module or "").split(".", 1)[0]
            if not root or root not in allowed_roots:
                blockers.append(f"import is not allowed: {root or '<relative>'}")
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in _FORBIDDEN_CALLS:
                blockers.append(f"unsafe call is not allowed: {node.func.id}")
            if isinstance(node.func, ast.Attribute) and node.func.attr.lower() in _FORBIDDEN_ATTRIBUTES:
                blockers.append(f"unsafe attribute call is not allowed: {node.func.attr}")
            if (
                implementation.implementation_kind == "optimization_objective"
                and isinstance(node.func, ast.Name)
                and node.func.id in {"getattr", "globals", "input", "locals", "setattr", "vars"}
            ):
                blockers.append(f"unsafe objective call is not allowed: {node.func.id}")
        if implementation.implementation_kind == "optimization_objective":
            if isinstance(node, ast.Name) and node.id in _FORBIDDEN_OBJECTIVE_NAMES:
                blockers.append(f"unsafe objective name is not allowed: {node.id}")
            if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
                blockers.append(f"dunder objective attribute is not allowed: {node.attr}")
    return tuple(sorted(set(blockers)))


def load_implementation(implementation: ImplementationVersion) -> object:
    """Load one already source-hash-validated implementation in memory."""
    suffix = "".join(character for character in implementation.implementation_version_id if character.isalnum())[-20:]
    if implementation.implementation_kind == "optimization_objective":
        return _load_objective_module(
            f"_trader_objective_{suffix}",
            implementation.source_code,
            filename=f"research://postgres/implementation_version/{implementation.implementation_version_id}",
        )
    return load_module_from_source(
        f"_trader_implementation_{suffix}",
        implementation.source_code,
        filename=f"research://postgres/implementation_version/{implementation.implementation_version_id}",
    )


def instantiate_strategy(
    implementation: ImplementationVersion,
    *,
    symbols: list[str],
    asset_class: str,
    timeframe: str,
    parameters: Mapping[str, Any],
    sizing: Mapping[str, Any] | None = None,
) -> Strategy:
    """Instantiate a strategy factory using only declared context and parameters."""
    module = load_implementation(implementation)
    factory = _factory(module, implementation)
    kwargs = {
        "symbols": symbols,
        "asset_class": asset_class,
        "timeframe": timeframe,
        **dict(parameters),
        **dict(sizing or {}),
    }
    instance = _call_supported(factory, kwargs)
    if not isinstance(instance, Strategy):
        raise ValueError("implementation factory did not return trader.strategies.Strategy")
    return instance


def instantiate_risk_manager(
    implementation: ImplementationVersion,
    *,
    parameters: Mapping[str, Any],
) -> RiskManager:
    """Instantiate a risk-manager factory using declared parameters."""
    module = load_implementation(implementation)
    factory = _factory(module, implementation)
    signature = inspect.signature(factory)
    if "parameters" in signature.parameters:
        instance = factory(parameters=dict(parameters))
    else:
        instance = _call_supported(factory, dict(parameters))
    if not isinstance(instance, RiskManager):
        raise ValueError("implementation factory did not return trader.risk.RiskManager")
    return instance


def evaluate_objective(
    implementation: ImplementationVersion,
    observation: Mapping[str, Any],
) -> tuple[float, Mapping[str, Any]]:
    """Evaluate a validated optimization objective over the closed observation."""
    from trader_research.optimization.contracts import OptimizationObservation

    closed_observation = OptimizationObservation.from_mapping(observation).to_dict()
    module = load_implementation(implementation)
    function = _factory(module, implementation)
    result = function(closed_observation)
    diagnostics: Mapping[str, Any] = {}
    if isinstance(result, Mapping):
        value = result.get("value")
        diagnostics_value = result.get("diagnostics") or {}
        if isinstance(diagnostics_value, Mapping):
            diagnostics = dict(diagnostics_value)
    else:
        value = result
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("optimization objective must return a numeric value or {value, diagnostics}")
    if not math.isfinite(float(value)):
        raise ValueError("optimization objective must return a finite numeric value")
    try:
        encoded_diagnostics = json.dumps(diagnostics, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise ValueError("optimization objective diagnostics must be JSON-compatible") from exc
    if len(encoded_diagnostics.encode("utf-8")) > 100_000:
        raise ValueError("optimization objective diagnostics exceed the 100000-byte limit")
    return float(value), diagnostics


def smoke_risk_manager(manager: RiskManager) -> tuple[Mapping[str, object], ...]:
    """Run a deterministic bounded risk-manager fixture."""
    order = {
        "client_order_id": "fixture-order",
        "symbol": "SYNTH",
        "side": "buy",
        "qty": 1.0,
        "order_type": "market",
    }
    context = RiskContext(
        positions={},
        open_orders=(),
        price_lookup={"SYNTH": 100.0},
        run_id="implementation-validation",
        cycle_id="fixture",
        decision_ts=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    approved, rejected = manager.evaluate([order], context)
    return tuple(dict(item) for item in (*approved, *rejected))


def _factory(module: object, implementation: ImplementationVersion) -> Any:
    name = str(implementation.entrypoint.get("factory_name") or "")
    factory = getattr(module, name, None)
    if not callable(factory):
        raise ValueError(f"implementation factory not found: {name}")
    class_name = str(implementation.entrypoint.get("class_name") or "")
    if class_name and not hasattr(module, class_name):
        raise ValueError(f"implementation class not found: {class_name}")
    return factory


def _call_supported(factory: Any, values: Mapping[str, Any]) -> Any:
    signature = inspect.signature(factory)
    accepts_kwargs = any(parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in signature.parameters.values())
    kwargs = dict(values) if accepts_kwargs else {name: value for name, value in values.items() if name in signature.parameters}
    return factory(**kwargs)


def _objective_module_blockers(tree: ast.Module) -> list[str]:
    blockers: list[str] = []
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            continue
        if isinstance(node, ast.FunctionDef):
            if node.decorator_list:
                blockers.append("objective functions cannot use decorators")
            continue
        blockers.append(f"objective module contains executable top-level statement: {node.__class__.__name__}")
    return blockers


def _load_objective_module(module_name: str, source_code: str, *, filename: str) -> types.ModuleType:
    module = types.ModuleType(module_name)

    def restricted_import(
        name: str,
        globals_value: Mapping[str, Any] | None = None,
        locals_value: Mapping[str, Any] | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> Any:
        del globals_value, locals_value
        root = str(name).split(".", 1)[0]
        if level != 0 or root not in _OBJECTIVE_IMPORT_ROOTS:
            raise ImportError(f"objective import is not allowed: {name}")
        return builtins.__import__(name, {}, {}, fromlist, 0)

    restricted_builtins = {**_OBJECTIVE_BUILTINS, "__import__": restricted_import}
    module.__dict__["__builtins__"] = restricted_builtins
    code = compile(source_code, filename, "exec")
    exec(code, module.__dict__)
    return module
