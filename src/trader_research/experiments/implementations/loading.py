"""Transient loading of admitted implementation source."""

from __future__ import annotations

import types


def load_module_from_source(
    module_name: str,
    source_code: str,
    *,
    filename: str,
) -> types.ModuleType:
    """Compile DB-stored implementation source into an isolated module object."""
    module = types.ModuleType(module_name)
    code = compile(source_code, filename, "exec")
    exec(code, module.__dict__)
    return module
