"""Construct and exercise validated implementations within bounded fixtures.

Runtime helpers recheck source identity and declared parameters before creating
strategies, risk managers, or closed-input objectives. Static safety inspection
and smoke fixtures return explicit blockers rather than granting arbitrary
filesystem, network, broker, or process access.
"""

from __future__ import annotations

import ast
import builtins
from datetime import datetime, timezone
import inspect
import json
import math
import types
from typing import Any, Mapping, Sequence

from trader.risk import RiskContext, RiskManager
from trader.strategies import Strategy
from .loading import load_module_from_source

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
_FORBIDDEN_NAMES = _FORBIDDEN_CALLS | frozenset(
    {
        "__builtins__",
        "breakpoint",
        "getattr",
        "globals",
        "input",
        "locals",
        "setattr",
        "vars",
    }
)
_FORBIDDEN_ATTRIBUTES = frozenset(
    {
        "commit",
        "connect",
        "connection",
        "cursor",
        "execute",
        "executemany",
        "open",
        "place_order",
        "popen",
        "record_event",
        "remove",
        "rmdir",
        "rollback",
        "submit_order",
        "system",
        "unlink",
    }
)
_FORBIDDEN_IMPORT_PREFIXES = (
    "trader.broker",
    "trader.config",
    "trader.event_store",
    "trader.market_data.alpaca",
    "trader.operator",
    "trader.runtime",
    "trader.web",
)
_FORBIDDEN_OBJECTIVE_NAMES = _FORBIDDEN_CALLS | frozenset(
    {"__builtins__", "breakpoint", "dir", "help", "memoryview"}
)
_OBJECTIVE_IMPORT_ROOTS = frozenset({"math"})
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
    """Inspect implementation source for statically detectable unsafe behavior.

    The scan parses source without executing it and checks imports, calls, names,
    dunder access, and the narrower closed-input objective rules. It is an
    admission control, not a general Python sandbox or proof of runtime safety.

    Returns:
        Sorted unique blocker messages, including syntax errors. An empty tuple
        means no maintained static rule was violated.
    """
    blockers: list[str] = []
    try:
        tree = ast.parse(implementation.source_code)
    except SyntaxError as exc:
        return (f"source code does not compile: {exc}",)
    allowed_roots = _ALLOWED_IMPORT_ROOTS
    if implementation.implementation_kind == "optimization_objective":
        allowed_roots = _OBJECTIVE_IMPORT_ROOTS
        blockers.extend(_objective_module_blockers(tree))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                blockers.extend(_import_blockers(alias.name, allowed_roots))
                if alias.name == "trader":
                    blockers.append("broad import is not allowed: trader")
        elif isinstance(node, ast.ImportFrom):
            module = str(node.module or "")
            blockers.extend(_import_blockers(module, allowed_roots))
            for alias in node.names:
                blockers.extend(
                    _import_blockers(f"{module}.{alias.name}", allowed_roots)
                )
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
        if isinstance(node, ast.Name) and node.id in _FORBIDDEN_NAMES:
            blockers.append(f"unsafe name is not allowed: {node.id}")
        if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            blockers.append(f"dunder attribute is not allowed: {node.attr}")
        if implementation.implementation_kind == "optimization_objective":
            if isinstance(node, ast.Name) and node.id in _FORBIDDEN_OBJECTIVE_NAMES:
                blockers.append(f"unsafe objective name is not allowed: {node.id}")
    return tuple(sorted(set(blockers)))


def _import_blockers(module_name: str, allowed_roots: frozenset[str]) -> list[str]:
    module = str(module_name or "")
    root = module.split(".", 1)[0]
    if not root or root not in allowed_roots:
        return [f"import is not allowed: {root or '<relative>'}"]
    if any(
        module == prefix or module.startswith(f"{prefix}.")
        for prefix in _FORBIDDEN_IMPORT_PREFIXES
    ):
        return [f"import is not allowed: {module}"]
    return []


def load_implementation(implementation: ImplementationVersion) -> object:
    """Load an admitted implementation into a version-specific namespace.

    Objective code uses the narrower objective loader; other kinds use the
    transient module loader. This function assumes source identity and safety were
    already validated and does not repeat persistence or admission checks.
    """
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
    prediction_bindings: Sequence[object] | None = None,
) -> Strategy:
    """Instantiate a validated strategy from declared runtime inputs.

    The implementation is loaded in memory, its factory receives only supported
    symbol, asset, timeframe, parameter, sizing, and optional prediction values,
    and the result must implement Trader's ``Strategy`` contract. Prediction
    bindings are required exactly when the implementation declares them.

    Returns:
        The constructed Trader strategy instance.

    Raises:
        ValueError: If the factory is missing, prediction bindings conflict with
            declared requirements, or the factory returns the wrong type.
    """
    module = load_implementation(implementation)
    factory = _factory(module, implementation)
    prediction_requirements = implementation.runtime_requirements.get("prediction_requirements") or []
    if prediction_requirements and prediction_bindings is None:
        raise ValueError("model-backed strategy implementation requires prediction_bindings")
    if not prediction_requirements and prediction_bindings:
        raise ValueError("strategy implementation does not declare prediction requirements")
    kwargs = {
        "symbols": symbols,
        "asset_class": asset_class,
        "timeframe": timeframe,
        **dict(parameters),
        **dict(sizing or {}),
    }
    if prediction_requirements:
        kwargs["prediction_bindings"] = tuple(prediction_bindings or ())
    instance = _call_supported(factory, kwargs)
    if not isinstance(instance, Strategy):
        raise ValueError("implementation factory did not return trader.strategies.Strategy")
    return instance


def instantiate_risk_manager(
    implementation: ImplementationVersion,
    *,
    parameters: Mapping[str, Any],
) -> RiskManager:
    """Instantiate a validated risk manager from declared parameters.

    Factories that accept a single ``parameters`` mapping receive a copy of the
    mapping; other factories receive only keyword arguments present in their
    signature. The returned object must implement Trader's ``RiskManager`` port.

    Returns:
        The constructed risk-manager instance.

    Raises:
        ValueError: If the entrypoint is missing or returns the wrong type.
    """
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
    """Evaluate a validated objective over one closed optimization observation.

    The observation is normalized to the provider-neutral public schema before
    execution. Objectives may return a scalar or ``{value, diagnostics}``; the
    value must be finite and diagnostics must be JSON-compatible and no larger
    than 100,000 encoded bytes.

    Returns:
        The finite scalar objective value and bounded diagnostic metadata.

    Raises:
        ValueError: If the entrypoint is invalid or its output violates the
            objective return contract.
    """
    from trader_research.experiments.optimization.contracts import OptimizationObservation

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
    """Exercise a risk manager with one deterministic synthetic order.

    The fixed context contains no positions or open orders and prices ``SYNTH``
    at 100. The fixture performs no broker, database, clock, or network access.

    Returns:
        Normalized approved and rejected orders in that order for inclusion in
        implementation-validation evidence.
    """
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
