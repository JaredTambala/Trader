"""Schema and projection contracts for human next-decision artifacts.

Subject: Research-owned typed projection declaration and writer dispatch.
Level: Offline adapter contract.
Collaborators: Declared schema and a synchronous SQL capture double; no live Postgres or Console.
Guarantees: The canonical schema contains the next-decision projection and its writer is registered.
Non-goals: PostgreSQL planner behavior, evidence qualification, and HTTP transport.
"""

from __future__ import annotations

from typing import Any

from trader_research.foundation import ORCHESTRATION_DOMAIN_OWNER
from trader_research.foundation.artifacts import build_artifact_record
from trader_research.governance.artifacts import RESEARCH_NEXT_DECISION
from trader_research.infrastructure.postgres import RESEARCH_ARTIFACT_SCHEMA_STATEMENTS
from trader_research.infrastructure.postgres.projections import default_projection_registry


def _record():
    """Build one projection payload accepted by the writer."""
    return build_artifact_record(
        artifact_type=RESEARCH_NEXT_DECISION,
        artifact_id="research_next_decision_1",
        domain_owner=ORCHESTRATION_DOMAIN_OWNER,
        producer_tool="console_record_next_decision",
        actor="human:jared",
        payload={
            "artifact_type": RESEARCH_NEXT_DECISION,
            "decision_id": "decision-1",
            "revision": 1,
            "outcome": "reject",
            "operator": "human:jared",
            "decided_at": "2026-10-05T10:00:00Z",
            "source_run_ref": {"artifact_id": "run-1"},
            "decision_digest": "a" * 64,
        },
    )


class _Connection:
    def __init__(self) -> None:
        self.statement = ""
        self.parameters: list[Any] = []

    def execute(self, statement: str, parameters: list[Any]) -> None:
        """Capture one writer call."""
        self.statement = statement
        self.parameters = parameters


def test_schema_and_registry_expose_next_decision_projection() -> None:
    """Keep typed schema and context-owned writer registration together."""
    schema = "\n".join(RESEARCH_ARTIFACT_SCHEMA_STATEMENTS)
    assert "CREATE TABLE IF NOT EXISTS research_next_decisions" in schema
    assert RESEARCH_NEXT_DECISION in default_projection_registry().writers


def test_next_decision_projection_writer_flattens_identity() -> None:
    """The projection carries revision and source-run identity without replacing the payload."""
    connection = _Connection()
    default_projection_registry().write(connection, _record(), json_value=lambda value: value)
    assert "INSERT INTO research_next_decisions" in connection.statement
    assert connection.parameters[1:6] == ["decision-1", 1, "reject", "run-1", "human:jared"]

