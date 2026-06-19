"""Public API for citation-backed Python method implementation workflows."""

from __future__ import annotations

from trader_research.method_implementations.fixtures import run_indicator_fixtures, run_signal_fixtures
from trader_research.method_implementations.generation import (
    generate_python_method_from_payload,
    generation_messages,
    generation_response_schema,
)
from trader_research.method_implementations.manifest import (
    DEFAULT_ALLOWED_IMPORTS,
    DEFAULT_ENTRYPOINTS,
    FORBIDDEN_CALLS,
    INDICATOR_RUNTIME_CONTRACT,
    MATH_GENERATE_PYTHON_METHOD,
    MATH_REGISTER_METHOD_IMPLEMENTATION,
    MATH_RUN_INDICATOR_FIXTURES,
    MATH_RUN_SIGNAL_FIXTURES,
    SCHEMA_VERSION,
    SIGNAL_RUNTIME_CONTRACT,
    MethodImplementationManifest,
)
from trader_research.method_implementations.registration import register_method_implementation


__all__ = [
    "DEFAULT_ALLOWED_IMPORTS",
    "DEFAULT_ENTRYPOINTS",
    "FORBIDDEN_CALLS",
    "INDICATOR_RUNTIME_CONTRACT",
    "MATH_GENERATE_PYTHON_METHOD",
    "MATH_REGISTER_METHOD_IMPLEMENTATION",
    "MATH_RUN_INDICATOR_FIXTURES",
    "MATH_RUN_SIGNAL_FIXTURES",
    "MethodImplementationManifest",
    "SCHEMA_VERSION",
    "SIGNAL_RUNTIME_CONTRACT",
    "generate_python_method_from_payload",
    "generation_messages",
    "generation_response_schema",
    "register_method_implementation",
    "run_indicator_fixtures",
    "run_signal_fixtures",
]
