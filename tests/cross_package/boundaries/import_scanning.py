"""AST support for repository dependency contracts.

Subject: Extraction of absolute imported module names from one Python source file.
Level: Cross-package test support.
Collaborators: Python AST and a caller-supplied repository path.
Guarantees: Boundary suites share one deterministic import-reading implementation.
Non-goals: Resolving relative imports or enforcing any dependency policy itself.
"""

import ast
from pathlib import Path


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update((alias.name for alias in node.names))
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    return imported
