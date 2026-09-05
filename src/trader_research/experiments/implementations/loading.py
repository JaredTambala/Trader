"""Compile admitted implementation source into transient Python modules.

Loading operates only on source already admitted by the research validation
path. The resulting module exists in memory for the current process and is not
registered in the global import system or persisted by this module.
"""

from __future__ import annotations

import types


def load_module_from_source(
    module_name: str,
    source_code: str,
    *,
    filename: str,
) -> types.ModuleType:
    """Compile source into a new transient module namespace.

    ``filename`` is retained in syntax errors and tracebacks. The module is not
    inserted into ``sys.modules``, but this helper is not a security sandbox and
    must receive source that has already passed admission policy.
    """
    module = types.ModuleType(module_name)
    code = compile(source_code, filename, "exec")
    exec(code, module.__dict__)
    return module
