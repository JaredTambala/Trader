"""Core consumer for human-authorized paper operator commands.

The Console owns request authentication, admission validation, idempotency, and
the durable request receipt. The runtime owns applying a receipt to the running
process and records the resulting outcome here. Research, MCP, and agent code
has no import path to this mutation boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Literal, Mapping

from ..broker import Broker
from ..event_store import EventStore
from .status import set_halt_state


OperatorCommandName = Literal["start", "pause", "stop", "set_halt", "clear_halt", "reconcile"]
OperatorCommandStatus = Literal[
    "requested",
    "accepted",
    "completed",
    "rejected",
    "ambiguous",
    "failed",
]


@dataclass(frozen=True)
class OperatorCommand:
    """Normalized command receipt consumed by the runtime process."""

    command_id: str
    scope_id: str
    command: OperatorCommandName
    admission_id: str
    requested_by: str
    reason: str | None
    status: OperatorCommandStatus
    requested_at: datetime


@dataclass(frozen=True)
class OperatorCommandOutcome:
    """Terminal or explicitly ambiguous application result."""

    command_id: str
    status: OperatorCommandStatus
    outcome_code: str
    outcome_message: str
    completed_at: datetime


def is_human_operator_principal(principal_id: str) -> bool:
    """Require an explicit human/operator namespace for mutation authority."""
    normalized = principal_id.strip().lower()
    return normalized.startswith(("human:", "operator:"))


def _utc(value: object) -> datetime:
    """Normalize a database timestamp to an aware UTC value."""
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _row(row: Mapping[str, object]) -> OperatorCommand:
    """Normalize a selected command row without passing a raw mapping onward."""
    command = str(row["command"])
    if command not in {"start", "pause", "stop", "set_halt", "clear_halt", "reconcile"}:
        raise ValueError(f"Unknown paper operator command: {command}")
    status = str(row["status"])
    if status not in {"requested", "accepted", "completed", "rejected", "ambiguous", "failed"}:
        raise ValueError(f"Unknown paper operator command status: {status}")
    return OperatorCommand(
        command_id=str(row["command_id"]),
        scope_id=str(row["scope_id"]),
        command=command,  # type: ignore[arg-type]
        admission_id=str(row["admission_id"]),
        requested_by=str(row["requested_by"]),
        reason=str(row["reason"]) if row.get("reason") is not None else None,
        status=status,  # type: ignore[arg-type]
        requested_at=_utc(row["requested_at"]),
    )


def _connection(event_store: EventStore) -> Any:
    connection = getattr(event_store, "connection", lambda: None)()
    if connection is None:
        raise ValueError("Operator command consumption requires a SQL event-store connection")
    return connection


def claim_pending_operator_commands(event_store: EventStore, *, limit: int = 20) -> tuple[OperatorCommand, ...]:
    """Atomically claim a bounded batch of requests for the running process."""
    connection = _connection(event_store)
    commands: list[OperatorCommand] = []
    with event_store.transaction():
        cursor = connection.execute(
            "SELECT command_id, scope_id, command, admission_id, requested_by, reason, status, requested_at "
            "FROM paper_operator_commands WHERE status = 'requested' "
            "ORDER BY requested_at, command_id LIMIT %s FOR UPDATE SKIP LOCKED",
            [limit],
        )
        rows = cursor.fetchall()
        for values in rows:
            row = {
                "command_id": values[0],
                "scope_id": values[1],
                "command": values[2],
                "admission_id": values[3],
                "requested_by": values[4],
                "reason": values[5],
                "status": values[6],
                "requested_at": values[7],
            }
            command = _row(row)
            connection.execute(
                "UPDATE paper_operator_commands SET status = 'accepted', accepted_at = transaction_timestamp() "
                "WHERE command_id = %s AND status = 'requested'",
                [command.command_id],
            )
            commands.append(command)
    return tuple(commands)


def _record_outcome(event_store: EventStore, outcome: OperatorCommandOutcome) -> None:
    """Persist one terminal or ambiguous command outcome."""
    connection = _connection(event_store)
    connection.execute(
        "UPDATE paper_operator_commands SET status = %s, outcome_code = %s, outcome_message = %s, "
        "completed_at = %s WHERE command_id = %s AND status = 'accepted'",
        [
            outcome.status,
            outcome.outcome_code,
            outcome.outcome_message,
            outcome.completed_at,
            outcome.command_id,
        ],
    )


def apply_operator_command(
    event_store: EventStore,
    command: OperatorCommand,
    *,
    stop_callback: Callable[[], None] | None = None,
    broker: Broker | None = None,
    now: datetime | None = None,
) -> OperatorCommandOutcome:
    """Apply one claimed command through existing core operator primitives.

    Reconciliation failures are recorded as ``ambiguous`` because broker state
    cannot be inferred from a failed request. Every other failure is recorded as
    ``failed`` and leaves the global halt state untouched.
    """
    completed_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    try:
        if command.command == "start":
            outcome = OperatorCommandOutcome(
                command.command_id,
                "completed",
                "runtime_already_running",
                "The running Trader process consumed the start request.",
                completed_at,
            )
        elif command.command == "pause":
            set_halt_state(event_store, halted=True, reason=command.reason or "operator_pause", now=completed_at)
            outcome = OperatorCommandOutcome(command.command_id, "completed", "paused", "Paper runtime paused.", completed_at)
        elif command.command == "stop":
            if stop_callback is None:
                raise RuntimeError("The runtime stop callback is unavailable")
            stop_callback()
            outcome = OperatorCommandOutcome(command.command_id, "completed", "stop_requested", "Paper runtime stop requested.", completed_at)
        elif command.command == "set_halt":
            set_halt_state(event_store, halted=True, reason=command.reason or "operator_halt", now=completed_at)
            outcome = OperatorCommandOutcome(command.command_id, "completed", "halt_set", "Paper runtime halt set.", completed_at)
        elif command.command == "clear_halt":
            set_halt_state(event_store, halted=False, reason="", now=completed_at)
            outcome = OperatorCommandOutcome(command.command_id, "completed", "halt_cleared", "Paper runtime halt cleared.", completed_at)
        else:
            if broker is None or not callable(getattr(broker, "reconcile_orders", None)):
                raise RuntimeError("The broker reconciliation operation is unavailable")
            updates = getattr(broker, "reconcile_orders")()
            outcome = OperatorCommandOutcome(
                command.command_id,
                "completed",
                "reconciled",
                f"Broker reconciliation completed with {len(updates or ())} updates.",
                completed_at,
            )
    except Exception as exc:
        status: OperatorCommandStatus = "ambiguous" if command.command == "reconcile" else "failed"
        outcome = OperatorCommandOutcome(
            command.command_id,
            status,
            "reconciliation_outcome_unknown" if command.command == "reconcile" else "command_failed",
            str(exc),
            completed_at,
        )
    with event_store.transaction():
        _record_outcome(event_store, outcome)
    return outcome


def consume_pending_operator_commands(
    event_store: EventStore,
    *,
    stop_callback: Callable[[], None] | None = None,
    broker: Broker | None = None,
    limit: int = 20,
) -> tuple[OperatorCommandOutcome, ...]:
    """Claim and apply pending paper commands at runtime loop boundaries."""
    return tuple(
        apply_operator_command(
            event_store,
            command,
            stop_callback=stop_callback,
            broker=broker,
        )
        for command in claim_pending_operator_commands(event_store, limit=limit)
    )


__all__ = [
    "OperatorCommand",
    "OperatorCommandName",
    "OperatorCommandOutcome",
    "OperatorCommandStatus",
    "apply_operator_command",
    "claim_pending_operator_commands",
    "consume_pending_operator_commands",
    "is_human_operator_principal",
]
