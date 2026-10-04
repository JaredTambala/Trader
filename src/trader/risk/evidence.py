"""Typed, deterministic evidence for risk composition and decisions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Mapping, Sequence


_ORDER_FIELDS = (
    "client_order_id",
    "signal_event_id",
    "symbol",
    "side",
    "qty",
    "price",
    "order_type",
    "time_in_force",
)


def _normalize_value(value: object) -> object:
    """Return a JSON-stable primitive representation for evidence payloads."""
    if isinstance(value, Mapping):
        return {
            str(key): _normalize_value(value[key])
            for key in sorted(value, key=lambda item: str(item))
        }
    if isinstance(value, (list, tuple)):
        return [_normalize_value(item) for item in value]
    if isinstance(value, datetime):
        timestamp = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return timestamp.astimezone(timezone.utc).isoformat()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def normalize_order(order: Mapping[str, object] | None) -> dict[str, object] | None:
    """Keep only the stable order fields exposed in risk evidence."""
    if order is None:
        return None
    return {
        field: _normalize_value(order.get(field))
        for field in _ORDER_FIELDS
        if order.get(field) is not None
    }


def orders_differ(
    before: Mapping[str, object],
    after: Mapping[str, object],
) -> bool:
    """Return whether an approved order changed through risk evaluation."""
    return normalize_order(before) != normalize_order(after)


@dataclass(frozen=True)
class RiskManagerDescriptor:
    """Allowlisted identity and typed parameters for one manager."""

    manager_id: str
    manager_type: str
    catalogue_version: str
    parameters: Mapping[str, object]

    def to_payload(self) -> dict[str, object]:
        """Return the producer-owned JSON shape for this descriptor."""
        return {
            "manager_id": self.manager_id,
            "manager_type": self.manager_type,
            "catalogue_version": self.catalogue_version,
            "parameters": _normalize_value(self.parameters),
        }


@dataclass(frozen=True)
class RiskComposition:
    """Ordered risk-manager composition with a deterministic fingerprint."""

    composition_fingerprint: str
    catalogue_version: str
    managers: tuple[RiskManagerDescriptor, ...]

    def to_record(self, *, run_id: str, session_id: str | None = None) -> dict[str, object]:
        """Return an idempotent append-only composition snapshot record."""
        record_id = _fingerprint(
            {"run_id": run_id, "composition": self.composition_fingerprint}
        )
        return {
            "risk_composition_record_id": f"riskcomp_{record_id}",
            "run_id": run_id,
            "session_id": session_id,
            "catalogue_version": self.catalogue_version,
            "composition_fingerprint": self.composition_fingerprint,
            "manager_count": len(self.managers),
            "managers": json.dumps([manager.to_payload() for manager in self.managers], sort_keys=True),
            "created_at": datetime.now(timezone.utc),
        }


@dataclass(frozen=True)
class RiskDecisionTrace:
    """One ordered manager evaluation for one candidate order."""

    risk_decision_id: str
    composition_fingerprint: str
    run_id: str
    session_id: str | None
    cycle_id: str
    client_order_id: str | None
    decision_ts: datetime
    manager_id: str
    manager_type: str
    manager_position: int
    outcome: str
    reason_code: str
    before_order: Mapping[str, object]
    after_order: Mapping[str, object] | None

    def to_record(self) -> dict[str, object]:
        """Return the typed append-only event payload."""
        before = normalize_order(self.before_order) or {}
        after = normalize_order(self.after_order)
        return {
            "risk_decision_id": self.risk_decision_id,
            "composition_fingerprint": self.composition_fingerprint,
            "run_id": self.run_id,
            "session_id": self.session_id,
            "cycle_id": self.cycle_id,
            "client_order_id": self.client_order_id,
            "decision_ts": self.decision_ts,
            "manager_id": self.manager_id,
            "manager_type": self.manager_type,
            "manager_position": self.manager_position,
            "outcome": self.outcome,
            "reason_code": self.reason_code,
            "before_qty": before.get("qty"),
            "after_qty": after.get("qty") if after else None,
            "before_order": json.dumps(before, sort_keys=True),
            "after_order": json.dumps(after, sort_keys=True) if after is not None else None,
        }


def describe_risk_manager(manager: object) -> RiskManagerDescriptor:
    """Resolve a manager's stable descriptor without inspecting private state."""
    describe = getattr(manager, "risk_descriptor", None)
    if callable(describe):
        value = describe()
        if isinstance(value, RiskManagerDescriptor):
            return value
        if isinstance(value, Mapping):
            return RiskManagerDescriptor(
                manager_id=str(value.get("manager_id") or manager.__class__.__name__),
                manager_type=str(value.get("manager_type") or _manager_type(manager)),
                catalogue_version=str(value.get("catalogue_version") or "runtime-1"),
                parameters=dict(value.get("parameters") or {}),
            )
    return RiskManagerDescriptor(
        manager_id=manager.__class__.__name__,
        manager_type=_manager_type(manager),
        catalogue_version="runtime-1",
        parameters={},
    )


def build_risk_composition(managers: Sequence[object]) -> RiskComposition:
    """Build the ordered composition fingerprint for a flattened manager chain."""
    descriptors = tuple(describe_risk_manager(manager) for manager in managers)
    payload = {
        "catalogue_version": "runtime-1",
        "managers": [descriptor.to_payload() for descriptor in descriptors],
    }
    return RiskComposition(
        composition_fingerprint=_fingerprint(payload),
        catalogue_version="runtime-1",
        managers=descriptors,
    )


def build_risk_decision_id(
    *,
    run_id: str,
    cycle_id: str,
    client_order_id: str | None,
    manager_position: int,
    before_order: Mapping[str, object],
) -> str:
    """Build a deterministic identity for one manager evaluation."""
    return f"riskdec_{_fingerprint({
        'run_id': run_id,
        'cycle_id': cycle_id,
        'client_order_id': client_order_id,
        'manager_position': manager_position,
        'before_order': normalize_order(before_order),
    })}"


def _manager_type(manager: object) -> str:
    return f"{manager.__class__.__module__}.{manager.__class__.__qualname__}"


def _fingerprint(value: object) -> str:
    canonical = json.dumps(_normalize_value(value), separators=(",", ":"), sort_keys=True)
    return sha256(canonical.encode("utf-8")).hexdigest()


__all__ = [
    "RiskComposition",
    "RiskDecisionTrace",
    "RiskManagerDescriptor",
    "build_risk_composition",
    "build_risk_decision_id",
    "describe_risk_manager",
    "normalize_order",
    "orders_differ",
]
