"""Storage contract checks for the Console agent-session workspace.

Subject: Explicit producer projection and command-intent catalogues.
Level: Repository schema contract.
Collaborators: SQL contract constants only; no PostgreSQL connection or runtime.
Guarantees: Command storage is explicit, constrained, and separate from canonical
agent evidence; no compatibility reader or implicit bootstrap is introduced.
Non-goals: Query mapping, command application, HTTP authority, and UI behavior.
"""

from trader_console_api.repositories.agent_sessions_schema import (
    CATALOG_SQL,
    COMMAND_COLUMNS,
    INSTALL_SQL,
    RECEIPT_COLUMNS,
    SESSION_COLUMNS,
)


def test_agent_session_storage_requires_three_explicit_relations() -> None:
    """The read projections and append-only command table are named in one contract."""
    assert set(SESSION_COLUMNS) == {
        "session_id",
        "operator_id",
        "model_profile_id",
        "tool_catalog_id",
        "status",
        "payload",
    }
    assert "research_agent_sessions" in CATALOG_SQL
    assert "research_agent_decision_receipts" in CATALOG_SQL
    assert set(RECEIPT_COLUMNS) >= {"receipt_id", "session_id", "payload"}
    assert "CREATE TABLE IF NOT EXISTS console_app.agent_session_commands" in INSTALL_SQL
    assert "CREATE TABLE IF NOT EXISTS console_app.agent_session_public_states" in INSTALL_SQL
    assert "lease_expires_at" in INSTALL_SQL
    assert "UNIQUE (scope_id, idempotency_key)" in INSTALL_SQL
    assert "CHECK (command IN ('inspect', 'interrupt', 'resume', 'cancel'))" in INSTALL_SQL
    assert "prompt" not in INSTALL_SQL.lower()
    assert "credential" not in INSTALL_SQL.lower()
    assert "raw_payload" not in INSTALL_SQL.lower()
    assert "command_id" in COMMAND_COLUMNS
