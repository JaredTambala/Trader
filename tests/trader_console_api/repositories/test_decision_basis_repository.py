"""Exact SQL discovery contracts for the Console decision evidence adapter.

Subject: Bounded canonical outcome selection and producer reference revalidation.
Level: Repository unit tests.
Collaborators: SQL cursor double; actual query construction and reference pinning.
Guarantees: Outcome joins use canonical run refs and never latest timestamp guesses.
Non-goals: PostgreSQL planner behavior, canonical domain validation and UI.
"""

import asyncio

from trader_console_api.repositories.decision_basis import DecisionBasisSession


class Cursor:
    description = ()

    async def fetchall(self):
        """Return the empty persisted discovery result."""
        return []


class Connection:
    def __init__(self):
        self.calls = []

    async def execute(self, query, parameters):
        """Retain bound SQL separately from the caller's identity."""
        self.calls.append((query, parameters))
        return Cursor()


def test_outcome_discovery_binds_exact_run_and_bounds_ambiguity():
    """Two canonical matches suffice to refuse an ambiguous terminal selection."""
    connection = Connection()
    run_id = "run'; SELECT secret"
    result = asyncio.run(DecisionBasisSession(connection, "scope-1").outcomes(run_id))
    query, parameters = connection.calls[0]
    assert result == []
    assert "LIMIT 2" in query
    assert "produced_artifact_refs" in query
    assert run_id not in query
    assert parameters[0].obj == [{"artifact_type": "backtest_run", "artifact_id": run_id}]


def test_review_discovery_uses_explicit_payload_run_identity():
    """Standalone review evidence must name the run directly in its payload."""
    connection = Connection()
    asyncio.run(DecisionBasisSession(connection, "scope-1").linked("run-1", ("evaluation_report",)))
    query, parameters = connection.calls[0]
    assert "payload->>'run_id' = %s" in query
    assert "LIMIT 33" in query
    assert parameters == [["evaluation_report"], "run-1"]
