"""Event store interface for persisting trading system events."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Mapping


class EventStore(ABC):
    """Persists append-only events for traceability."""

    @abstractmethod
    def record_event(self, event_type: str, payload: Mapping[str, object]) -> None:
        """Record a single event with a typed payload."""


class NoOpEventStore(EventStore):
    """Event store used for a no-op cycle."""

    def record_event(self, event_type: str, payload: Mapping[str, object]) -> None:
        return None
