"""Quantitative Methods contracts, tooling, diagnostics, and packages.

The package keeps submodule imports lightweight because knowledge storage imports
method contracts during MCP server startup. Public package attributes are loaded
lazily so callers can still use ergonomic imports such as
`from trader_research.methods import math_validate_method_contract`.
"""

from typing import Any


_EXPORT_MODULES = {
    "MATH_COMPILE_KERNEL": "trader_research.methods.tools",
    "MATH_GENERATE_CPP_KERNEL": "trader_research.methods.tools",
    "MATH_GENERATE_PYTHON_METHOD": "trader_research.methods.tools",
    "MATH_LIST_METHOD_CONTRACTS": "trader_research.methods.tools",
    "MATH_PACKAGE_METHOD_ARTIFACT": "trader_research.methods.tools",
    "MATH_REGISTER_METHOD_IMPLEMENTATION": "trader_research.methods.tools",
    "MATH_RUN_INDICATOR_FIXTURES": "trader_research.methods.tools",
    "MATH_RUN_MULTIPLE_TESTING_REPORT": "trader_research.methods.tools",
    "MATH_RUN_SIGNAL_DIAGNOSTICS": "trader_research.methods.tools",
    "MATH_RUN_SIGNAL_FIXTURES": "trader_research.methods.tools",
    "MATH_VALIDATE_METHOD_CONTRACT": "trader_research.methods.tools",
    "MethodContract": "trader_research.methods.contracts",
    "MethodPackageManifest": "trader_research.methods.packages",
    "MethodRegistryEntry": "trader_research.methods.contracts",
    "MethodValidationReport": "trader_research.methods.contracts",
    "ParameterSpec": "trader_research.methods.contracts",
    "get_method": "trader_research.methods.registry",
    "list_methods": "trader_research.methods.registry",
    "math_compile_kernel": "trader_research.methods.tools",
    "math_generate_cpp_kernel": "trader_research.methods.tools",
    "math_generate_python_method": "trader_research.methods.tools",
    "math_list_method_contracts": "trader_research.methods.tools",
    "math_package_method_artifact": "trader_research.methods.tools",
    "math_register_method_implementation": "trader_research.methods.tools",
    "math_run_indicator_fixtures": "trader_research.methods.tools",
    "math_run_multiple_testing_report": "trader_research.methods.tools",
    "math_run_signal_diagnostics": "trader_research.methods.tools",
    "math_run_signal_fixtures": "trader_research.methods.tools",
    "math_validate_method_contract": "trader_research.methods.tools",
    "method_package_path": "trader_research.methods.packages",
    "package_method_artifact": "trader_research.methods.packages",
    "save_bootstrap_method_contracts": "trader_research.methods.registry",
    "seed_method_contracts": "trader_research.methods.registry",
}


def __getattr__(name: str) -> Any:
    """Load public Quantitative Methods exports on first access.

    Args:
        name: Exported package attribute requested by import machinery or callers.

    Returns:
        The requested object from its bounded implementation module.

    Raises:
        AttributeError: If the name is not part of the public methods surface.
    """
    module_name = _EXPORT_MODULES.get(name)
    if module_name is None:
        raise AttributeError(f"module 'trader_research.methods' has no attribute {name!r}")

    from importlib import import_module

    value = getattr(import_module(module_name), name)
    globals()[name] = value
    return value


__all__ = sorted(_EXPORT_MODULES)
