"""Catalog contract for the research-owned next-decision Console projection.

Subject: Fail-closed catalog verification for the typed research projection.
Level: Repository unit contract.
Collaborators: Schema constants only; no database or command service.
Guarantees: Console checks the research-owned projection without installing or repairing it.
Non-goals: Canonical artifact writes, evidence qualification, and PostgreSQL execution.
"""

from trader_console_api.repositories.next_research_decisions_schema import CATALOG_SQL, COLUMNS


def test_catalog_targets_research_projection_and_expected_columns() -> None:
    """Keep Console's read/write adapter aligned with the research schema owner."""
    assert "table_schema = 'public'" in CATALOG_SQL
    assert "table_name = 'research_next_decisions'" in CATALOG_SQL
    assert COLUMNS["payload"] == "jsonb"
    assert COLUMNS["revision"] == "int4"

