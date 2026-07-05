"""Method-contract loading for Quantitative Methods tools."""

from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path

from trader_research.knowledge.store import KnowledgeStore
from .contracts import MethodRegistryEntry


BOOTSTRAP_METHOD_CONTRACTS_PATH = Path(__file__).resolve().parents[1] / "method_contracts_seed.json"


@lru_cache(maxsize=1)
def seed_method_contracts() -> tuple[MethodRegistryEntry, ...]:
    """Load bundled bootstrap method contracts from the repository seed JSON file.

    The result is cached because the seed data is immutable at runtime and used as
    the fallback registry when no persisted store entries exist. Each payload is
    converted into a typed `MethodRegistryEntry` before tools inspect it.
    """
    payload = json.loads(BOOTSTRAP_METHOD_CONTRACTS_PATH.read_text(encoding="utf-8"))
    return tuple(
        MethodRegistryEntry.from_dict(method)
        for method in payload.get("methods", ())
    )


def save_bootstrap_method_contracts(knowledge_store: KnowledgeStore) -> None:
    """Write bundled method contracts into a configured knowledge store.

    Store implementations are expected to upsert by method ID, so calling this
    during startup or tests is safe and refreshes the persisted registry with the
    current bundled contracts without duplicating entries.
    """
    for method in seed_method_contracts():
        knowledge_store.save_method_contract(method)


def list_methods(
    *,
    family: str | None = None,
    status: str | None = None,
    include_planned: bool = True,
    knowledge_store: KnowledgeStore | None = None,
) -> tuple[MethodRegistryEntry, ...]:
    """List method contracts from the store, falling back to seed data only when no store data exists."""
    source_methods = _stored_methods(knowledge_store) or seed_method_contracts()
    methods = []
    for entry in source_methods:
        if family and entry.family != family:
            continue
        if status and entry.status != status:
            continue
        if not include_planned and entry.status != "approved":
            continue
        methods.append(entry)
    return tuple(sorted(methods, key=lambda item: item.method_id))


def get_method(method_id: str, *, knowledge_store: KnowledgeStore | None = None) -> MethodRegistryEntry | None:
    """Return one method contract from the store, falling back to seed data only when no store data exists."""
    stored = _stored_methods(knowledge_store)
    source_methods = stored or seed_method_contracts()
    by_id = {method.method_id: method for method in source_methods}
    return by_id.get(method_id)


def _stored_methods(knowledge_store: KnowledgeStore | None) -> tuple[MethodRegistryEntry, ...]:
    if knowledge_store is None:
        return tuple()
    return knowledge_store.list_persisted_method_contracts()
