"""Provide a narrow read boundary for evidence-backed method cards.

Callers may resolve canonical cards and, when required, enforce approved lifecycle
status and method ownership. The port intentionally exposes no drafting,
publication, retirement, or underlying-store mutation operations.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence

from .domain import MethodCard
from .store import KnowledgeStore, KnowledgeStoreError


class ApprovedMethodCardReadError(RuntimeError):
    """Raised when canonical method-card evidence cannot be read safely."""


class ApprovedMethodCardReader(Protocol):
    """Read approved methodology evidence without exposing card mutation."""

    def get_method_card(self, method_card_id: str) -> MethodCard | None:
        """Return one canonical card without granting mutation access."""

    def get_approved_method_card(self, method_card_id: str) -> MethodCard | None:
        """Return one approved card, or ``None`` for absent/non-approved records."""

    def has_approved_method_card(
        self,
        method_card_ids: Sequence[str],
        *,
        method_id: str | None = None,
    ) -> bool:
        """Return whether the references contain an approved matching card."""


@dataclass(frozen=True)
class StoreBackedApprovedMethodCardReader:
    """Approved-card reader backed by the canonical knowledge store."""

    knowledge_store: KnowledgeStore

    def get_method_card(self, method_card_id: str) -> MethodCard | None:
        """Return one canonical card regardless of lifecycle status."""
        try:
            return get_stored_method_card(self.knowledge_store, method_card_id)
        except KnowledgeStoreError as exc:
            raise ApprovedMethodCardReadError(str(exc)) from exc

    def get_approved_method_card(self, method_card_id: str) -> MethodCard | None:
        """Return one approved canonical method card."""
        card = self.get_method_card(method_card_id)
        return card if card is not None and card.approved else None

    def has_approved_method_card(
        self,
        method_card_ids: Sequence[str],
        *,
        method_id: str | None = None,
    ) -> bool:
        """Check approved card identity and optional method ownership."""
        for method_card_id in method_card_ids:
            card = self.get_approved_method_card(str(method_card_id))
            if card is not None and (method_id is None or card.method_id == method_id):
                return True
        return False


def get_stored_method_card(knowledge_store: KnowledgeStore, method_card_id: str) -> MethodCard | None:
    """Resolve one stored method card regardless of lifecycle visibility.

    Blank IDs return ``None``. Otherwise the first exact immutable card ID is
    selected from persisted cards, including draft, rejected, or superseded entries.
    """
    normalized_id = method_card_id.strip()
    if not normalized_id:
        return None
    return next(
        (
            card
            for card in knowledge_store.list_persisted_method_cards()
            if card.method_card_id == normalized_id
        ),
        None,
    )
