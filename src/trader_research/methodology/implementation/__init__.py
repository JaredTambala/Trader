"""Expose citation-backed Python method implementation workflows.

The facade generates source into quarantine, validates manifests and provenance,
runs deterministic fixtures, and registers accepted build artifacts. Generated
code remains research evidence and must still pass normal strategy admission.
"""

from __future__ import annotations

from trader_research.methodology.implementation.fixtures import run_indicator_fixtures, run_signal_fixtures
from trader_research.methodology.implementation.generation import (
    generate_python_method_from_payload,
    generation_messages,
    generation_response_schema,
)
from trader_research.methodology.implementation.manifest import (
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
from trader_research.methodology.implementation.registration import register_method_implementation


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
