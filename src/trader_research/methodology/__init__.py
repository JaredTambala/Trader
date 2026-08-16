"""Expose deterministic computational-methodology engineering services.

The package validates method contracts, generates quarantined implementations,
runs diagnostics and multiple-testing controls, and packages admitted evidence.
It does not execute trading experiments or place generated code on the live path.
"""

from .contracts import MethodContract, MethodRegistryEntry, MethodValidationReport, ParameterSpec
from .implementation import generation_messages, generation_response_schema
from .packaging import MethodPackageManifest, method_package_path, package_method_artifact
from .registry import get_method, list_methods, maintained_method_contracts
from .services import (
    MATH_COMPILE_KERNEL,
    MATH_GENERATE_CPP_KERNEL,
    MATH_GENERATE_PYTHON_METHOD,
    MATH_LIST_METHOD_CONTRACTS,
    MATH_PACKAGE_METHOD_ARTIFACT,
    MATH_REGISTER_METHOD_IMPLEMENTATION,
    MATH_RUN_INDICATOR_FIXTURES,
    MATH_RUN_MULTIPLE_TESTING_REPORT,
    MATH_RUN_SIGNAL_DIAGNOSTICS,
    MATH_RUN_SIGNAL_FIXTURES,
    MATH_VALIDATE_METHOD_CONTRACT,
    math_compile_kernel,
    math_generate_cpp_kernel,
    math_generate_python_method,
    math_list_method_contracts,
    math_package_method_artifact,
    math_register_method_implementation,
    math_run_indicator_fixtures,
    math_run_multiple_testing_report,
    math_run_signal_diagnostics,
    math_run_signal_fixtures,
    math_validate_method_contract,
)

__all__ = [
    "MATH_COMPILE_KERNEL",
    "MATH_GENERATE_CPP_KERNEL",
    "MATH_GENERATE_PYTHON_METHOD",
    "MATH_LIST_METHOD_CONTRACTS",
    "MATH_PACKAGE_METHOD_ARTIFACT",
    "MATH_REGISTER_METHOD_IMPLEMENTATION",
    "MATH_RUN_INDICATOR_FIXTURES",
    "MATH_RUN_MULTIPLE_TESTING_REPORT",
    "MATH_RUN_SIGNAL_DIAGNOSTICS",
    "MATH_RUN_SIGNAL_FIXTURES",
    "MATH_VALIDATE_METHOD_CONTRACT",
    "MethodContract",
    "MethodPackageManifest",
    "MethodRegistryEntry",
    "MethodValidationReport",
    "ParameterSpec",
    "get_method",
    "generation_messages",
    "generation_response_schema",
    "list_methods",
    "maintained_method_contracts",
    "math_compile_kernel",
    "math_generate_cpp_kernel",
    "math_generate_python_method",
    "math_list_method_contracts",
    "math_package_method_artifact",
    "math_register_method_implementation",
    "math_run_indicator_fixtures",
    "math_run_multiple_testing_report",
    "math_run_signal_diagnostics",
    "math_run_signal_fixtures",
    "math_validate_method_contract",
    "method_package_path",
    "package_method_artifact",
]
