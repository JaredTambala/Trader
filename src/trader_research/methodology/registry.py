"""Immutable maintained method-contract catalog."""

from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path

from .contracts import MethodRegistryEntry


MAINTAINED_METHOD_CONTRACTS_PATH = Path(__file__).with_name("maintained_method_contracts.json")


@lru_cache(maxsize=1)
def maintained_method_contracts() -> tuple[MethodRegistryEntry, ...]:
    """Load bundled computational contracts from immutable package data.

    The result is cached because the seed data is immutable at runtime and used as
    the fallback registry when no persisted store entries exist. Each payload is
    converted into a typed `MethodRegistryEntry` before tools inspect it.
    """
    payload = json.loads(MAINTAINED_METHOD_CONTRACTS_PATH.read_text(encoding="utf-8"))
    return tuple(
        MethodRegistryEntry.from_dict(method)
        for method in payload.get("methods", ())
    )


def list_methods(
    *,
    family: str | None = None,
    status: str | None = None,
    include_planned: bool = True,
) -> tuple[MethodRegistryEntry, ...]:
    """List maintained method contracts after deterministic filtering."""
    methods = []
    for entry in maintained_method_contracts():
        if family and entry.family != family:
            continue
        if status and entry.status != status:
            continue
        if not include_planned and entry.status != "approved":
            continue
        methods.append(entry)
    return tuple(sorted(methods, key=lambda item: item.method_id))


def get_method(method_id: str) -> MethodRegistryEntry | None:
    """Return one maintained method contract by stable ID."""
    by_id = {method.method_id: method for method in maintained_method_contracts()}
    return by_id.get(method_id)
