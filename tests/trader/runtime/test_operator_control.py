"""Core runtime contracts for consuming paper operator commands.

Subject: Human principal policy and runtime command outcomes.
Level: Runtime unit tests.
Collaborators: Lightweight event-store/ broker doubles; no external broker or database.
Guarantees: Halt/stop commands use core primitives and reconciliation failures stay ambiguous.
Non-goals: Console authentication, admission projection SQL, and end-to-end process startup.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone

from trader.runtime.operator_control import (
    OperatorCommand,
    apply_operator_command,
    is_human_operator_principal,
)


class _Cursor:
    def __init__(self, rows: list[tuple[object, ...]] | None = None) -> None:
        self._rows = rows or []

    def fetchall(self) -> list[tuple[object, ...]]:
        """Return the configured query rows."""
        return self._rows


class _Connection:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.outcomes: list[tuple[object, ...]] = []

    def execute(self, query: str, parameters: list[object] | None = None) -> _Cursor:
        """Handle the bounded config and command update SQL used by the test."""
        params = parameters or []
        if query.startswith("INSERT INTO config_kv"):
            self.values[str(params[0])] = str(params[1])
        if query.startswith("SELECT key, value FROM config_kv"):
            keys = {str(value) for value in params}
            return _Cursor([(key, value) for key, value in self.values.items() if key in keys])
        if query.startswith("UPDATE paper_operator_commands"):
            self.outcomes.append(tuple(params))
        return _Cursor()


class _Store:
    def __init__(self) -> None:
        self.connection_value = _Connection()

    def connection(self) -> _Connection:
        """Expose the bounded SQL double."""
        return self.connection_value

    @contextmanager
    def transaction(self):
        """Provide the event-store transaction seam."""
        yield


class _Broker:
    def reconcile_orders(self):
        """Raise to model a remote outcome that cannot be established."""
        raise RuntimeError("broker timeout")


def _command(command: str, reason: str | None = None) -> OperatorCommand:
    return OperatorCommand(
        command_id="command-1",
        scope_id="paper-primary",
        command=command,  # type: ignore[arg-type]
        admission_id="admission-1",
        requested_by="human:operator",
        reason=reason,
        status="accepted",
        requested_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def test_human_namespace_is_required_for_operator_mutation() -> None:
    """Agent and MCP namespaces never satisfy the core operator policy."""
    assert is_human_operator_principal("human:operator")
    assert is_human_operator_principal("operator:operator")
    assert not is_human_operator_principal("agent:research")
    assert not is_human_operator_principal("mcp:client")


def test_reconcile_failure_is_recorded_as_ambiguous() -> None:
    """A broker timeout never becomes a false successful reconciliation."""
    store = _Store()
    outcome = apply_operator_command(
        store, _command("reconcile"), broker=_Broker(), now=datetime(2026, 1, 1, tzinfo=timezone.utc)
    )
    assert outcome.status == "ambiguous"
    assert outcome.outcome_code == "reconciliation_outcome_unknown"
    assert store.connection_value.outcomes[-1][0] == "ambiguous"


def test_pause_uses_global_halt_primitive_and_records_completion() -> None:
    """Pause sets the existing halt state and produces an auditable completion."""
    store = _Store()
    outcome = apply_operator_command(
        store,
        _command("pause", reason="operator pause"),
        now=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    assert outcome.status == "completed"
    assert store.connection_value.values["halt"] == "true"
    assert store.connection_value.values["halt_reason"] == "operator pause"
