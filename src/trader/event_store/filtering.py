"""Pure event-store filtering policy values."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

__all__ = ["EventFilterPolicy", "build_event_filter_policy"]


@dataclass(frozen=True)
class EventFilterPolicy:
    """Immutable allowlist policy for optional event-store writes."""

    allowed_event_types: frozenset[str]

    def allows(self, event_type: str) -> bool:
        """Return whether one event type should be delegated to the inner store."""
        return event_type in self.allowed_event_types


def build_event_filter_policy(allowed_event_types: Iterable[str]) -> EventFilterPolicy:
    """Return an immutable event-filter policy from configured event names."""
    return EventFilterPolicy(frozenset(allowed_event_types))
